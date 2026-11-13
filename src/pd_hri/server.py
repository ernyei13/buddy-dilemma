"""FastAPI app: serves the screen, and hosts two WebSocket endpoints.

/ws/screen  browser screen(s): start panel, timers, voting, webcam expressions, mic audio
/ws/robot   robot adapter(s), e.g. the Buddy app (see docs/protocol.md)

Everything runs locally: speech recognition (faster-whisper) and the LLM (Ollama).
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import dataclasses
import logging
import time
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

from .config import Config
from .expression import LABELS, NO_FACE, ExpressionTracker, classify
from .game import Mode, parse_rounds
from .llm import Brain, ollama_status
from .robot import MockRobot, RemoteRobot
from .robot.misty import MistyRobot
from .session import Session, speech_seconds
from .stt import Transcriber

log = logging.getLogger(__name__)
WEB_DIR = Path(__file__).parent / "web"


class Hub:
    def __init__(self):
        self.screens: set[WebSocket] = set()
        self.robots: set[WebSocket] = set()

    @staticmethod
    async def _send_all(sockets: set[WebSocket], msg: dict) -> None:
        for ws in list(sockets):
            try:
                await ws.send_json(msg)
            except Exception:
                sockets.discard(ws)

    async def to_screens(self, msg: dict) -> None:
        await self._send_all(self.screens, msg)

    async def to_robots(self, msg: dict) -> None:
        await self._send_all(self.robots, msg)


def create_app(cfg: Config | None = None) -> FastAPI:
    cfg = cfg or Config()
    app = FastAPI(title="PD-HRI")
    hub = Hub()
    state: dict = {
        "session": None,
        "armed": None,
        "task": None,
        "tracker": ExpressionTracker(cfg.expression_window_s),
        "llm": "off" if not cfg.use_llm else "checking",
    }
    transcriber = Transcriber(cfg.stt_model)
    state["misty_ok"] = False

    async def robot_speech_done() -> None:
        if state["session"]:
            state["session"].speech_done()  # lets the robot finish its sentence before the vote
        await hub.to_screens({"type": "robot_speech_done"})  # unmute the mic now

    misty_speech_done = robot_speech_done

    misty = MistyRobot(cfg.misty_ip, misty_speech_done) if cfg.robot == "misty" else None
    background: set[asyncio.Task] = set()

    def spawn(coro) -> None:
        task = asyncio.create_task(coro)
        background.add(task)
        task.add_done_callback(background.discard)

    @contextlib.asynccontextmanager
    async def lifespan(_app):
        await warm_up()
        yield

    app.router.lifespan_context = lifespan

    async def warm_up() -> None:
        async def load_stt():
            await asyncio.to_thread(transcriber.load)
            await hub.to_screens(status())

        async def check_llm():
            state["llm"] = await ollama_status(cfg.ollama_url, cfg.llm_model)
            if state["llm"] == "ready":
                brain = Brain(Mode.FRIENDLY, cfg.llm_model, cfg.ollama_url)
                try:
                    await brain.warm_up()
                finally:
                    await brain.aclose()
            await hub.to_screens(status())

        async def watch_misty():  # show on the start screen whether Misty answers
            misty.start_events()
            while True:
                ok = await misty.reachable()
                if ok != state["misty_ok"]:
                    state["misty_ok"] = ok
                    await hub.to_screens(status())
                if ok and not misty.red_ready and not state.get("red_tried"):
                    state["red_tried"] = True
                    await misty.prepare_red_eyes()
                await asyncio.sleep(5)

        spawn(load_stt())
        if cfg.use_llm:
            spawn(check_llm())
        if misty:
            spawn(watch_misty())

    async def robot_send(cmd: dict) -> None:
        # Screens always get the command (subtitles / mock avatar); the robot gets it too.
        extra = {"est_s": round(speech_seconds(cmd["text"]), 1)} if cmd["cmd"] == "say" else {}
        await hub.to_screens({"type": "robot", **cmd, **extra})
        if cfg.robot == "buddy":
            await hub.to_robots(cmd)
        elif misty:
            await misty.handle(cmd)

    def make_robot():
        if cfg.robot in ("buddy", "misty"):
            return RemoteRobot(robot_send)
        return MockRobot(robot_send)

    def status() -> dict:
        return {
            "type": "status",
            "robot": cfg.robot,
            "robots_connected": int(state["misty_ok"]) if misty else len(hub.robots),
            "misty_ip": cfg.misty_ip,
            "robot_name": cfg.robot_name,
            "armed": state["armed"] is not None,
            "running": state["task"] is not None and not state["task"].done(),
            "modes": [m.value for m in Mode],
            "config": {
                "rounds": cfg.rounds,
                "first_chat_s": cfg.first_chat_s,
                "chat_s": cfg.chat_s,
                "vote_s": cfg.vote_s,
                "lie_rounds": ",".join(str(r) for r in cfg.lie_rounds),
            },
            "camera": cfg.camera,
            "llm": state["llm"],
            "llm_model": cfg.llm_model,
            "stt": "ready" if transcriber.ready else ("error" if transcriber.error else "loading"),
        }

    def session_config(settings: dict) -> Config:
        """Per-session copy of the config with the start-screen settings applied."""

        def num(key, default, lo, hi):
            try:
                return min(hi, max(lo, float(settings.get(key, default))))
            except (TypeError, ValueError):
                return default

        rounds = int(num("rounds", cfg.rounds, 1, 30))
        lies = settings.get("lie_rounds")
        return dataclasses.replace(
            cfg,
            rounds=rounds,
            first_chat_s=num("first_chat_s", cfg.first_chat_s, 5, 600),
            chat_s=num("chat_s", cfg.chat_s, 5, 600),
            vote_s=num("vote_s", cfg.vote_s, 3, 120),
            lie_rounds=parse_rounds(lies, rounds) if lies is not None else cfg.lie_rounds,
        )

    async def start_session(mode: str, participant: str, settings: dict | None = None) -> None:
        if status()["running"]:
            return
        mode = mode if mode in [m.value for m in Mode] else Mode.FRIENDLY.value
        scfg = session_config(settings or {})
        tracker = ExpressionTracker(cfg.expression_window_s)
        state["tracker"] = tracker
        brain = (
            Brain(Mode(mode), cfg.llm_model, cfg.ollama_url, cfg.robot_name)
            if state["llm"] == "ready"
            else None
        )
        session = Session(
            scfg, Mode(mode), participant or "anon", make_robot(), hub.to_screens, tracker, brain
        )
        # Misty and Buddy report when they finish speaking; the browser mock avatar does not.
        session.speech_events = cfg.robot in ("misty", "buddy")
        state["session"] = session

        async def runner():
            try:
                await session.run()
            except asyncio.CancelledError:
                await hub.to_screens({"type": "state", "phase": "aborted"})
                raise
            except Exception:
                log.exception("session crashed")
                await hub.to_screens({"type": "state", "phase": "aborted"})
            finally:
                await hub.to_screens(status() | {"running": False})

        state["task"] = asyncio.create_task(runner())
        await hub.to_screens(status())

    async def handle_speech(audio: str = "", text: str = "") -> None:
        session = state["session"]
        if not session or not session.accepting_speech:
            return
        if audio:
            text = await transcriber.transcribe(base64.b64decode(audio))
        if text.strip() and session.add_speech(text):
            await hub.to_screens({"type": "transcript", "who": "human", "text": text.strip()})

    # Versioned path for the screen files: a new URL on every start, so browsers never run a
    # stale cached app.js after an update.
    version = str(int(time.time()))

    @app.get("/")
    async def index():
        html = (WEB_DIR / "index.html").read_text(encoding="utf-8")
        return HTMLResponse(html.replace("/static/", f"/v/{version}/"))

    @app.get("/api/robot-camera")
    async def robot_camera():
        """Latest frame from the robot's camera (Misty), for expression tracking."""
        frame = await misty.picture() if misty else None
        if frame is None:
            return Response(status_code=503)
        return Response(frame, media_type="image/jpeg", headers={"Cache-Control": "no-store"})

    @app.get("/api/status")
    async def api_status():
        return status()

    @app.middleware("http")
    async def no_cache(request, call_next):
        # Always serve the latest screen code (avoids stale cached app.js after updates).
        response = await call_next(request)
        if request.url.path == "/" or request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-cache"
        return response

    app.mount(f"/v/{version}", StaticFiles(directory=WEB_DIR), name="versioned")
    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

    @app.websocket("/ws/screen")
    async def ws_screen(ws: WebSocket):
        await ws.accept()
        hub.screens.add(ws)
        await ws.send_json(status())
        try:
            while True:
                msg = await ws.receive_json()
                kind = msg.get("type")
                if kind in ("arm", "start") and not status()["running"] and state["armed"] is None:
                    state["armed"] = (ws, msg)
                    await hub.to_screens(status())
                elif kind == "vote" and state["session"]:
                    if state["session"].submit_vote(msg.get("choice")):
                        await hub.to_screens({"type": "vote_ack", "choice": msg["choice"]})
                elif kind == "expression":
                    label = msg.get("label")
                    if label not in (*LABELS, NO_FACE):
                        label = classify(msg.get("scores") or {})
                    state["tracker"].add(label)
                    await ws.send_json({"type": "expression", "label": label})
                    armed = state["armed"]
                    if armed and armed[0] is ws:
                        if msg.get("scores"):  # armed: start the moment a face is seen
                            setup = armed[1]
                            state["armed"] = None
                            await start_session(
                                setup.get("mode", "friendly"),
                                str(setup.get("participant", "")),
                                setup.get("settings"),
                            )
                elif kind == "audio":
                    spawn(handle_speech(audio=msg.get("pcm16", "")))
                elif kind == "text":
                    spawn(handle_speech(text=str(msg.get("text", ""))))
                elif kind == "abort" and state["task"]:
                    state["task"].cancel()
        except WebSocketDisconnect:
            pass
        finally:
            hub.screens.discard(ws)
            if state["armed"] and state["armed"][0] is ws:
                state["armed"] = None
                await hub.to_screens(status())

    @app.websocket("/ws/robot")
    async def ws_robot(ws: WebSocket):
        await ws.accept()
        hub.robots.add(ws)
        log.info("robot adapter connected (%d total)", len(hub.robots))
        await hub.to_screens(status())
        try:
            while True:
                msg = await ws.receive_json()  # {"type": "hello" | "log" | "speech_done"}
                if msg.get("type") == "speech_done":
                    await robot_speech_done()
                else:
                    log.info("robot says: %s", msg)
        except WebSocketDisconnect:
            pass
        finally:
            hub.robots.discard(ws)
            with contextlib.suppress(Exception):
                await hub.to_screens(status())

    return app
