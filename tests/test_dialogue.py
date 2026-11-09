import random

import pytest

from pd_hri.dialogue import PERSUADE_HONEST_DOUBTFUL, PERSUADE_LIAR_DOUBTFUL, Dialogue, Line
from pd_hri.expression import LABELS
from pd_hri.game import C, D, Mode
from pd_hri.robot import FACES, GESTURES

OUTCOMES = ("mutual", "betrayed", "exploit", "conflict", "missed")


@pytest.mark.parametrize("mode", list(Mode))
def test_every_situation_has_a_valid_line(mode):
    dlg = Dialogue(mode, random.Random(0))
    lines = [dlg.intro(), dlg.vote(), dlg.goodbye()]
    for planned in (C, D):
        for prev in (None, *OUTCOMES):
            lines.append(dlg.opening(prev, planned))
        for expr in LABELS:
            lines.append(dlg.persuade(expr, planned))
    for outcome in OUTCOMES:
        for expr in LABELS:
            lines.append(dlg.reaction(outcome, expr))
    for line in lines:
        assert isinstance(line, Line) and line.text
        assert line.face in FACES
        assert line.gesture is None or line.gesture in GESTURES


def test_doubtful_face_changes_persuasion_by_mode():
    liar = Dialogue(Mode.LIAR, random.Random(0)).persuade("doubtful", D)
    honest = Dialogue(Mode.HONEST, random.Random(0)).persuade("doubtful", C)
    assert liar in PERSUADE_LIAR_DOUBTFUL
    assert honest in PERSUADE_HONEST_DOUBTFUL


def test_neutral_mode_ignores_expression():
    happy = {Dialogue(Mode.NEUTRAL, random.Random(1)).reaction("betrayed", "happy").text}
    sad = {Dialogue(Mode.NEUTRAL, random.Random(1)).reaction("betrayed", "doubtful").text}
    assert happy == sad
