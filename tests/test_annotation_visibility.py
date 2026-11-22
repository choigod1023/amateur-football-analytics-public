import csv
from scripts.audit_annotated_visibility import summarize


def test_coverage_counts_only_valid_team_associated_boxes(tmp_path):
    path = tmp_path / 'sample.csv'
    with path.open('w', newline='', encoding='utf-8') as handle:
        w = csv.writer(handle)
        w.writerow([''] + ['0'] * 8 + ['1'] * 8)
        w.writerow([''] + ['1'] * 4 + ['2'] * 4 + ['1'] * 4 + ['2'] * 4)
        w.writerow([''] + ['bb_left', 'bb_top', 'bb_width', 'bb_height'] * 4)
        w.writerow(['frame'])
        w.writerow(['1'] + [1, 2, 3, 4] * 4)
        w.writerow(['2'] + [1, 2, 3, 4] * 3 + ['', '', '', ''])
    result = summarize(path)
    assert result['frames'] == 2
    assert result['both_teams_at_least_two_frames'] == 1
    assert result['both_teams_at_least_two_fraction'] == 0.5
    assert result['box_height_median_px'] == 4
