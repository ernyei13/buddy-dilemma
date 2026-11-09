"""Pretend to be the Buddy adapter: connect to /ws/robot and print every command.

Usage: uv run python tools/fake_robot.py [ws://localhost:8000/ws/robot]
"""

import asyncio
import json
import sys

import websockets


async def main(url: str) -> None:
    async with websockets.connect(url) as ws:
        await ws.send(json.dumps({"type": "hello", "name": "fake_robot"}))
        print(f"connected to {url}, waiting for commands (Ctrl+C to quit)")
        async for raw in ws:
            msg = json.loads(raw)
            detail = {k: v for k, v in msg.items() if k != "cmd"}
            print(f"{msg.get('cmd', '?'):8} {detail}")


if __name__ == "__main__":
    try:
        asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "ws://localhost:8000/ws/robot"))
    except KeyboardInterrupt:
        pass
