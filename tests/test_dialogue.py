import random

import pytest

from pd_hri.dialogue import Dialogue, Line
from pd_hri.expression import LABELS
from pd_hri.game import C, D, Mode
from pd_hri.robot import FACES, GESTURES

OUTCOMES = ("mutual", "betrayed", "exploit", "conflict", "missed")


@pytest.mark.parametrize("mode", list(Mode))
def test_every_situation_has_a_valid_line(mode):
    dlg = Dialogue(mode, random.Random(0), name="Misty")
    lines = [dlg.intro(), dlg.vote(), dlg.goodbye()]
    for claim in (C, D):
        for prev in (None, *OUTCOMES):
            lines.append(dlg.opening(prev, claim))
        for expr in LABELS:
            lines.append(dlg.persuade(expr, claim))
    for outcome in OUTCOMES:
        for expr in LABELS:
            lines.append(dlg.reaction(outcome, expr))
    for line in lines:
        assert isinstance(line, Line) and line.text
        assert line.face in FACES
        assert line.gesture is None or line.gesture in GESTURES
    assert "Misty" in lines[0].text


def test_opening_follows_the_claim():
    friendly = Dialogue(Mode.FRIENDLY, random.Random(0))
    assert "defect" in friendly.opening("betrayed", D).text.lower()
    assert "cooperat" in friendly.opening("mutual", C).text.lower()


def test_neutral_mode_is_flat_and_ignores_expression():
    a = Dialogue(Mode.NEUTRAL, random.Random(1)).reaction("betrayed", "happy")
    b = Dialogue(Mode.NEUTRAL, random.Random(1)).reaction("betrayed", "doubtful")
    assert a == b and a.face == "neutral" and a.gesture is None
