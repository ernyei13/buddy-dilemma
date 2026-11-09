"""One CSV per session, one row per round. Flushed after every row."""

from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path

FIELDS = [
    "timestamp",
    "session_id",
    "participant",
    "mode",
    "round",
    "robot_vote",
    "human_vote",
    "outcome",
    "human_points",
    "robot_points",
    "human_total",
    "robot_total",
    "vote_time_s",
    "expr_chat",  # JSON label counts during the chat
    "expr_vote",  # JSON label counts during voting
    "expr_reaction",  # dominant label right after the reveal
    "utterances",  # robot lines this round, " | " separated
]


class RoundLogger:
    def __init__(self, data_dir: Path, participant: str, mode: str):
        data_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        safe = "".join(ch for ch in participant if ch.isalnum() or ch in "-_") or "anon"
        self.session_id = f"{stamp}_{safe}_{mode}"
        self.path = data_dir / f"{self.session_id}.csv"
        self._fh = self.path.open("w", newline="", encoding="utf-8")
        self._writer = csv.DictWriter(self._fh, fieldnames=FIELDS)
        self._writer.writeheader()
        self._fh.flush()

    def write(self, **row) -> None:
        row.setdefault("timestamp", datetime.now().isoformat(timespec="seconds"))
        row.setdefault("session_id", self.session_id)
        for key in ("expr_chat", "expr_vote"):
            if isinstance(row.get(key), dict):
                row[key] = json.dumps(row[key], sort_keys=True)
        if isinstance(row.get("utterances"), list):
            row["utterances"] = " | ".join(row["utterances"])
        self._writer.writerow(row)
        self._fh.flush()

    def close(self) -> None:
        self._fh.close()
