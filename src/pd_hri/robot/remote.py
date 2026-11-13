"""Robots driven over WebSocket with JSON commands.

Both backends just emit {"cmd": ..., ...} messages through a send callback:

- MockRobot: sent to the browser screen, which draws an avatar and speaks with
  the browser's text-to-speech.
- RemoteRobot ("buddy"): sent to every robot adapter connected to /ws/robot.
  The Buddy app connects to the laptop as a WebSocket *client*, so Buddy needs
  no server of its own, only the laptop's IP.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from .base import Robot

log = logging.getLogger(__name__)

Send = Callable[[dict], Awaitable[None]]


class CommandRobot(Robot):
    def __init__(self, send: Send):
        self._send = send

    async def _cmd(self, cmd: str, **kw) -> None:
        try:
            await self._send({"cmd": cmd, **kw})
        except Exception:  # never let a robot hiccup crash a study session
            log.exception("robot command failed: %s", cmd)

    async def say(self, text: str) -> None:
        await self._cmd("say", text=text)

    async def face(self, mood: str, tint: str | None = None) -> None:
        if tint:
            await self._cmd("face", mood=mood, tint=tint)
        else:
            await self._cmd("face", mood=mood)

    async def gesture(self, name: str) -> None:
        await self._cmd("gesture", name=name)

    async def led(self, color: str) -> None:
        await self._cmd("led", color=color)

    async def perform(self, line, tint: str | None = None) -> None:
        """Like Robot.perform, but tells the screen whether the line was scripted or LLM."""
        await self.face(line.face, tint)
        if line.gesture:
            await self.gesture(line.gesture)
        await self._cmd("say", text=line.text, source=getattr(line, "source", "script"))


class MockRobot(CommandRobot):
    """Avatar + TTS rendered by the browser screen."""


class RemoteRobot(CommandRobot):
    """A physical robot (Buddy) running the adapter app from buddy_adapter/."""
