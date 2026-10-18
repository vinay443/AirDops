from airdops.earsense import PAUSE, RESUME, EarDetector


def feed(det, seq):
    """seq: list of (t, left, right) -> list of non-None actions with times."""
    out = []
    for t, l, r in seq:
        a = det.update(l, r, t)
        if a:
            out.append((t, a))
    return out


def test_pause_after_debounce_and_resume_only_if_we_paused():
    d = EarDetector(trigger="one", debounce_s=1.0)
    acts = feed(d, [(0, True, True), (1, True, False), (1.5, True, False), (2.1, True, False)])
    assert acts == [(2.1, PAUSE)]
    d.paused_by_us = True
    acts = feed(d, [(3, True, True), (4.2, True, True)])
    assert acts == [(4.2, RESUME)]


def test_no_resume_when_nothing_was_paused():
    d = EarDetector(debounce_s=0.5)
    feed(d, [(0, True, True), (1, False, False), (2, False, False)])
    assert feed(d, [(3, True, True), (4, True, True)]) == []


def test_blip_is_ignored():
    d = EarDetector(debounce_s=1.0)
    assert feed(d, [(0, True, True), (0.5, True, False), (0.8, True, True), (2, True, True)]) == []


def test_both_trigger_needs_both_out():
    d = EarDetector(trigger="both", debounce_s=0.5)
    assert feed(d, [(0, True, True), (1, True, False), (2, True, False)]) == []
    assert feed(d, [(3, False, False), (4, False, False)]) == [(4, PAUSE)]


def test_first_reading_never_acts_and_stale_gap_resets():
    d = EarDetector(debounce_s=0.5, stale_after_s=5)
    assert feed(d, [(0, False, False), (1, False, False)]) == []
    feed(d, [(2, True, True), (3, True, True)])
    # 30 s of silence, then "out": treated as a fresh first reading
    assert feed(d, [(33, False, False), (34, False, False)]) == []
