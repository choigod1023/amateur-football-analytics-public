import numpy as np

from app.live_feedback import LiveAnalyzer
from app.live_publish import LivePublisher, dashboard_players


BOX = [(1, 40., -5.), (2, 38., 2.), (3, 37., 8.)]


def feed(analyzer, start, end):
    return [alert for step in range(start, end)
            for alert in analyzer.update(step / 5, BOX, [])]


def test_interruption_preserves_cooldown_and_breaks_all_temporal_evidence():
    analyzer = LiveAnalyzer(1)
    assert [a['kind'] for a in feed(analyzer, 0, 16)] == ['box_attack']
    cooldowns, last_any = dict(analyzer.last_alert), analyzer.last_any
    analyzer.interrupt_observations(3.2)
    assert analyzer.last_alert == cooldowns and analyzer.last_any == last_any
    assert not analyzer.frames and not analyzer.box_seconds
    assert not analyzer.isolation_series
    assert analyzer.paths == analyzer.series == {'team': {}, 'other': {}}
    assert analyzer.update(3.2, BOX, []) == []
    assert feed(analyzer, 17, 50) == []


def test_interruption_cannot_join_box_observations_across_bad_frame():
    analyzer = LiveAnalyzer(1)
    assert feed(analyzer, 0, 9) == []
    analyzer.interrupt_observations(1.8)
    assert analyzer.update(2., BOX, []) == []
    assert feed(analyzer, 11, 20) == []
    assert [a['kind'] for a in analyzer.update(4., BOX, [])] == ['box_attack']


def test_calibration_failure_blocks_old_alert_and_metrics(tmp_path):
    pitch = {'length': 89, 'width': 60}
    players = dashboard_players({'home': BOX}, pitch)
    data = LivePublisher(tmp_path).publish(np.zeros((10, 10, 3), dtype=np.uint8),
        players, [{'title': 'old', 'text': 'old'}], 1, pitch, False, 5, 1)
    assert data['feedback'] == []
    assert all(v is None for v in data['metrics'].values())
    assert data['coaching_diagnostics']['state'] == 'blocked'
    assert data['coaching_diagnostics']['reason_codes'] == ['calibration_unavailable']


def test_observing_and_active_alert_are_distinct(tmp_path):
    publisher = LivePublisher(tmp_path)
    args = (np.zeros((10, 10, 3), dtype=np.uint8), [])
    data = publisher.publish(*args, [], 1, {'length': 89, 'width': 60}, True, 5, 1)
    assert data['coaching_diagnostics']['state'] == 'observing'
    assert data['coaching_diagnostics']['reason_codes'] == ['no_recent_alerts']
    data = publisher.publish(*args, [{'title': 'observed', 'text': 'observed'}],
        2, {'length': 89, 'width': 60}, True, 5, 1)
    assert data['coaching_diagnostics']['state'] == 'ready'
