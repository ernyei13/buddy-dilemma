"""All tunable study parameters in one place.

The round settings (rounds, chat lengths, vote time, lie rounds) can also be changed on the
start screen before each session.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Config:
    # Robot backend: "mock" (avatar + TTS in the browser), "misty" (HTTP API) or "buddy" (app).
    robot: str = "mock"
    misty_ip: str = ""  # Misty II address, e.g. 192.168.1.50 (only for robot="misty")
    # Camera for facial expressions: "laptop" (webcam) or "robot" (Misty's camera).
    camera: str = "laptop"

    @property
    def robot_name(self) -> str:
        return "Misty" if self.robot == "misty" else "Buddy"

    # ---- Round structure (editable on the start screen) -------------------------------------
    rounds: int = 8
    first_chat_s: float = 60.0  # chat length in round 1
    chat_s: float = 20.0  # chat length in every later round
    vote_s: float = 10.0
    result_s: float = 6.0

    # Robot strategy: this opening pattern, then copycat (plays the human's previous vote).
    opening: tuple[str, ...] = ("C", "D", "C", "C")
    # Rounds in which the robot lies about its vote (says the opposite of what it does).
    lie_rounds: tuple[int, ...] = (2, 5, 7)
    # Friendly mode only: red eyes and a sad face at the reveal when the robot cooperated but
    # the person defected.
    red_eyes_when_betrayed: bool = True

    # Scripted fallback only (no LLM): seconds into the chat at which the robot speaks.
    chat_beats: tuple[float, ...] = (0.0, 10.0, 20.0, 35.0, 50.0)

    # Conversation (all local): Ollama LLM + faster-whisper speech recognition.
    use_llm: bool = True
    llm_model: str = "qwen2.5:3b"  # small + fast; better: qwen2.5:7b
    ollama_url: str = "http://localhost:11434"
    stt_model: str = "base.en"  # faster-whisper size: tiny.en, base.en, small.en, ...
    silence_nudge_s: float = 6.0  # robot speaks up after this much silence
    min_turn_s: float = 3.0  # no new robot turn this close to the end of the chat
    hand_gesture_chance: float = 0.85  # friendly mode: chance of a hand gesture on a plain line

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

    def chat_seconds(self, round_no: int) -> float:
        return self.first_chat_s if round_no == 1 else self.chat_s
