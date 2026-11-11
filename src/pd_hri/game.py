"""Prisoner's Dilemma rules, the robot's voting strategy, and when it lies.

Strategy (same in both modes): a fixed opening pattern (default C, D, C, C), then copycat:
the robot plays whatever the human played the round before.

Lies (same in both modes): in a few configured rounds (default 3 per game) the robot tells the
person it will do the OPPOSITE of what it really does.

Modes differ only in how the robot talks:
  friendly  expressive, reads and reflects the person's face, pushes hard for cooperation
  neutral   machine-like, professional, pragmatic, ignores the face (control condition)
"""

from __future__ import annotations

from enum import Enum

C, D, NONE = "C", "D", "none"


class Mode(str, Enum):
    FRIENDLY = "friendly"
    NEUTRAL = "neutral"

    @property
    def adaptive(self) -> bool:
        """Whether the robot reacts to the person's facial expression."""
        return self is Mode.FRIENDLY


def robot_vote(round_no: int, human_history: list[str], opening=(C, D, C, C)) -> str:
    """The robot's real vote, decided before the chat."""
    if round_no <= len(opening):
        return opening[round_no - 1]
    # Copycat: repeat the human's last valid vote (cooperate if there is none).
    return next((v for v in reversed(human_history) if v in (C, D)), C)


def robot_claim(actual: str, round_no: int, lie_rounds) -> str:
    """What the robot SAYS it will do: the opposite of the truth in lie rounds."""
    if round_no in lie_rounds:
        return D if actual == C else C
    return actual


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


def parse_rounds(text: str, max_round: int) -> tuple[int, ...]:
    """'2, 5,7' -> (2, 5, 7); ignores junk and rounds outside 1..max_round."""
    out = set()
    for part in str(text).replace(";", ",").split(","):
        part = part.strip()
        if part.isdigit() and 1 <= int(part) <= max_round:
            out.add(int(part))
    return tuple(sorted(out))
