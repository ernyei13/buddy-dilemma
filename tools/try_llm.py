"""Chat with Buddy's LLM brain in the terminal, to tune the prompts in src/pd_hri/llm.py.

Usage:
  uv run python tools/try_llm.py --mode liar --vote D --face doubtful
  uv run python tools/try_llm.py --mode honest --demo     # scripted questions, prints latency
"""

import argparse
import asyncio
import time

from pd_hri.config import Config
from pd_hri.game import Mode
from pd_hri.llm import Brain, vote_rule

DEMO = [
    None,
    "Hi Buddy! So what are you going to vote?",
    "Can I really trust you?",
    "Be honest, are you going to defect?",
]


async def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=[m.value for m in Mode], default="honest")
    p.add_argument("--vote", choices=["C", "D"], default="C", help="Buddy's real vote")
    p.add_argument("--face", default="neutral", help="happy | neutral | doubtful | surprised")
    p.add_argument("--model", default=Config.llm_model)
    p.add_argument("--demo", action="store_true")
    args = p.parse_args()

    brain = Brain(Mode(args.mode), args.model)
    vote = "COOPERATE" if args.vote == "C" else "DEFECT"
    print(f"mode={args.mode} real vote={vote} face={args.face} model={args.model}")
    print("warming up…", "ok" if await brain.warm_up() else "Ollama not reachable")

    async def turn(text):
        # History consistent with the strategy: honest/neutral only defect after the human did.
        human_r1 = "DEFECT" if args.vote == "D" and args.mode != "liar" else "COOPERATE"
        pts = "you 0, human 5" if human_r1 == "DEFECT" else "you 3, human 3"
        ctx = (
            f"Round 2/5. 20 seconds left to talk. Your real vote this round: {vote}. "
            f"{vote_rule(Mode(args.mode), args.vote)} "
            f"History: R1: you COOPERATE, human {human_r1}. Score: {pts}."
        )
        if Mode(args.mode).adaptive:
            ctx += f" The person's facial expression right now: {args.face}."
        t = time.perf_counter()
        line = await brain.reply(ctx, text)
        dt = time.perf_counter() - t
        print(f"  human: {text or '(silent)'}")
        if line:
            print(f"  buddy: {line.text}  [{line.face}, {line.gesture}]  ({dt:.1f}s)")
        else:
            print(f"  buddy: <no reply> ({dt:.1f}s)")

    if args.demo:
        for text in DEMO:
            await turn(text)
    else:
        print("Type what the person says (empty line = silence, Ctrl+C to quit).")
        while True:
            await turn(input("> ").strip() or None)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, EOFError):
        pass
