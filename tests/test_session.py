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

    async def face(self, mood, tint=None):
        self.calls.append(("face", mood, tint))

    async def gesture(self, name):
        self.calls.append(("gesture", name))

    async def led(self, color):
        self.calls.append(("led", color))


def fast_config(tmp_path, rounds=3, **kw):
    return Config(
        rounds=rounds,
        first_chat_s=0.05,
        chat_s=0.05,
        vote_s=0.2,
        result_s=0.01,
        chat_beats=(0.0, 0.02),
        min_turn_s=0.0,
        data_dir=tmp_path,
        **kw,
    )


def run_session(tmp_path, mode, human_votes, **cfg_kw):
    from pd_hri.session import Session

    cfg = fast_config(tmp_path, rounds=len(human_votes), **cfg_kw)
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


def test_full_game_strategy_lies_and_log(tmp_path):
    human = [C, C, D, C, C, D, C, None]
    session, robot, states, rows = run_session(tmp_path, Mode.FRIENDLY, human)
    assert len(rows) == 8
    # C D C C, then copycat of the human's previous vote
    assert [r["robot_vote"] for r in rows] == [C, D, C, C, C, C, D, C]
    # exactly 3 lies, in rounds 2, 5, 7: the claim is the opposite of the real vote
    assert [r["lied"] for r in rows] == ["0", "1", "0", "0", "1", "0", "1", "0"]
    assert rows[1]["robot_claim"] == C and rows[1]["robot_vote"] == D
    assert states[-1]["phase"] == "end"


def test_red_eyes_while_lying_and_when_defecting(tmp_path):
    _, robot, _, _ = run_session(tmp_path, Mode.FRIENDLY, [C, C])
    faces = [c for c in robot.calls if c[0] == "face"]
    # round 2 is a lie round and the robot defects: red eyes in that chat and at its reveal
    assert any(t == "red" for _, _, t in faces)
    # round 1 (truthful, cooperates) starts with normal eyes
    assert faces[0][2] is None


def test_first_round_chat_is_longer(tmp_path):
    from pd_hri.session import Session

    cfg = fast_config(tmp_path, rounds=2)
    cfg.first_chat_s, cfg.chat_s = 0.3, 0.05
    durations = []

    async def broadcast(msg):
        if msg.get("phase") == "chat":
            durations.append(msg["duration"])

    async def main():
        s = Session(cfg, Mode.NEUTRAL, "P", RecordingRobot(), broadcast, ExpressionTracker())
        await s.run()

    asyncio.run(main())
    assert durations == [0.3, 0.05]


def test_neutral_mode_has_no_emotions_or_gestures(tmp_path):
    _, robot, _, _ = run_session(tmp_path, Mode.NEUTRAL, [C, D])
    assert all(c[1] == "neutral" for c in robot.calls if c[0] == "face")
    assert not [c for c in robot.calls if c[0] == "gesture"]


class FakeBrain:
    def __init__(self):
        self.contexts, self.heard, self.noted = [], [], []

    def note_robot_line(self, text):
        self.noted.append(text)

    async def reply(self, context, human_text):
        from pd_hri.dialogue import Line

        self.contexts.append(context)
        self.heard.append(human_text)
        return Line(f"reply to {human_text}", "happy", "nod")


def test_interactive_chat_replies_to_speech(tmp_path, monkeypatch):
    monkeypatch.setattr("pd_hri.session.speech_seconds", lambda _: 0.01)
    from pd_hri.session import Session

    cfg = Config(
        rounds=1,
        first_chat_s=0.6,
        vote_s=0.05,
        result_s=0.01,
        silence_nudge_s=10.0,
        min_turn_s=0.1,
        data_dir=tmp_path,
        robot="misty",
    )
    brain = FakeBrain()
    holder = {}

    async def broadcast(msg):
        if msg.get("phase") == "chat":
            loop = asyncio.get_running_loop()
            loop.call_later(0.05, holder["s"].add_speech, "will you cooperate?")

    async def main():
        tracker = ExpressionTracker()
        tracker.add("doubtful")
        s = Session(cfg, Mode.FRIENDLY, "P", RecordingRobot(), broadcast, tracker, brain)
        holder["s"] = s
        await s.run()
        return s

    s = asyncio.run(main())
    rows = list(csv.DictReader(s.logger.path.open()))
    assert brain.heard == ["will you cooperate?"]
    assert "Truth: you WILL COOPERATE" in brain.contexts[0]
    assert "facial expression right now: doubtful" in brain.contexts[0]
    assert "Human: will you cooperate?" in rows[0]["dialogue"]
    assert "Misty: reply to will you cooperate?" in rows[0]["dialogue"]
    assert s.add_speech("too late") is False  # speech is ignored outside the chat


def test_votes_rejected_outside_vote_phase(tmp_path):
    from pd_hri.session import Session

    async def noop(_):
        pass

    async def main():
        s = Session(
            fast_config(tmp_path), Mode.FRIENDLY, "P", RecordingRobot(), noop, ExpressionTracker()
        )
        ok = s.submit_vote(C)
        s.logger.close()
        return ok

    assert asyncio.run(main()) is False


def test_stalled_reply_is_cancelled_before_vote(tmp_path, monkeypatch):
    from pd_hri.session import Session

    monkeypatch.setattr("pd_hri.session.speech_seconds", lambda _: 0.025)
    for mode in (Mode.NEUTRAL, Mode.FRIENDLY):

        class StalledBrain(FakeBrain):
            cancelled = False

            async def reply(self, context, human_text):
                try:
                    await asyncio.Event().wait()
                finally:
                    self.cancelled = True

        async def main(mode=mode):
            cfg = fast_config(tmp_path, rounds=1)
            cfg.first_chat_s = 0.45
            cfg.silence_nudge_s = 0
            cfg.min_turn_s = 0.05
            brain, robot = StalledBrain(), RecordingRobot()
            phases = {}

            async def broadcast(msg):
                phases[msg["phase"]] = asyncio.get_running_loop().time()

            s = Session(cfg, mode, "P", robot, broadcast, ExpressionTracker(), brain)
            await asyncio.wait_for(s.run(), timeout=2)
            assert brain.cancelled and brain.noted
            assert phases["vote"] - phases["chat"] < 0.8
            if mode is Mode.NEUTRAL:
                assert ("say", "One moment.") in robot.calls
            else:
                assert ("face", "thinking", None) in robot.calls

        asyncio.run(main())
