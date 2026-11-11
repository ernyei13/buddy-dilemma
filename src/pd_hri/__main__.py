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
    p.add_argument("--robot", choices=["mock", "buddy", "misty"], default="mock")
    p.add_argument("--misty-ip", default="", help="Misty II IP address (with --robot misty)")
    p.add_argument(
        "--camera",
        choices=["laptop", "robot"],
        default=None,
        help="camera for facial expressions (default: robot for Misty, else laptop)",
    )
    p.add_argument("--rounds", type=int, default=Config.rounds)
    p.add_argument("--first-chat", type=float, default=Config.first_chat_s, help="round 1 chat s")
    p.add_argument("--chat", type=float, default=Config.chat_s, help="later rounds chat s")
    p.add_argument("--vote", type=float, default=Config.vote_s, help="vote seconds")
    p.add_argument("--port", type=int, default=Config.port)
    p.add_argument(
        "--fast", action="store_true", help="short timings for testing (20 s / 12 s chats)"
    )
    p.add_argument("--no-llm", action="store_true", help="scripted lines only, no Ollama")
    p.add_argument("--llm-model", default=Config.llm_model, help="Ollama model name")
    p.add_argument("--stt-model", default=Config.stt_model, help="faster-whisper model size")
    args = p.parse_args()

    cfg = Config(
        robot=args.robot,
        misty_ip=args.misty_ip,
        camera=args.camera or ("robot" if args.robot == "misty" else "laptop"),
        rounds=args.rounds,
        first_chat_s=args.first_chat,
        chat_s=args.chat,
        vote_s=args.vote,
        port=args.port,
        use_llm=not args.no_llm,
        llm_model=args.llm_model,
        stt_model=args.stt_model,
    )
    if args.fast:
        cfg.first_chat_s, cfg.chat_s, cfg.vote_s, cfg.result_s = 20.0, 12.0, 6.0, 4.0

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ip = _lan_ip()
    if cfg.robot == "misty" and not cfg.misty_ip:
        p.error("--robot misty needs --misty-ip, e.g. --misty-ip 192.168.1.50")
    print(f"\n  Screen:        http://localhost:{cfg.port}")
    if cfg.robot == "misty":
        print(f"  Robot:         Misty II at http://{cfg.misty_ip}\n")
    else:
        print(f"  Robot adapter: ws://{ip}:{cfg.port}/ws/robot   (robot backend: {cfg.robot})\n")
    uvicorn.run(create_app(cfg), host=cfg.host, port=cfg.port, log_level="warning")


if __name__ == "__main__":
    main()
