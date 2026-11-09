"""Run the study app:  uv run pd-hri [--robot buddy] [--fast]"""

from __future__ import annotations

import argparse
import logging
import socket

import uvicorn

from .config import Config
from .server import create_app


def _lan_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))  # no packets are sent
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def main() -> None:
    p = argparse.ArgumentParser(description="Prisoner's Dilemma HRI study")
    p.add_argument("--robot", choices=["mock", "buddy"], default="mock")
    p.add_argument("--rounds", type=int, default=Config.rounds)
    p.add_argument("--chat", type=float, default=Config.chat_s, help="chat seconds")
    p.add_argument("--vote", type=float, default=Config.vote_s, help="vote seconds")
    p.add_argument("--port", type=int, default=Config.port)
    p.add_argument("--fast", action="store_true", help="short timings for testing (12 s chat)")
    args = p.parse_args()

    cfg = Config(
        robot=args.robot, rounds=args.rounds, chat_s=args.chat, vote_s=args.vote, port=args.port
    )
    if args.fast:
        cfg.chat_s, cfg.vote_s, cfg.result_s, cfg.chat_beats = 12.0, 6.0, 4.0, (0.0, 4.0, 8.0)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ip = _lan_ip()
    print(f"\n  Screen:        http://localhost:{cfg.port}")
    print(f"  Robot adapter: ws://{ip}:{cfg.port}/ws/robot   (robot backend: {cfg.robot})\n")
    uvicorn.run(create_app(cfg), host=cfg.host, port=cfg.port, log_level="warning")


if __name__ == "__main__":
    main()
