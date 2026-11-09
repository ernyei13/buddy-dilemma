"""The interaction state machine: CHAT (60 s) -> VOTE (10 s) -> RESULT, repeated.

Sense:  ExpressionTracker (fed by the browser webcam) + the human's vote
Plan:   robot vote from the mode's strategy; line choice from mode + expression
Act:    Robot.perform() -> face, gesture, speech
"""

from __future__ import annotations

import asyncio
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


class Session:
    def __init__(
        self,
        cfg: Config,
        mode: Mode,
        participant: str,
        robot: Robot,
        broadcast: Broadcast,
        tracker: ExpressionTracker,
        rng: random.Random | None = None,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.cfg = cfg
        self.mode = mode
        self.participant = participant
        self.robot = robot
        self.broadcast = broadcast
        self.tracker = tracker
        self.dialogue = Dialogue(mode, rng)
        self.clock = clock
        self.logger = RoundLogger(cfg.data_dir, participant, mode.value)

        self.human_history: list[str] = []
        self.totals = {"human": 0, "robot": 0}
        self._vote_event = asyncio.Event()
        self._human_vote: str | None = None
        self._accepting_votes = False

    # ---- input from the screen -------------------------------------------
    def submit_vote(self, choice: str) -> bool:
        if not self._accepting_votes or choice not in (C, D) or self._human_vote:
            return False
        self._human_vote = choice
        self._vote_event.set()
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
            self.logger.close()

    async def _round(self, round_no: int, prev_outcome: str | None) -> str:
        cfg = self.cfg
        planned = robot_vote(self.mode, round_no, self.human_history, cfg.liar_defect_rounds)
        utterances: list[str] = []

        async def speak(line: Line) -> None:
            utterances.append(line.text)
            await self.robot.perform(line)

        # ---- CHAT --------------------------------------------------------
        self.tracker.pop_phase_counts()
        await self._state("chat", round_no, cfg.chat_s)
        start = self.clock()
        for i, beat in enumerate(b for b in cfg.chat_beats if b < cfg.chat_s):
            await self._wait_until(start + beat)
            if i == 0:
                line = self.dialogue.opening(prev_outcome, planned)
                if round_no == 1:
                    intro = self.dialogue.intro()
                    line = Line(f"{intro.text} {line.text}", line.face, line.gesture)
            else:
                line = self.dialogue.persuade(self.tracker.current(), planned)
            await speak(line)
        await self._wait_until(start + cfg.chat_s)
        expr_chat = self.tracker.pop_phase_counts()

        # ---- VOTE --------------------------------------------------------
        self._human_vote = None
        self._vote_event.clear()
        self._accepting_votes = True
        await self._state("vote", round_no, cfg.vote_s)
        await self.robot.perform(self.dialogue.vote())
        vote_start = self.clock()
        try:
            await asyncio.wait_for(self._vote_event.wait(), timeout=cfg.vote_s)
        except asyncio.TimeoutError:
            pass
        self._accepting_votes = False
        vote_time = round(self.clock() - vote_start, 2) if self._human_vote else ""
        human = self._human_vote or NONE
        expr_vote = self.tracker.pop_phase_counts()

        # ---- RESULT ------------------------------------------------------
        h_pts, r_pts = score(human, planned, cfg.payoff)
        self.totals["human"] += h_pts
        self.totals["robot"] += r_pts
        self.human_history.append(human)
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
        await speak(self.dialogue.reaction(outcome, reaction_expr))
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
            utterances=utterances,
        )
        return outcome
