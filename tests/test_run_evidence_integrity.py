from scripts import build_tactical_report as report
from app.tactical_concepts import runs_in_behind


def test_seven_synthetic_positions_cannot_complete_a_run(monkeypatch):
    monkeypatch.setattr(report, 'feet_to_metres', lambda fitted, box, *a, **k: (box[0], 0))
    rows = {'runner': [{'frame': f, 'team': 'B', 'box': [.8*f, 0, .8*f+1, 2],
                        'interpolated': 7 <= f <= 13} for f in range(21)]}
    _, observed = report.metre_rows(rows, {}, [], None, 0, 21)
    _, with_estimates = report.metre_rows(rows, {}, [], None, 0, 21, include_estimates=True)
    line = {s: 8 for s in range(5)}
    assert len(observed['runner']) == 14
    assert runs_in_behind(observed, line, fps=5) == []
    assert len(runs_in_behind(with_estimates, line, fps=5)) == 1
