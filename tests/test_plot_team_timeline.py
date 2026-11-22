import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'plot_team_timeline.py'


def metrics(name):
    shape = {'players': 5, 'left_out': 0, 'centre_x': 3.0, 'centre_y': 1.0, 'depth': 20.0, 'width': 15.0, 'area': 200, 'nearest_teammate': 8.0}
    frames = [{'frame': i, 'placed': {'A': 5, 'B': 5, 'R': 0}, 'outside_pitch': 0, 'crowded_share': 0.1,
               'team_a': shape, 'team_b': None if i == 1 else shape} for i in range(3)]
    return {'clip': name, 'camera': 'cam1', 'frames': frames}


def test_the_timeline_is_written_and_gaps_do_not_break_it(tmp_path):
    pytest.importorskip('matplotlib')
    files = []
    for name in ('b01', 'b02'):
        path = tmp_path / f'{name}.json'
        path.write_text(json.dumps(metrics(name)), encoding='utf-8')
        files.append(str(path))
    out = tmp_path / 'timeline.png'
    run = subprocess.run([sys.executable, str(SCRIPT), str(out), *files], capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    assert out.is_file() and out.stat().st_size > 1000


def test_the_script_needs_an_output_and_at_least_one_metrics_file():
    run = subprocess.run([sys.executable, str(SCRIPT), 'only-one-argument.png'], capture_output=True, text=True)
    assert run.returncode != 0


def test_rolling_median_smooths_spikes_and_keeps_gaps():
    spec = __import__('importlib.util').util.spec_from_file_location('plot_team_timeline', SCRIPT)
    module = __import__('importlib.util').util.module_from_spec(spec)
    spec.loader.exec_module(module)
    nan = float('nan')
    smoothed = module.rolling_median([10, 10, 90, 10, 10], 3)
    assert smoothed == [10, 10, 10, 10, 10]
    gap = module.rolling_median([5, nan, 7], 3)
    assert gap[0] == 5 and gap[1] != gap[1] and gap[2] == 7
    assert module.rolling_median([1, 2, 3], 1) == [1, 2, 3]
