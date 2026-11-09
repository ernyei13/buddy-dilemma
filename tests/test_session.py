import asyncio
import csv
import random

from pd_hri.config import Config
from pd_hri.expression import ExpressionTracker
from pd_hri.game import C, D, Mode
from pd_hri.robot import Robot


class RecordingRobot(Robot):
    def __init__(self):
        self.calls = []

    async def say(self, text):
        self.calls.append(("say", text))

    async def face(self, mood):
        self.calls.append(("face", mood))

    async def gesture(self, name):
        self.calls.append(("gesture", name))

    async def led(self, color):
        self.calls.append(("led", color))


def fast_config(tmp_path, rounds=3):
    return Config(
        rounds=rounds,
        chat_s=0.05,
        vote_s=0.2,
        result_s=0.01,
        chat_beats=(0.0, 0.02),
        data_dir=tmp_path,
    )


def run_session(tmp_path, mode, human_votes):
    from pd_hri.session import Session

    cfg = fast_config(tmp_path, rounds=len(human_votes))
    robot = RecordingRobot()
    states = []
    votes = iter(human_votes)
    holder = {}

    async def broadcast(msg):
        states.append(msg)
        if msg.get("phase") == "vote":
            v = next(votes)
            if v:
                asyncio.get_running_loop().call_soon(holder["s"].submit_vote, v)

    async def main():
        tracker = ExpressionTracker()
        tracker.add("doubtful")
        s = Session(cfg, mode, "P01", robot, broadcast, tracker, rng=random.Random(0))
        holder["s"] = s
        await s.run()
        return s

    session = asyncio.run(main())
    rows = list(csv.DictReader(session.logger.path.open()))
    return session, robot, states, rows


def test_liar_session_logs_every_round(tmp_path):
    session, robot, states, rows = run_session(tmp_path, Mode.LIAR, [C, C, None])
    assert [r["robot_vote"] for r in rows] == [C, D, C]
    assert [r["human_vote"] for r in rows] == [C, C, "none"]
    assert [r["outcome"] for r in rows] == ["mutual", "exploit", "missed"]
    assert session.totals == {"human": 3, "robot": 8}
    assert states[-1]["phase"] == "end"
    assert any(kind == "say" for kind, _ in robot.calls)


def test_honest_session_retaliates_once(tmp_path):
    _, _, _, rows = run_session(tmp_path, Mode.HONEST, [D, C, C])
    assert [r["robot_vote"] for r in rows] == [C, D, C]


def test_votes_rejected_outside_vote_phase(tmp_path):
    from pd_hri.session import Session

    async def noop(_):
        pass

    async def main():
        s = Session(
            fast_config(tmp_path), Mode.HONEST, "P", RecordingRobot(), noop, ExpressionTracker()
        )
        ok = s.submit_vote(C)
        s.logger.close()
        return ok

    assert asyncio.run(main()) is False
