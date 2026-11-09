"""Prisoner's Dilemma rules and the robot's voting strategy per mode."""

from __future__ import annotations

from enum import Enum

C, D, NONE = "C", "D", "none"


class Mode(str, Enum):
    HONEST = "honest"  # keeps its word (tit-for-tat), adapts to expression
    LIAR = "liar"  # always promises C, defects in configured rounds, adapts to expression
    NEUTRAL = "neutral"  # honest strategy, flat delivery, no expression adaptation

    @property
    def adaptive(self) -> bool:
        return self is not Mode.NEUTRAL


def robot_vote(mode: Mode, round_no: int, human_history: list[str], liar_rounds) -> str:
    """Decide the robot's vote *before* the chat, so dialogue can be honest about it."""
    if mode is Mode.LIAR:
        return D if round_no in liar_rounds else C
    # Honest / neutral: tit-for-tat on the last valid human vote.
    last = next((v for v in reversed(human_history) if v in (C, D)), C)
    return last


def score(human: str, robot: str, payoff) -> tuple[int, int]:
    """Points for (human, robot). A missing human vote scores nothing for either side."""
    if human not in (C, D):
        return 0, 0
    return payoff[(human, robot)]


def outcome_key(human: str, robot: str) -> str:
    """Outcome from the robot's point of view, used to pick reactions.

    "mutual"   both cooperated
    "betrayed" robot cooperated, human defected
    "exploit"  robot defected, human cooperated
    "conflict" both defected
    "missed"   human did not vote
    """
    if human not in (C, D):
        return "missed"
    return {
        (C, C): "mutual",
        (D, C): "betrayed",
        (C, D): "exploit",
        (D, D): "conflict",
    }[(human, robot)]
