import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import startup_check as sc  # noqa: E402


def test_interval_stats_of_a_regular_stream():
    stats = sc.interval_stats([i * 0.04 for i in range(26)])
    assert stats['fps'] == pytest.approx(25.0)
    assert stats['cv'] == pytest.approx(0.0, abs=1e-6)
    assert stats['max_gap'] == pytest.approx(0.04)


def test_interval_stats_with_a_stall():
    times = [i * 0.04 for i in range(10)] + [0.36 + 2.0 + i * 0.04 for i in range(10)]
    stats = sc.interval_stats(times)
    assert stats['max_gap'] > 1.9
    assert stats['cv'] > 1.0


def test_interval_stats_with_too_few_frames():
    assert sc.interval_stats([0.0])['fps'] is None
    assert sc.interval_stats([])['frames'] == 0


def test_grade_input():
    regular = sc.interval_stats([i * 0.04 for i in range(50)])
    assert sc.grade_input(regular, 0, 25.0)[0] == '통과'
    assert sc.grade_input(regular, 2, 25.0)[0] == '주의'
    assert sc.grade_input(sc.interval_stats([0.0]), 0, 25.0)[0] == '실패'
    stalled = sc.interval_stats([0.0, 0.04, 0.08, 2.5, 2.54])
    assert sc.grade_input(stalled, 0, 25.0)[0] == '실패'
    slow = sc.interval_stats([i * 0.1 for i in range(30)])
    assert sc.grade_input(slow, 0, 25.0)[0] == '주의'


def test_grade_people():
    assert sc.grade_people([20, 21, 19])[0] == '통과'
    assert sc.grade_people([9, 10, 11])[0] == '주의'
    assert sc.grade_people([2, 3])[0] == '실패'
    assert sc.grade_people([])[0] == '실패'


def test_colour_group_follows_the_live_rule():
    neon, dark = 0, 1
    assert sc.colour_group([0.2, 0.0], neon, dark) == 'bright'
    assert sc.colour_group([0.05, 0.5], neon, dark) == 'dark'
    assert sc.colour_group([0.05, 0.1], neon, dark) is None
    assert sc.colour_group([0.15, 0.6], neon, dark) == 'bright'      # neon wins over dark


def test_grade_teams():
    assert sc.grade_teams({'bright': 30, 'dark': 40}, 10)[0] == '통과'
    assert sc.grade_teams({'bright': 2, 'dark': 40}, 0)[0] == '실패'
    assert sc.grade_teams({'bright': 0, 'dark': 0}, 5)[0] == '실패'
    assert sc.grade_teams({'bright': 5, 'dark': 5}, 40)[0] == '주의'


def test_direction_toward_minus_x_when_the_own_team_stands_at_plus_x():
    own = [[10 + i for i in range(6)] for _ in range(5)]            # mean 12.5
    other = [[-20 + i for i in range(6)] for _ in range(5)]         # mean -17.5
    result = sc.suggest_direction(own, other)
    assert result['direction'] == -1
    assert result['gap'] == pytest.approx(30.0)
    assert result['frames'] == 5


def test_direction_toward_plus_x_when_the_own_team_stands_at_minus_x():
    own = [[-15.0] * 6]
    other = [[12.0] * 6]
    assert sc.suggest_direction(own, other)['direction'] == 1


def test_no_direction_when_the_means_are_close_or_people_are_missing():
    close = sc.suggest_direction([[1.0] * 6], [[-1.0] * 6])
    assert close['direction'] is None and 'm' in close['reason']
    few = sc.suggest_direction([[10.0] * 3], [[-10.0] * 6])
    assert few['direction'] is None and few['frames'] == 0
    assert sc.suggest_direction([], [])['direction'] is None


def test_worst_status_and_public_source(tmp_path):
    assert sc.worst(['통과', '주의', '통과']) == '주의'
    assert sc.worst(['통과', '실패', '주의']) == '실패'
    assert sc.worst([]) == '실패'
    video = tmp_path / 'match.mp4'
    video.write_bytes(b'x')
    assert sc.public_source(str(video)) == 'match.mp4'
    hidden = sc.public_source('srt://example.invalid:9000?streamid=x')
    assert 'example' not in hidden and 'streamid' not in hidden


def test_calibration_check_without_a_file(tmp_path):
    cv2 = pytest.importorskip('cv2')
    result, fitted, shift = sc.calibration_check(cv2, tmp_path / 'missing.json', 'cam1', None)
    assert result['status'] == '실패' and fitted is None and shift == (0.0, 0.0)
    path = tmp_path / 'calibrations.json'
    path.write_text(json.dumps({'cam3': {}}), encoding='utf-8')
    result, fitted, _ = sc.calibration_check(cv2, path, 'cam1', None)
    assert result['status'] == '실패' and not result['camera_entry']
