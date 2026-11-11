"""Misty II backend: drives the robot directly over its built-in HTTP API (nothing to install).

Our four commands map to Misty like this:
  say      -> POST /api/tts/speak        (Misty's on-board voice)
  face     -> POST /api/images/display   (Misty's built-in eye images)
  gesture  -> POST /api/head, /api/arms/set  (short movement sequences)
  led      -> POST /api/led              (chest LED)

When Misty finishes a sentence it publishes a TextToSpeechComplete event on ws://<ip>/pubsub;
we forward that so the participant's mic unmutes right away.

Angles and eye images are in the tables below — tune them on the real robot.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import uuid
from collections.abc import Awaitable, Callable

import httpx

log = logging.getLogger(__name__)

# Misty's default eye images (the "native face").
EYES = {
    "neutral": "e_DefaultContent.jpg",
    "happy": "e_Joy.jpg",
    "sad": "e_Sadness.jpg",
    "angry": "e_Anger.jpg",
    "surprised": "e_Surprise.jpg",
    "thinking": "e_ContentLeft.jpg",
    "listening": "e_DefaultContent.jpg",
}

# Head: pitch (+ = down), roll (+ = tilt), yaw (+ = turn). Degrees. If a move goes the wrong
# way on the real robot, flip the sign here. Each step: (kind, values, seconds to wait after).
HEAD_VELOCITY = 80  # 0-100
ARM_VELOCITY = 80
ARMS_DOWN = 90  # Misty arm angle: about 90 = down, -29 = up
GESTURES = {
    "nod": [
        ("head", {"Pitch": 15}, 0.35),
        ("head", {"Pitch": -5}, 0.35),
        ("head", {"Pitch": 15}, 0.35),
        ("head", {"Pitch": 0}, 0.3),
    ],
    "shake": [
        ("head", {"Yaw": 30}, 0.4),
        ("head", {"Yaw": -30}, 0.5),
        ("head", {"Yaw": 0}, 0.3),
    ],
    "tilt": [
        ("head", {"Roll": 20}, 1.0),
        ("head", {"Roll": 0}, 0.3),
    ],
    "look_down": [
        ("head", {"Pitch": 20}, 1.5),
        ("head", {"Pitch": 0}, 0.3),
    ],
    "celebrate": [
        ("arms", {"Left": -29, "Right": -29}, 0.6),
        ("head", {"Pitch": -10}, 0.4),
        ("arms", {"Left": ARMS_DOWN, "Right": ARMS_DOWN}, 0.5),
        ("head", {"Pitch": 0}, 0.3),
    ],
}

SpeechDone = Callable[[], Awaitable[None]]


def hex_to_rgb(color: str) -> tuple[int, int, int] | None:
    c = color.lstrip("#")
    if len(c) != 6:
        return None
    try:
        return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
    except ValueError:
        return None


class MistyRobot:
    """Turns our robot commands into Misty REST calls. Failures are logged, never raised."""

    def __init__(self, address: str, on_speech_done: SpeechDone | None = None, http=None):
        self.address = address.removeprefix("http://").rstrip("/")
        self.base = f"http://{self.address}"
        self.on_speech_done = on_speech_done
        self.http = http or httpx.AsyncClient(timeout=3.0)
        self._gesture: asyncio.Task | None = None
        self._events: asyncio.Task | None = None

    # ---- connection --------------------------------------------------------
    async def reachable(self) -> bool:
        try:
            res = await self.http.get(f"{self.base}/api/device")
            return res.status_code == 200
        except httpx.HTTPError:
            return False

    def start_events(self) -> None:
        """Listen for 'finished speaking' events in the background."""
        if self._events is None:
            self._events = asyncio.create_task(self._event_loop())

    async def _event_loop(self) -> None:
        import websockets  # installed with uvicorn[standard]

        sub = {
            "Operation": "subscribe",
            "Type": "TextToSpeechComplete",
            "DebounceMs": 0,
            "EventName": "pdhri_tts",
        }
        while True:
            try:
                async with websockets.connect(f"ws://{self.address}/pubsub") as ws:
                    await ws.send(json.dumps(sub))
                    async for raw in ws:
                        await self.handle_event(raw)
            except asyncio.CancelledError:
                raise
            except Exception as e:  # robot off, network hiccup: retry quietly
                log.info("Misty events unavailable (%s); retrying", e)
                await asyncio.sleep(3)

    async def handle_event(self, raw: str | bytes) -> None:
        try:
            msg = json.loads(raw)
        except ValueError:
            return
        # Subscription acks are plain strings; real events carry eventName + message.
        if isinstance(msg, dict) and msg.get("eventName") == "pdhri_tts":
            if self.on_speech_done:
                await self.on_speech_done()

    async def close(self) -> None:
        for task in (self._gesture, self._events):
            if task:
                task.cancel()
        await self.http.aclose()

    # ---- commands ----------------------------------------------------------
    async def handle(self, cmd: dict) -> None:
        kind = cmd.get("cmd")
        if kind == "say":
            await self.say(cmd.get("text", ""))
        elif kind == "face":
            await self.face(cmd.get("mood", "neutral"))
        elif kind == "gesture":
            self.gesture(cmd.get("name", ""))
        elif kind == "led":
            await self.led(cmd.get("color", ""))

    async def _post(self, path: str, body: dict) -> None:
        try:
            res = await self.http.post(f"{self.base}{path}", json=body)
            if res.status_code >= 400:
                log.warning("Misty %s -> HTTP %s: %s", path, res.status_code, res.text[:200])
        except httpx.HTTPError as e:
            log.warning("Misty %s failed: %s", path, e)

    async def say(self, text: str) -> None:
        if text.strip():
            await self._post(
                "/api/tts/speak",
                {"Text": text, "Flush": True, "UtteranceId": uuid.uuid4().hex},
            )

    async def face(self, mood: str) -> None:
        await self._post(
            "/api/images/display",
            {"FileName": EYES.get(mood, EYES["neutral"]), "Alpha": 1},
        )

    async def led(self, color: str) -> None:
        rgb = hex_to_rgb(color)
        if rgb:
            r, g, b = rgb
            await self._post("/api/led", {"red": r, "green": g, "blue": b})

    def gesture(self, name: str) -> None:
        """Start a movement sequence in the background; a new gesture cancels the old one."""
        steps = GESTURES.get(name)
        if not steps:
            return
        if self._gesture and not self._gesture.done():
            self._gesture.cancel()
        self._gesture = asyncio.create_task(self._run_gesture(steps))

    async def _run_gesture(self, steps) -> None:
        with contextlib.suppress(asyncio.CancelledError):
            for kind, values, wait in steps:
                if kind == "head":
                    body = {"Pitch": 0, "Roll": 0, "Yaw": 0, **values}
                    await self._post(
                        "/api/head", {**body, "Velocity": HEAD_VELOCITY, "Units": "degrees"}
                    )
                else:
                    await self._post(
                        "/api/arms/set",
                        {
                            "LeftArmPosition": values["Left"],
                            "RightArmPosition": values["Right"],
                            "LeftArmVelocity": ARM_VELOCITY,
                            "RightArmVelocity": ARM_VELOCITY,
                            "Units": "degrees",
                        },
                    )
                await asyncio.sleep(wait)
