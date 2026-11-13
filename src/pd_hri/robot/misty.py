"""Misty II backend: drives the robot directly over its built-in HTTP API (nothing to install).

Our commands map to Misty like this:
  say      -> POST /api/tts/speak            (Misty's on-board voice)
  face     -> POST /api/images/display       (Misty's built-in eye images, or red versions)
              + a head/arm pose per emotion  (so emotions are big and visible)
  gesture  -> POST /api/head, /api/arms/set  (short movement sequences)
  led      -> POST /api/led                  (chest LED)
  camera   -> GET  /api/cameras/rgb          (frames for facial-expression tracking)

Red eyes: at startup we download Misty's own eye images, recolour the iris red, and upload them
as pdhri_red_<name>.jpg. face(..., tint="red") then shows those and turns the LED red.

When Misty finishes a sentence it publishes TextToSpeechComplete on ws://<ip>/pubsub; we
forward that so the participant's mic unmutes right away.

All angles are in the tables below: tune them on the real robot.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import io
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
RED_PREFIX = "pdhri_red_"
# Professional mode: one plain, machine-like eye image we generate, shown with blinking off.
STATIC_EYES = "pdhri_static.jpg"

# Head angles in degrees: Pitch (+ = down), Roll (+ = tilt), Yaw (+ = turn).
# REST_PITCH looks slightly up, at the face of a person sitting in front of Misty.
# If a move goes the wrong way on the real robot, flip its sign here.
REST_PITCH = -10
HEAD_VELOCITY = 90  # 0-100
ARM_VELOCITY = 90
ARMS_DOWN = 90  # Misty arm angle: 90 = down, 0 = straight forward, -29 = up
ARMS_UP = -29

# A body pose for each emotion, applied when the face changes (makes emotions bigger).
MOOD_POSE = {
    "static": {"head": {"Pitch": REST_PITCH}, "arms": (ARMS_DOWN, ARMS_DOWN)},  # professional
    "neutral": {"head": {"Pitch": REST_PITCH}, "arms": (ARMS_DOWN, ARMS_DOWN)},
    "listening": {"head": {"Pitch": REST_PITCH, "Roll": 12}, "arms": (70, 70)},
    "happy": {"head": {"Pitch": REST_PITCH - 15, "Roll": 10}, "arms": (15, 15)},
    "sad": {"head": {"Pitch": 28}, "arms": (ARMS_DOWN, ARMS_DOWN)},
    "angry": {"head": {"Pitch": 5}, "arms": (60, 60)},
    "surprised": {"head": {"Pitch": REST_PITCH - 20}, "arms": (-15, -15)},
    "thinking": {"head": {"Pitch": REST_PITCH - 5, "Roll": 20, "Yaw": 18}, "arms": (60, 80)},
}

# Gestures: each step is (kind, values, seconds to wait after).
GESTURES = {
    "nod": [
        ("head", {"Pitch": REST_PITCH + 25}, 0.35),
        ("head", {"Pitch": REST_PITCH - 12}, 0.35),
        ("head", {"Pitch": REST_PITCH + 25}, 0.35),
        ("head", {"Pitch": REST_PITCH}, 0.3),
    ],
    "shake": [
        ("head", {"Yaw": 45}, 0.4),
        ("head", {"Yaw": -45}, 0.5),
        ("head", {"Yaw": 35}, 0.45),
        ("head", {"Yaw": 0}, 0.3),
    ],
    "tilt": [
        ("head", {"Roll": 30}, 1.1),
        ("head", {"Roll": 0}, 0.3),
    ],
    "look_down": [
        ("head", {"Pitch": 30}, 1.6),
        ("head", {"Pitch": REST_PITCH}, 0.3),
    ],
    "celebrate": [
        ("arms", (ARMS_UP, ARMS_UP), 0.2),
        ("head", {"Pitch": REST_PITCH - 15, "Roll": 15}, 0.5),
        ("head", {"Pitch": REST_PITCH - 15, "Roll": -15}, 0.5),
        ("arms", (ARMS_DOWN, ARMS_DOWN), 0.2),
        ("head", {"Pitch": REST_PITCH}, 0.3),
    ],
    "open_arms": [  # "trust me": arms wide open, head tilted
        ("arms", (-15, -15), 0.2),
        ("head", {"Pitch": REST_PITCH - 8, "Roll": 15}, 1.4),
        ("arms", (ARMS_DOWN, ARMS_DOWN), 0.2),
        ("head", {"Pitch": REST_PITCH}, 0.3),
    ],
    "point": [  # reach one arm toward the person, lean the head in
        ("arms", (ARMS_DOWN, 0), 0.2),
        ("head", {"Pitch": REST_PITCH + 8, "Yaw": -10}, 1.2),
        ("arms", (ARMS_DOWN, ARMS_DOWN), 0.2),
        ("head", {"Pitch": REST_PITCH}, 0.3),
    ],
    "wave": [
        ("arms", (ARMS_DOWN, ARMS_UP), 0.45),
        ("arms", (ARMS_DOWN, 25), 0.4),
        ("arms", (ARMS_DOWN, ARMS_UP), 0.4),
        ("arms", (ARMS_DOWN, 25), 0.4),
        ("arms", (ARMS_DOWN, ARMS_DOWN), 0.3),
    ],
    "talk_hands": [  # hands and head move together while explaining
        ("arms", (25, 60), 0.1),
        ("head", {"Roll": 12, "Yaw": 8}, 0.5),
        ("arms", (60, 20), 0.1),
        ("head", {"Roll": -12, "Yaw": -8}, 0.5),
        ("arms", (30, 45), 0.1),
        ("head", {"Roll": 6}, 0.5),
        ("arms", (ARMS_DOWN, ARMS_DOWN), 0.1),
        ("head", {"Pitch": REST_PITCH}, 0.3),
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


def static_eyes_image(width: int = 480, height: int = 272) -> bytes:
    """Plain machine-like eyes: two flat light-grey bars on black, no iris, no shine."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (width, height), (0, 0, 0))
    d = ImageDraw.Draw(img)
    w, h = width * 0.22, height * 0.12
    for cx in (width * 0.3, width * 0.7):
        d.rounded_rectangle(
            (cx - w / 2, height * 0.45 - h / 2, cx + w / 2, height * 0.45 + h / 2),
            radius=int(h / 3),
            fill=(200, 205, 210),
        )
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=92)
    return buf.getvalue()


def redden(jpeg: bytes) -> bytes:
    """Recolour the coloured parts of an eye image (the iris) to red."""
    import numpy as np
    from PIL import Image

    img = Image.open(io.BytesIO(jpeg)).convert("RGB")
    hsv = np.array(img.convert("HSV"))
    mask = hsv[..., 1] > 60
    hsv[..., 0][mask] = 0
    hsv[..., 1][mask] = np.maximum(hsv[..., 1][mask], 200)
    out = Image.fromarray(hsv, "HSV").convert("RGB")
    buf = io.BytesIO()
    out.save(buf, "JPEG", quality=92)
    return buf.getvalue()


class MistyRobot:
    """Turns our robot commands into Misty REST calls. Failures are logged, never raised."""

    def __init__(self, address: str, on_speech_done: SpeechDone | None = None, http=None):
        self.address = address.removeprefix("http://").rstrip("/")
        self.base = f"http://{self.address}"
        self.on_speech_done = on_speech_done
        self.http = http or httpx.AsyncClient(timeout=5.0)
        self.red_ready = False
        self.static_ready = False
        self._blinking: bool | None = None
        self._gesture: asyncio.Task | None = None
        self._events: asyncio.Task | None = None
        self._mood: str | None = None
        self._led = "#00BFFF"
        self._camera_lock = asyncio.Lock()

    # ---- connection & setup ------------------------------------------------
    async def reachable(self) -> bool:
        try:
            res = await self.http.get(f"{self.base}/api/device")
            return res.status_code == 200
        except httpx.HTTPError:
            return False

    async def prepare_red_eyes(self) -> bool:
        """Create red versions of the eye images on Misty (once per robot; overwrites)."""
        try:
            for name in sorted(set(EYES.values())):
                res = await self.http.get(
                    f"{self.base}/api/images", params={"FileName": name, "Base64": "true"}
                )
                info = res.json()["result"]
                original = base64.b64decode(info["base64"])
                red = await asyncio.to_thread(redden, original)
                up = await self.http.post(
                    f"{self.base}/api/images",
                    json={
                        "FileName": RED_PREFIX + name,
                        "Data": base64.b64encode(red).decode(),
                        "Width": int(info.get("width", 480)),
                        "Height": int(info.get("height", 272)),
                        "ImmediatelyApply": False,
                        "OverwriteExisting": True,
                    },
                    timeout=20,
                )
                up.raise_for_status()
            self.red_ready = True
            log.info("Misty red eye images ready")
        except Exception as e:
            log.warning("could not create red eye images (%s); using LED only", e)
        try:
            up = await self.http.post(
                f"{self.base}/api/images",
                json={
                    "FileName": STATIC_EYES,
                    "Data": base64.b64encode(static_eyes_image()).decode(),
                    "Width": 480,
                    "Height": 272,
                    "ImmediatelyApply": False,
                    "OverwriteExisting": True,
                },
                timeout=20,
            )
            up.raise_for_status()
            self.static_ready = True
        except Exception as e:
            log.warning("could not create static eye image (%s); using the default eyes", e)
        return self.red_ready

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

    # ---- camera --------------------------------------------------------------
    async def picture(self) -> bytes | None:
        """One JPEG frame from Misty's camera (about 0.3 s), or None."""
        async with self._camera_lock:  # one capture at a time
            try:
                res = await self.http.get(
                    f"{self.base}/api/cameras/rgb",
                    params={
                        "Base64": "false",
                        "Width": 640,
                        "Height": 480,
                        "DisplayOnScreen": "false",
                        "OverwriteExisting": "true",
                    },
                )
            except httpx.HTTPError:
                return None
        if res.status_code == 200 and res.headers.get("content-type", "").startswith("image"):
            return res.content
        return None

    # ---- commands ----------------------------------------------------------
    async def handle(self, cmd: dict) -> None:
        kind = cmd.get("cmd")
        if kind == "say":
            await self.say(cmd.get("text", ""))
        elif kind == "face":
            await self.face(cmd.get("mood", "neutral"), cmd.get("tint"))
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

    async def face(self, mood: str, tint: str | None = None) -> None:
        if mood == "static":  # professional mode: fixed machine eyes, no blinking
            image = STATIC_EYES if self.static_ready else EYES["neutral"]
        else:
            image = EYES.get(mood, EYES["neutral"])
            if tint == "red" and self.red_ready:
                image = RED_PREFIX + image
        await self._set_blinking(mood != "static")
        await self._post("/api/images/display", {"FileName": image, "Alpha": 1})
        await self._set_led("#FF0000" if tint == "red" else self._led)
        if mood != self._mood:  # body pose only when the emotion changes
            self._mood = mood
            pose = MOOD_POSE.get(mood)
            if pose and not (self._gesture and not self._gesture.done()):
                await self._head(pose.get("head", {}))
                if "arms" in pose:
                    await self._arms(*pose["arms"])

    async def _set_blinking(self, on: bool) -> None:
        if on != self._blinking:
            self._blinking = on
            await self._post("/api/blink", {"Blink": on})

    async def led(self, color: str) -> None:
        self._led = color
        await self._set_led(color)

    async def _set_led(self, color: str) -> None:
        rgb = hex_to_rgb(color)
        if rgb:
            r, g, b = rgb
            await self._post("/api/led", {"red": r, "green": g, "blue": b})

    async def _head(self, values: dict) -> None:
        body = {"Pitch": REST_PITCH, "Roll": 0, "Yaw": 0, **values}
        await self._post("/api/head", {**body, "Velocity": HEAD_VELOCITY, "Units": "degrees"})

    async def _arms(self, left: float, right: float) -> None:
        await self._post(
            "/api/arms/set",
            {
                "LeftArmPosition": left,
                "RightArmPosition": right,
                "LeftArmVelocity": ARM_VELOCITY,
                "RightArmVelocity": ARM_VELOCITY,
                "Units": "degrees",
            },
        )

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
                    await self._head(values)
                else:
                    await self._arms(*values)
                await asyncio.sleep(wait)
