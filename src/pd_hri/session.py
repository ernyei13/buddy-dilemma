"""The interaction state machine: CHAT (30 s) -> VOTE (10 s) -> RESULT, repeated.

Sense:  facial expression (webcam), the person's speech (local Whisper), their vote
Plan:   robot vote from the mode's strategy; reply from the local LLM (or scripted lines)
Act:    Robot.perform() -> face, gesture, speech
"""

from __future__ import annotations

import asyncio
import contextlib
import random
import time
from collections.abc import Awaitable, Callable

from .config import Config
from .dialogue import Dialogue, Line
from .expression import ExpressionTracker
from .game import NONE, C, D, Mode, outcome_key, robot_vote, score
from .logger import RoundLogger
from .robot import Robot

Broadcast = Callable[[dict], Awaitable[None]]

REACTION_DELAY_S = 1.5  # wait after the reveal so the person's reaction shows on their face
VOTE_WORD = {C: "COOPERATE", D: "DEFECT", NONE: "no vote"}


def speech_seconds(text: str) -> float:
    """Rough time the robot needs to say a line (about 2.6 words per second)."""
    return len(text.split()) / 2.6 + 0.5


class Session:
    def __init__(
        self,
        cfg: Config,
        mode: Mode,
        participant: str,
        robot: Robot,
        broadcast: Broadcast,
        tracker: ExpressionTracker,
        brain=None,  # llm.Brain or None for scripted lines only
        rng: random.Random | None = None,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.cfg = cfg
        self.mode = mode
        self.participant = participant
        self.robot = robot
        self.broadcast = broadcast
        self.tracker = tracker
        self.brain = brain
        self.dialogue = Dialogue(mode, rng)
        self.clock = clock
        self.logger = RoundLogger(cfg.data_dir, participant, mode.value)

        self.human_history: list[str] = []
        self.robot_history: list[str] = []
        self.totals = {"human": 0, "robot": 0}
        self._vote_event = asyncio.Event()
        self._human_vote: str | None = None
        self._accepting_votes = False
        self._speech: asyncio.Queue[str] = asyncio.Queue()
        self.accepting_speech = False

    # ---- input from the screen -------------------------------------------
    def submit_vote(self, choice: str) -> bool:
        if not self._accepting_votes or choice not in (C, D) or self._human_vote:
            return False
        self._human_vote = choice
        self._vote_event.set()
        return True

    def add_speech(self, text: str) -> bool:
        """What the person said (from speech recognition or the typed test box)."""
        if not self.accepting_speech or not text.strip():
            return False
        self._speech.put_nowait(text.strip())
        return True

    # ---- helpers ---------------------------------------------------------
    async def _state(self, phase: str, round_no: int, duration: float = 0, **extra) -> None:
        await self.broadcast(
            {
                "type": "state",
                "phase": phase,
                "round": round_no,
                "rounds": self.cfg.rounds,
                "duration": duration,
                "totals": dict(self.totals),
                **extra,
            }
        )

    async def _wait_until(self, t: float) -> None:
        delay = t - self.clock()
        if delay > 0:
            await asyncio.sleep(delay)

    def _context(self, round_no: int, planned: str, seconds_left: float) -> str:
        history = "; ".join(
            f"R{i + 1}: you {VOTE_WORD[r]}, human {VOTE_WORD[h]}"
            for i, (r, h) in enumerate(zip(self.robot_history, self.human_history, strict=True))
        )
        parts = [
            f"Round {round_no}/{self.cfg.rounds}.",
            f"{max(0, round(seconds_left))} seconds left to talk.",
            f"Your real vote this round: {VOTE_WORD[planned]}.",
            f"History: {history}." if history else "First round.",
            f"Score: you {self.totals['robot']}, human {self.totals['human']}.",
        ]
        if self.mode.adaptive:
            parts.append(f"The person's facial expression right now: {self.tracker.current()}.")
        return " ".join(parts)

    # ---- main loop -------------------------------------------------------
    async def run(self) -> None:
        prev_outcome: str | None = None
        try:
            await self.robot.led("deepskyblue")
            for round_no in range(1, self.cfg.rounds + 1):
                prev_outcome = await self._round(round_no, prev_outcome)
            await self._state("end", self.cfg.rounds, session_id=self.logger.session_id)
            await self.robot.perform(self.dialogue.goodbye())
        finally:
            self.accepting_speech = False
            self.logger.close()

    async def _chat(self, round_no: int, planned: str, prev_outcome, dialogue_log) -> None:
        cfg = self.cfg

        async def speak(line: Line) -> float:
            dialogue_log.append(f"Buddy: {line.text}")
            await self.robot.perform(line)
            return self.clock() + speech_seconds(line.text)

        start = self.clock()
        end = start + cfg.chat_s
        # Drop anything heard before the chat started.
        while not self._speech.empty():
            self._speech.get_nowait()
        self.accepting_speech = True

        opening = self.dialogue.opening(prev_outcome, planned)
        if round_no == 1:
            intro = self.dialogue.intro()
            opening = Line(f"{intro.text} {opening.text}", opening.face, opening.gesture)
        robot_done = await speak(opening)
        if self.brain:
            self.brain.note_robot_line(opening.text)

        if not self.brain:  # scripted beats
            for beat in [b for b in cfg.chat_beats if 0 < b < cfg.chat_s]:
                await self._wait_until(start + beat)
                await speak(self.dialogue.persuade(self.tracker.current(), planned))
        else:  # interactive: reply to speech, nudge after silence
            last_activity = robot_done
            while end - self.clock() > cfg.min_turn_s:
                wait = min(
                    end - cfg.min_turn_s - self.clock(),
                    max(0.0, last_activity + cfg.silence_nudge_s - self.clock()),
                )
                heard = None
                with contextlib.suppress(asyncio.TimeoutError):
                    heard = await asyncio.wait_for(self._speech.get(), timeout=max(0.0, wait))
                if heard is not None:
                    while not self._speech.empty():  # merge back-to-back utterances
                        heard += " " + self._speech.get_nowait()
                    dialogue_log.append(f"Human: {heard}")
                elif end - self.clock() <= cfg.min_turn_s:
                    break
                await self.robot.face("thinking")
                line = await self.brain.reply(
                    self._context(round_no, planned, end - self.clock()), heard
                )
                if line is None:
                    line = self.dialogue.persuade(self.tracker.current(), planned)
                    self.brain.note_robot_line(line.text)
                if self.clock() >= end:
                    break
                last_activity = await speak(line)

        await self._wait_until(end)
        self.accepting_speech = False
        while not self._speech.empty():  # log speech the robot did not reply to
            dialogue_log.append(f"Human: {self._speech.get_nowait()}")

    async def _round(self, round_no: int, prev_outcome: str | None) -> str:
        cfg = self.cfg
        planned = robot_vote(self.mode, round_no, self.human_history, cfg.liar_defect_rounds)
        dialogue_log: list[str] = []

        # ---- CHAT --------------------------------------------------------
        self.tracker.pop_phase_counts()
        await self._state("chat", round_no, cfg.chat_s)
        await self._chat(round_no, planned, prev_outcome, dialogue_log)
        expr_chat = self.tracker.pop_phase_counts()

        # ---- VOTE --------------------------------------------------------
        self._human_vote = None
        self._vote_event.clear()
        self._accepting_votes = True
        await self._state("vote", round_no, cfg.vote_s)
        await self.robot.perform(self.dialogue.vote())
        vote_start = self.clock()
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(self._vote_event.wait(), timeout=cfg.vote_s)
        self._accepting_votes = False
        vote_time = round(self.clock() - vote_start, 2) if self._human_vote else ""
        human = self._human_vote or NONE
        expr_vote = self.tracker.pop_phase_counts()

        # ---- RESULT ------------------------------------------------------
        h_pts, r_pts = score(human, planned, cfg.payoff)
        self.totals["human"] += h_pts
        self.totals["robot"] += r_pts
        self.human_history.append(human)
        self.robot_history.append(planned)
        outcome = outcome_key(human, planned)
        await self._state(
            "result",
            round_no,
            cfg.result_s,
            human_vote=human,
            robot_vote=planned,
            points={"human": h_pts, "robot": r_pts},
        )
        await asyncio.sleep(min(REACTION_DELAY_S, cfg.result_s))
        reaction_expr = self.tracker.current()
        reaction = self.dialogue.reaction(outcome, reaction_expr)
        dialogue_log.append(f"Buddy: {reaction.text}")
        await self.robot.perform(reaction)
        if self.brain:
            self.brain.note_robot_line(reaction.text)
        await asyncio.sleep(max(0.0, cfg.result_s - REACTION_DELAY_S))

        self.logger.write(
            participant=self.participant,
            mode=self.mode.value,
            round=round_no,
            robot_vote=planned,
            human_vote=human,
            outcome=outcome,
            human_points=h_pts,
            robot_points=r_pts,
            human_total=self.totals["human"],
            robot_total=self.totals["robot"],
            vote_time_s=vote_time,
            expr_chat=expr_chat,
            expr_vote=expr_vote,
            expr_reaction=reaction_expr,
            dialogue=dialogue_log,
        )
        return outcome
