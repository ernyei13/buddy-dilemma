"""FastAPI app: serves the screen, and hosts two WebSocket endpoints.

/ws/screen  browser screen(s): operator start panel, timers, voting, webcam expressions
/ws/robot   robot adapter(s), e.g. the Buddy app (see docs/protocol.md)
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import Config
from .expression import LABELS, NO_FACE, ExpressionTracker, classify
from .game import Mode
from .robot import MockRobot, RemoteRobot
from .session import Session

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
    }

    async def robot_send(cmd: dict) -> None:
        # Screens always get the command (subtitles / mock avatar); robots only in buddy mode.
        await hub.to_screens({"type": "robot", **cmd})
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
        }

    async def start_session(mode: str, participant: str) -> None:
        if status()["running"]:
            return
        tracker = ExpressionTracker(cfg.expression_window_s)
        state["tracker"] = tracker
        session = Session(
            cfg, Mode(mode), participant or "anon", make_robot(), hub.to_screens, tracker
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
                msg = await ws.receive_json()  # adapters may send {"type": "hello"/"log", ...}
                log.info("robot says: %s", msg)
        except WebSocketDisconnect:
            pass
        finally:
            hub.robots.discard(ws)
            with contextlib.suppress(Exception):
                await hub.to_screens(status())

    return app
