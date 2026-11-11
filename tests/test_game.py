from pd_hri.config import Config
from pd_hri.game import (
    NONE,
    C,
    D,
    Mode,
    outcome_key,
    parse_rounds,
    robot_claim,
    robot_vote,
    score,
)


def test_opening_pattern_then_copycat():
    human = [D, C, C, D, C, D, D]
    votes = [robot_vote(r, human[: r - 1]) for r in range(1, 9)]
    # rounds 1-4: C D C C; round 5+: copy the human's previous vote
    assert votes == [C, D, C, C, D, C, D, D]


def test_copycat_skips_missing_votes():
    assert robot_vote(5, [C, C, C, D, NONE]) == D
    assert robot_vote(5, [NONE] * 4) == C


def test_claims_lie_only_in_lie_rounds():
    lies = (2, 5, 7)
    assert robot_claim(D, 2, lies) == C  # defects, says cooperate
    assert robot_claim(C, 5, lies) == D  # cooperates, says defect
    assert robot_claim(C, 3, lies) == C  # truthful


def test_default_game_has_three_lies_in_eight_rounds():
    cfg = Config()
    assert cfg.rounds == 8 and len(cfg.lie_rounds) == 3
    assert cfg.chat_seconds(1) == 60 and cfg.chat_seconds(2) == 20


def test_modes():
    assert Mode.FRIENDLY.adaptive and not Mode.NEUTRAL.adaptive


def test_score_and_outcome():
    payoff = Config().payoff
    assert score(C, C, payoff) == (3, 3)
    assert score(C, D, payoff) == (0, 5)
    assert score(NONE, C, payoff) == (0, 0)
    assert outcome_key(D, C) == "betrayed"
    assert outcome_key(C, D) == "exploit"
    assert outcome_key(NONE, D) == "missed"


def test_parse_rounds():
    assert parse_rounds("2, 5,7", 8) == (2, 5, 7)
    assert parse_rounds("0, 9, x, 3;3", 8) == (3,)
    assert parse_rounds("", 8) == ()
