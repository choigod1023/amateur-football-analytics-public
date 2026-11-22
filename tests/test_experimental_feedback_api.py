import time
from app import main


def test_experimental_feedback_stays_separate_and_is_removed_when_stale(monkeypatch):
    players = [{'id':str(i), 'team_hint':i//3, 'kind':'observed', 'x':.3, 'y':.2+(i%3)*.2} for i in range(6)]
    candidate = {'status':'reference_unverified', 'field_size_m':[105,68], 'players':players}
    monkeypatch.setitem(main.analysis, 'experimental_map', candidate)
    monkeypatch.setitem(main.analysis, 'feedback', [])
    monkeypatch.setitem(main.status, 'status', 'running')
    monkeypatch.setattr(main, 'manual_mode', False)
    monkeypatch.setattr(main, 'last_map_generation', main.manual_tracks.generation())
    monkeypatch.setattr(main, 'last_analysis_monotonic', time.monotonic())
    current = main.get_analysis()
    assert current['feedback'] == []
    assert len(current['experimental_feedback']) == 2
    assert '실험' in current['experimental_feedback'][0]['limitations']
    monkeypatch.setattr(main, 'last_analysis_monotonic', time.monotonic()-2)
    stale = main.get_analysis()
    assert stale['experimental_map']['status'] == 'stale'
    assert stale['experimental_feedback'] == []
