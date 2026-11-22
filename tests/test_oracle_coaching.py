import pytest

from app.live_feedback import LiveAnalyzer
from scripts.evaluate_oracle_coaching import synthetic


@pytest.mark.parametrize('direction', [1, -1])
def test_two_complete_seconds_preserve_positive(direction):
    assert synthetic('sustained', direction) == [{'kind': 'box_attack', 'time': 2.0}]


@pytest.mark.parametrize('mode', ['brief_spikes', 'timestamp_gap'])
def test_incomplete_evidence_does_not_claim_two_seconds(mode):
    assert synthetic(mode) == []


def test_missing_sample_delays_alert_until_new_complete_window():
    assert synthetic('missing_sample') == [{'kind': 'box_attack', 'time': 3.0}]


def test_explicit_interruption_and_clock_gap_break_box_evidence():
    for interrupt in (False, True):
        analyzer = LiveAnalyzer(1, fps=5)
        box = [(i, 35, i) for i in range(3)]
        for sample in range(10):
            assert analyzer.update(sample/5, box, []) == []
        if interrupt:
            analyzer.interrupt_observations(2.0)
        assert analyzer.update(10, box, []) == []


def test_points_beyond_end_line_are_not_penalty_area():
    analyzer = LiveAnalyzer(1, fps=5)
    alerts = [a for f in range(16) for a in analyzer.update(f/5, [(i, 45, i) for i in range(3)], [])]
    assert alerts == []
