"""The only robot API the game uses. Every backend implements these four commands.

See docs/protocol.md for the JSON form sent to remote robots (Buddy).
"""

from __future__ import annotations

from abc import ABC, abstractmethod

FACES = ("neutral", "happy", "sad", "angry", "surprised", "thinking", "listening")
GESTURES = ("nod", "shake", "tilt", "look_down", "celebrate")


class Robot(ABC):
    @abstractmethod
    async def say(self, text: str) -> None:
        """Start speaking (non-blocking: do not wait for speech to finish)."""

    @abstractmethod
    async def face(self, mood: str) -> None:
        """Show a facial expression, one of FACES."""

    @abstractmethod
    async def gesture(self, name: str) -> None:
        """Play a short body/head movement, one of GESTURES."""

    @abstractmethod
    async def led(self, color: str) -> None:
        """Set body LED colour (CSS colour name or #rrggbb)."""

    async def perform(self, line) -> None:
        """Convenience: face + gesture + speech for a dialogue Line."""
        await self.face(line.face)
        if line.gesture:
            await self.gesture(line.gesture)
        await self.say(line.text)
