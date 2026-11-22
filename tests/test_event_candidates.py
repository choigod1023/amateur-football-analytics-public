import importlib.util
import json
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'build_event_candidates.py'
spec = importlib.util.spec_from_file_location('build_event_candidates', SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def person(x1, y1, x2, y2, neon=0.0, dark=0.0):
    return [x1, y1, x2, y2, .9, neon, dark, 0.0]


def test_referee_at_centre_circle_becomes_a_merged_candidate(tmp_path):
    scan = []
    for t in range(80):
        people = [person(300 + t, 800, 320 + t, 840, neon=.4), person(1500, 800, 1520, 840)]
        if 10 <= t <= 15 or 20 <= t <= 24:  # two close stays are one candidate
            people.append(person(998, 790, 1018, 828, dark=.7))
        if 50 <= t <= 52:                    # too short to count
            people.append(person(998, 790, 1018, 828, dark=.7))
        if 60 <= t <= 70:                    # very dark but far from the circle
            people.append(person(300, 790, 320, 828, dark=.7))
        scan.append({'t': t, 'people': people})
    scan_path = tmp_path / 'scan.jsonl'
    scan_path.write_text('\n'.join(json.dumps(r) for r in scan), encoding='utf-8')
    motion_path = tmp_path / 'motion.json'
    motion_path.write_text(json.dumps([[1, 0.0, 1.0, 0.0, 0.0, 500], [2, 30.0, 1.0, 0.0, 0.0, 500], [3, 60.0, 1.0, 0.0, 0.0, 500]]), encoding='utf-8')
    items, total = module.build(scan_path, motion_path, min_run=4, merge_window=20)
    assert total == 80
    assert [i['id'] for i in items] == ['c001']
    assert items[0]['t'] == 12.0 and items[0]['run'] == [10, 15]
    assert 0 < items[0]['score'] <= 1


def test_seconds_without_a_known_camera_transform_are_skipped(tmp_path):
    scan = [{'t': t, 'people': [person(998, 790, 1018, 828, dark=.7)]} for t in range(40)]
    scan_path = tmp_path / 'scan.jsonl'
    scan_path.write_text('\n'.join(json.dumps(r) for r in scan), encoding='utf-8')
    motion_path = tmp_path / 'motion.json'
    motion_path.write_text(json.dumps([[1, 0.0, None, None, None, 0]]), encoding='utf-8')
    items, _ = module.build(scan_path, motion_path, min_run=4, merge_window=20)
    assert items == []
