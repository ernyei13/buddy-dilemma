"""Turn facial blendshape scores into a smoothed expression label.

The browser runs MediaPipe FaceLandmarker and sends its 52 blendshape scores
(0..1). We classify here so the rules are testable and easy to tune.
"""

from __future__ import annotations

import time
from collections import Counter, deque

HAPPY, NEUTRAL, DOUBTFUL, SURPRISED, NO_FACE = (
    "happy",
    "neutral",
    "doubtful",
    "surprised",
    "no_face",
)
LABELS = (HAPPY, NEUTRAL, DOUBTFUL, SURPRISED)


def _avg(s: dict[str, float], *names: str) -> float:
    return sum(s.get(n, 0.0) for n in names) / len(names)


def classify(scores: dict[str, float]) -> str:
    """Rule-based label from MediaPipe blendshape names. Thresholds are a starting point."""
    if not scores:
        return NO_FACE
    smile = _avg(scores, "mouthSmileLeft", "mouthSmileRight")
    jaw = scores.get("jawOpen", 0.0)
    eye_wide = _avg(scores, "eyeWideLeft", "eyeWideRight")
    brow_up = scores.get("browInnerUp", 0.0)
    brow_down = _avg(scores, "browDownLeft", "browDownRight")
    frown = _avg(scores, "mouthFrownLeft", "mouthFrownRight")
    press = _avg(scores, "mouthPressLeft", "mouthPressRight")

    if smile > 0.3:  # light smiles count too
        return HAPPY
    if jaw > 0.35 and (eye_wide > 0.3 or brow_up > 0.4):
        return SURPRISED
    if brow_down > 0.35 or frown > 0.25 or press > 0.4:
        return DOUBTFUL
    return NEUTRAL


class ExpressionTracker:
    """Keeps recent labels and reports the dominant one over a sliding window."""

    def __init__(self, window_s: float = 3.0, clock=time.monotonic):
        self.window_s = window_s
        self._clock = clock
        self._samples: deque[tuple[float, str]] = deque()
        self._phase_counts: Counter[str] = Counter()

    def add(self, label: str) -> None:
        now = self._clock()
        self._samples.append((now, label))
        self._phase_counts[label] += 1
        self._trim(now)

    def _trim(self, now: float) -> None:
        while self._samples and now - self._samples[0][0] > self.window_s:
            self._samples.popleft()

    def current(self) -> str:
        """Dominant face label in the window; NEUTRAL if nothing usable was seen."""
        self._trim(self._clock())
        faces = [lbl for _, lbl in self._samples if lbl in LABELS]
        if not faces:
            return NEUTRAL
        counts = Counter(faces)
        if counts[HAPPY] >= 0.3 * len(faces):  # smiles are short: a brief one still counts
            return HAPPY
        return counts.most_common(1)[0][0]

    def pop_phase_counts(self) -> dict[str, int]:
        """Label counts since the last call (for logging per phase)."""
        counts = dict(self._phase_counts)
        self._phase_counts.clear()
        return counts
