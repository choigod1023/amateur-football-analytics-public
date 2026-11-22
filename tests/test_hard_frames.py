import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.hard_frames import HardFrameCollector, judge  # noqa: E402


def boxes(n, score=0.5):
    return [[10 * i, 10, 10 * i + 8, 40, score] for i in range(n)]


def frame():
    return np.zeros((72, 128, 3), np.uint8)


def test_judge_needs_history_for_drop():
    assert judge([(30, 9)] * 3, 20, 9) == []
    assert judge([(30, 9)] * 8, 25, 9) == ['count_drop']
    assert judge([(30, 9)] * 8, 27, 9) == []


def test_judge_team_rules_off_by_default_and_on_when_asked():
    assert judge([(30, 9)] * 8, 30, 3) == []
    assert judge([], 30, 3, settings={'team_low': 7}) == ['team_low']
    assert judge([(30, 10)] * 8, 30, 7, settings={'drop': 0, 'team_drop': 3}) == ['team_drop']


def test_judge_disagreement_counts_boxes_the_detector_lacks():
    mine = [[0, 0, 10, 30, 0.9]]
    other = [[0, 0, 10, 30, 0.9], [100, 0, 110, 30, 0.5], [200, 0, 210, 30, 0.2]]
    assert judge([], 1, None, mine, other, {'disagree': 1}) == ['detectors_disagree']
    assert judge([], 1, None, mine, other[:1], {'disagree': 1}) == []


def test_collector_saves_with_origin_and_respects_gap_and_cap(tmp_path):
    c = HardFrameCollector(tmp_path / 'hf', 'cam1', 'ft_n2.pt', {'min_gap': 10, 'max_frames': 2})
    t = 0.0
    for _ in range(10):                                                    # a steady crowd of 30
        assert c.observe(t, frame(), boxes(30)) is None
        t += 0.2
    first = c.observe(t, frame(), boxes(20))                                # sudden drop
    assert first and first['origin'] == 'hard_frame_collector' and first['status'] == 'unreviewed'
    assert first['camera'] == 'cam1' and first['reasons'] == ['count_drop'] and len(first['boxes']) == 20
    assert (tmp_path / 'hf' / first['image']).is_file()
    assert c.observe(t + 1, frame(), boxes(20)) is None                     # inside the gap
    assert c.flagged == 2 and c.saved == 1
    t += 12
    for _ in range(10):
        c.observe(t, frame(), boxes(30))
        t += 0.2
    assert c.observe(t, frame(), boxes(20)) is not None                     # second one
    t += 12
    for _ in range(10):
        c.observe(t, frame(), boxes(30))
        t += 0.2
    assert c.observe(t, frame(), boxes(20)) is None                         # cap of 2 reached
    rows = [json.loads(x) for x in (tmp_path / 'hf' / 'hard_frames.jsonl').read_text(encoding='utf-8').splitlines()]
    assert len(rows) == 2 and c.summary()['saved'] == 2


def test_collector_counts_on_when_the_run_is_continued(tmp_path):
    folder = tmp_path / 'hf'
    c = HardFrameCollector(folder, settings={'max_frames': 1})
    for i in range(10):
        c.observe(i * 0.2, frame(), boxes(30))
    assert c.observe(3.0, frame(), boxes(10)) is not None
    again = HardFrameCollector(folder, settings={'max_frames': 1})
    for i in range(10):
        again.observe(100 + i * 0.2, frame(), boxes(30))
    assert again.observe(105.0, frame(), boxes(10)) is None
