import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.pitch_map import fit
from tests.test_pitch_map import IDS, project, record

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'build_team_minimap.py'
spec = importlib.util.spec_from_file_location('build_team_minimap', SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def box_at(x, y):
    u, v = project(x, y)
    return [u * 1920 - 15, v * 1080 - 70, u * 1920 + 15, v * 1080]


def test_crowded_flags_mark_only_players_standing_close_together():
    flags = module.crowded_flags([(1, [100, 100, 130, 170]), (2, [120, 100, 150, 170]), (3, [900, 100, 930, 170])])
    assert flags == {1, 2}


def test_measure_frame_places_labelled_players_in_metres_and_counts_the_outside_ones():
    fitted = fit(record(IDS))
    tracks = {1: [{'frame': 0, 'team': 'A', 'box': box_at(10, 5)}], 2: [{'frame': 0, 'team': 'B', 'box': box_at(-20, 8)}],
              3: [{'frame': 0, 'team': 'S', 'box': box_at(0, 0)}], 4: [{'frame': 0, 'team': 'A', 'box': box_at(95, 5)}],
              5: [{'frame': 1, 'team': 'A', 'box': box_at(0, 0)}]}
    placed, outside = module.measure_frame(tracks, 0, fitted, 1920, 1080)
    assert len(placed['A']) == 1 and abs(placed['A'][0]['x'] - 10) < 0.05 and abs(placed['A'][0]['y'] - 5) < 0.05
    assert len(placed['B']) == 1 and outside == 1                      # the spectator is ignored; the player far outside is counted


def test_the_script_refuses_without_a_calibration_for_the_camera(tmp_path):
    tracks, calibrations = tmp_path / 't.json', tmp_path / 'c.json'
    tracks.write_text(json.dumps({'clip': 'b00', 'frames': 1, 'tracks': {}}), encoding='utf-8')
    calibrations.write_text('{}', encoding='utf-8')
    run = subprocess.run([sys.executable, str(SCRIPT), str(tracks), str(calibrations), 'cam1', str(tmp_path / 'out')], capture_output=True, text=True)
    assert run.returncode != 0 and 'No saved calibration' in run.stderr


def test_the_script_writes_a_video_and_metrics_for_a_valid_calibration(tmp_path):
    pytest.importorskip('cv2')
    tracks = {str(i): [{'frame': f, 'team': 'A' if i % 2 else 'B', 'box': box_at(-10 + 3 * i + f, -8 + 2 * i)} for f in range(3)] for i in range(1, 10)}
    (tmp_path / 't.json').write_text(json.dumps({'clip': 'synthetic', 'frames': 3, 'tracks': tracks}), encoding='utf-8')
    (tmp_path / 'c.json').write_text(json.dumps({'cam1': record(IDS)}), encoding='utf-8')
    run = subprocess.run([sys.executable, str(SCRIPT), str(tmp_path / 't.json'), str(tmp_path / 'c.json'), 'cam1', str(tmp_path / 'out')], capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    metrics = json.loads((tmp_path / 'out' / 'metrics.json').read_text(encoding='utf-8'))
    assert (tmp_path / 'out' / 'minimap.mp4').is_file() and len(metrics['frames']) == 3
    assert metrics['frames'][0]['team_a']['players'] == 5 and metrics['calibration_rms_m'] < 0.01


def test_a_shift_schedule_holds_from_its_frame_on():
    schedule = module.parse_schedule('0:-1.8,6.8;1950:0.3,0.3')
    assert schedule == [(0, (-1.8, 6.8)), (1950, (0.3, 0.3))]
    assert module.shift_at(schedule, 10) == (-1.8, 6.8) and module.shift_at(schedule, 1949) == (-1.8, 6.8)
    assert module.shift_at(schedule, 1950) == (0.3, 0.3) and module.shift_at(schedule, 5000) == (0.3, 0.3)
    assert module.shift_at([], 5, default=(1.0, 2.0)) == (1.0, 2.0)
