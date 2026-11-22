from scripts import build_tactical_report as report


def test_estimates_do_not_enter_observed_metrics(monkeypatch):
    monkeypatch.setattr(report, 'feet_to_metres', lambda *a, **k: (1., 2.))
    rows = {'one': [dict(frame=i, team='B', box=[0, 0, 1, 1], **flag)
                    for i, flag in enumerate([{}, {'interpolated': True}, {'predicted': True}, {'estimated': True}])]}
    evidence = {}
    frames, paths = report.metre_rows(rows, {}, [], None, 0, 4, evidence=evidence)
    assert list(frames) == [0]
    assert len(paths['one']) == 1
    assert evidence == {'observed_rows': 1, 'estimated_rows': 3}
    legacy, _ = report.metre_rows(rows, {}, [], None, 0, 4, include_estimates=True)
    assert len(legacy) == 4


def test_coaching_reports_ball_proxy_explicitly():
    from app.live_feedback import LiveAnalyzer
    analyzer = LiveAnalyzer(1)
    alerts = []
    for f in range(30):
        alerts += analyzer.update(f / 5, [(1, 40, 0), (2, 39, 1), (3, 38, 2)], [])
    assert alerts
    assert all(a['evidence']['ball_observed'] is False and a['limitations'] for a in alerts)
