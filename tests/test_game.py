from pd_hri.config import Config
from pd_hri.game import NONE, C, D, Mode, outcome_key, robot_vote, score

LIAR_ROUNDS = (2, 4)


def test_honest_is_tit_for_tat():
    assert robot_vote(Mode.HONEST, 1, [], LIAR_ROUNDS) == C
    assert robot_vote(Mode.HONEST, 2, [D], LIAR_ROUNDS) == D
    assert robot_vote(Mode.HONEST, 3, [D, C], LIAR_ROUNDS) == C


def test_honest_ignores_missing_votes():
    assert robot_vote(Mode.HONEST, 3, [D, NONE], LIAR_ROUNDS) == D
    assert robot_vote(Mode.NEUTRAL, 2, [NONE], LIAR_ROUNDS) == C


def test_liar_defects_only_in_configured_rounds():
    votes = [robot_vote(Mode.LIAR, r, [C] * (r - 1), LIAR_ROUNDS) for r in range(1, 6)]
    assert votes == [C, D, C, D, C]


def test_score_and_outcome():
    payoff = Config().payoff
    assert score(C, C, payoff) == (3, 3)
    assert score(C, D, payoff) == (0, 5)
    assert score(D, C, payoff) == (5, 0)
    assert score(NONE, C, payoff) == (0, 0)
    assert outcome_key(D, C) == "betrayed"
    assert outcome_key(C, D) == "exploit"
    assert outcome_key(NONE, D) == "missed"
