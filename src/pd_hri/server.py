"""FastAPI app: serves the screen, and hosts two WebSocket endpoints.

/ws/screen  browser screen(s): start panel, timers, voting, webcam expressions, mic audio
/ws/robot   robot adapter(s), e.g. the Buddy app (see docs/protocol.md)

Everything runs locally: speech recognition (faster-whisper) and the LLM (Ollama).
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import logging
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import Config
from .expression import LABELS, NO_FACE, ExpressionTracker, classify
from .game import Mode
from .llm import Brain, ollama_status
from .robot import MockRobot, RemoteRobot
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
        "task": None,
        "tracker": ExpressionTracker(cfg.expression_window_s),
        "llm": "off" if not cfg.use_llm else "checking",
    }
    transcriber = Transcriber(cfg.stt_model)
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
                await Brain(Mode.HONEST, cfg.llm_model, cfg.ollama_url).warm_up()
            await hub.to_screens(status())

        spawn(load_stt())
        if cfg.use_llm:
            spawn(check_llm())

    async def robot_send(cmd: dict) -> None:
        # Screens always get the command (subtitles / mock avatar); robots only in buddy mode.
        extra = {"est_s": round(speech_seconds(cmd["text"]), 1)} if cmd["cmd"] == "say" else {}
        await hub.to_screens({"type": "robot", **cmd, **extra})
        if cfg.robot == "buddy":
            await hub.to_robots(cmd)

    def make_robot():
        return RemoteRobot(robot_send) if cfg.robot == "buddy" else MockRobot(robot_send)

    def status() -> dict:
        return {
            "type": "status",
            "robot": cfg.robot,
            "robots_connected": len(hub.robots),
            "running": state["task"] is not None and not state["task"].done(),
            "modes": [m.value for m in Mode],
            "config": {"rounds": cfg.rounds, "chat_s": cfg.chat_s, "vote_s": cfg.vote_s},
            "llm": state["llm"],
            "llm_model": cfg.llm_model,
            "stt": "ready" if transcriber.ready else ("error" if transcriber.error else "loading"),
        }

    async def start_session(mode: str, participant: str) -> None:
        if status()["running"]:
            return
        tracker = ExpressionTracker(cfg.expression_window_s)
        state["tracker"] = tracker
        brain = (
            Brain(Mode(mode), cfg.llm_model, cfg.ollama_url) if state["llm"] == "ready" else None
        )
        session = Session(
            cfg, Mode(mode), participant or "anon", make_robot(), hub.to_screens, tracker, brain
        )
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

    @app.get("/")
    async def index():
        return FileResponse(WEB_DIR / "index.html")

    @app.get("/api/status")
    async def api_status():
        return status()

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
                if kind == "start":
                    await start_session(msg.get("mode", "honest"), str(msg.get("participant", "")))
                elif kind == "vote" and state["session"]:
                    if state["session"].submit_vote(msg.get("choice")):
                        await hub.to_screens({"type": "vote_ack", "choice": msg["choice"]})
                elif kind == "expression":
                    label = msg.get("label")
                    if label not in (*LABELS, NO_FACE):
                        label = classify(msg.get("scores") or {})
                    state["tracker"].add(label)
                    await ws.send_json({"type": "expression", "label": label})
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
                    await hub.to_screens({"type": "robot_speech_done"})  # unmute the mic now
                else:
                    log.info("robot says: %s", msg)
        except WebSocketDisconnect:
            pass
        finally:
            hub.robots.discard(ws)
            with contextlib.suppress(Exception):
                await hub.to_screens(status())

    return app
