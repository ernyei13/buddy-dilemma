"""All tunable study parameters in one place."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Config:
    # Robot backend: "mock" (avatar + TTS in the browser) or "buddy" (remote adapter).
    robot: str = "mock"

    # Round structure
    rounds: int = 5
    chat_s: float = 60.0
    vote_s: float = 10.0
    result_s: float = 6.0
    # Seconds into the chat phase at which the robot speaks.
    chat_beats: tuple[float, ...] = (0.0, 15.0, 30.0, 45.0)

    # Liar mode: rounds (1-based) in which the robot defects despite promising to cooperate.
    liar_defect_rounds: tuple[int, ...] = (2, 4)

    # Payoff: (human_points, robot_points) indexed by (human_vote, robot_vote).
    payoff: dict[tuple[str, str], tuple[int, int]] = field(
        default_factory=lambda: {
            ("C", "C"): (3, 3),
            ("C", "D"): (0, 5),
            ("D", "C"): (5, 0),
            ("D", "D"): (1, 1),
        }
    )

    # Expression smoothing window (seconds).
    expression_window_s: float = 3.0

    # Where per-session CSV logs go.
    data_dir: Path = Path("data")

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
