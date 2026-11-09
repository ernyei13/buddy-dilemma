from pd_hri.expression import (
    DOUBTFUL,
    HAPPY,
    NEUTRAL,
    NO_FACE,
    SURPRISED,
    ExpressionTracker,
    classify,
)


def test_classify_rules():
    assert classify({}) == NO_FACE
    assert classify({"mouthSmileLeft": 0.8, "mouthSmileRight": 0.7}) == HAPPY
    assert classify({"jawOpen": 0.6, "eyeWideLeft": 0.5, "eyeWideRight": 0.5}) == SURPRISED
    assert classify({"browDownLeft": 0.5, "browDownRight": 0.5}) == DOUBTFUL
    assert classify({"mouthSmileLeft": 0.1}) == NEUTRAL


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def test_tracker_majority_and_window():
    clock = FakeClock()
    tr = ExpressionTracker(window_s=3.0, clock=clock)
    assert tr.current() == NEUTRAL  # nothing seen yet
    for label in (HAPPY, HAPPY, DOUBTFUL, NO_FACE):
        tr.add(label)
    assert tr.current() == HAPPY
    clock.t = 10.0  # everything falls out of the window
    tr.add(DOUBTFUL)
    assert tr.current() == DOUBTFUL


def test_tracker_phase_counts_reset():
    tr = ExpressionTracker()
    tr.add(HAPPY)
    tr.add(HAPPY)
    assert tr.pop_phase_counts() == {HAPPY: 2}
    assert tr.pop_phase_counts() == {}
