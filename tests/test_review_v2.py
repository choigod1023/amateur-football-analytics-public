from app.review_text import analysis, captions, half_summary
from scripts.build_review_video import smooth_at


def test_smooth_positions_move_gently_and_bridge_short_gaps():
    frames = list(range(0, 20))
    jittery = {f: (f * 1.0 + (0.8 if f % 2 else -0.8), 5.0) for f in frames}
    steps = [smooth_at(frames, jittery, f / 2) for f in range(4, 30)]
    deltas = [abs(b[0] - a[0]) for a, b in zip(steps, steps[1:])]
    assert max(deltas) < 0.9                                                    # no tadpole shaking from frame to frame
    assert smooth_at([0, 1, 2], {0: (0, 0), 1: (1, 0), 2: (2, 0)}, 40.0) is None     # nothing seen near that frame


def test_the_analysis_is_specific_to_the_moment():
    facts = {'side': 'far', 'back_line': 34.0, 'defenders_near': 2, 'support_near': 3, 'box_ours': 1, 'speed_kmh': 22}
    run = analysis({'kind': 'run', 'goal_follow': True}, facts)
    assert '먼 쪽 측면' in run['summary'] and '골로 마무리' in run['summary']
    assert any('22km/h' in g for g in run['good']) and any('두 명' in f for f in run['fix']) and any('박스 안 인원이 적었습니다' in f for f in run['fix'])
    assert len(run['good']) <= 3 and len(run['fix']) <= 3 and run['next']
    poor = analysis({'kind': 'conceded_run'}, {'defenders_near': 1})
    assert '신호' in poor['next'] and any('한 명' in f for f in poor['fix'])


def test_captions_run_to_the_goal_and_the_half_summary_counts():
    event = {'kind': 'run', 'time': 100.0, 'goal_at': 108.0}
    texts = captions(event, {'side': 'centre', 'defenders_near': 2})
    assert any(t == '골' and abs(off - 7.8) < 0.01 for off, _dur, t in texts) and any('수비수 두 명' in t for _o, _d, t in texts)
    points = half_summary([{'kind': 'run', 'goal_follow': True}, {'kind': 'run', 'goal_follow': False}, {'kind': 'conceded_run'}])
    assert '침투가 2번' in points[0] and '1번이 골' in points[0] and any('허용' in p for p in points)
