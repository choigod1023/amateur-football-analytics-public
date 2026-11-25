"""The other team's block of the half-time report (app/opponent_summary.py): judged only with enough evidence, the same for both directions, never in developer words."""
import json
import re

from app.halftime_accumulator import Accumulator
from app.halftime_report import HalftimeService, build_report
from app.live_positions import PositionLog
from app.opponent_summary import NOT_JUDGED, summary

L = 89.0
DEV = re.compile(r'추적|탐지|프레임|모델|픽셀|track|frame|model|pixel|\d+\.\d|\bm\b|미터|%')


def our_frame_second(t):
    """Ours and theirs in our team's frame (u to the goal we attack, v with our left negative). First 300 s: we are in their half and they defend with a high back line
    (34.5 m from their goal line); after: they attack, mostly down our right (v > W/6) into our defensive third."""
    if t < 300:
        ours = [(5.0 + 3 * i, -25.0 + 5 * i) for i in range(11)]
        theirs = [(10.0, -8.0), (10.0, 8.0), (2.0, -20.0), (2.0, 20.0), (-2.0, 0.0), (-6.0, -12.0), (-6.0, 12.0), (-12.0, 0.0), (-14.0, -20.0), (-14.0, 20.0)]
    else:
        ours = [(-40.0 + 3 * i, -25.0 + 5 * i) for i in range(11)]
        theirs = [(-30.0, 15.0), (-28.0, 22.0), (-25.0, 18.0), (-20.0, 12.0), (-20.0, 0.0), (-10.0, 14.0), (-8.0, -10.0), (0.0, 10.0), (5.0, -5.0), (8.0, 5.0)]
    return ours, theirs


def make_session(store, direction=1, seen=10, seconds=range(0, 600), skip=(), session='s1'):
    folder = store / 'alerts' / session
    folder.mkdir(parents=True, exist_ok=True)
    log = PositionLog(folder / 'positions.jsonl', 'B', 'A', direction, L, 62.0, 0.0)
    for t in seconds:
        if t in skip:
            continue
        ours, theirs = our_frame_second(t)
        raw = lambda pts, base: [(base + i, u * direction, v * direction) for i, (u, v) in enumerate(pts)]  # noqa: E731
        log.add(float(t), raw(ours, 1), raw(theirs[:seen], 100))
    log.close()
    return folder


def report_of(tmp_path, **kw):
    folder = make_session(tmp_path, **kw)
    acc = Accumulator('s1')
    acc.catch_up(folder / 'positions.jsonl', None)
    return build_report({**acc.state, 'session': 's1'}, 1)


def item(block, key):
    return next(i for i in block['items'] if i['key'] == key)


def test_a_well_seen_other_team_is_judged_line_side_and_numbers(tmp_path):
    o = report_of(tmp_path)['opponent_team']
    assert o['judged'] is True
    assert item(o, 'line')['text'].startswith('상대 수비 줄이 높았습니다')
    assert o['lanes']['main'] == 2 and '우리 오른쪽' in item(o, 'lanes')['text']
    assert o['headline'] == ['상대는 수비 줄을 높이 올렸고, 주로 우리 오른쪽으로 들어왔습니다.']
    assert o['shape']['defend'] and o['shape']['attack'] and len(o['shape']['defend']['grid']) == 18
    numbers = item(o, 'numbers')['text']
    assert '5명 안팎이 올라왔습니다' in numbers and '6명 안팎을 남겼습니다' in numbers
    for i in o['items']:
        assert not DEV.search(i['text']), i['text']
    assert not DEV.search(' '.join(o['headline']))


def test_the_same_play_attacking_the_other_way_gives_the_same_block(tmp_path):
    a = report_of(tmp_path / 'a', direction=1)['opponent_team']
    b = report_of(tmp_path / 'b', direction=-1)['opponent_team']
    assert a == b
    assert a['lanes']['main'] == 2                                       # our right stays our right, the back line stays high


def test_a_partly_seen_other_team_is_not_judged(tmp_path):
    r = report_of(tmp_path, seen=5)
    o = r['opponent_team']
    assert o['judged'] is False and o['headline'] == [NOT_JUDGED] and o['lanes'] is None
    assert all(not i['judged'] and i['text'] == NOT_JUDGED for i in o['items'])
    assert not re.search(r'\d', json.dumps(o['headline'], ensure_ascii=False))


def test_a_few_good_seconds_judge_only_what_they_can(tmp_path):
    seconds = list(range(0, 130)) + list(range(300, 311))                # enough defending seconds, too few attacking ones
    o = report_of(tmp_path, seconds=seconds)['opponent_team']
    assert o['judged'] is True
    assert item(o, 'line')['judged'] and not item(o, 'shape_attack')['judged'] and o['shape']['attack'] is None
    assert o['lanes'] is None and item(o, 'lanes')['text'] == NOT_JUDGED


def test_no_other_team_at_all_keeps_the_report_as_it_was(tmp_path):
    r = report_of(tmp_path, seen=0)
    for key in ('summary', 'problems', 'opponent', 'pictures', 'box_attacks', 'conceded', 'alerts', 'missing', 'second_half', 'end_text', 'build_seconds'):
        assert key in r
    assert r['opponent_team']['judged'] is False and r['opponent_team']['headline'] == [NOT_JUDGED]


def test_a_stop_in_the_middle_of_the_half_still_makes_the_block(tmp_path):
    r = report_of(tmp_path, skip=set(range(200, 420)))
    assert r['missing']['ranges']
    assert r['opponent_team']['judged'] is True


def test_sums_from_an_older_file_without_the_block_are_read_as_nothing(tmp_path):
    folder = make_session(tmp_path)
    acc = Accumulator('s1')
    acc.catch_up(folder / 'positions.jsonl', None)
    for b in acc.state['halves']['1']['minutes'].values():
        b.pop('opp')
    r = build_report({**acc.state, 'session': 's1'}, 1)
    assert r['opponent_team']['judged'] is False
    assert summary([])['judged'] is False


def test_too_many_points_of_the_other_team_are_a_colour_mix_up_and_do_not_count():
    from app.opponent_summary import add_second, new_opp
    o = new_opp()
    add_second(o, [(0.0, 0.0)] * 5, [(float(i), 0.0) for i in range(14)], L, 62.0)
    assert o['n7'] == 0


def test_the_service_writes_the_block_into_report_json(tmp_path):
    make_session(tmp_path)
    service = HalftimeService(tmp_path, half_seconds=9999)
    service.start('s1')
    assert service.report('s1')['opponent_team']['judged'] is True


def test_no_side_is_said_when_the_moments_they_came_in_point_elsewhere(tmp_path):
    folder = make_session(tmp_path)
    acc = Accumulator('s1')
    acc.catch_up(folder / 'positions.jsonl', None)
    buckets = list(acc.state['halves']['1']['minutes'].values())
    assert summary(buckets, entry_side=2)['lanes']['main'] == 2
    for other in (0, 1, -1):
        o = summary(buckets, entry_side=other)
        assert o['lanes']['main'] is None and '분명하지 않았습니다' in item(o, 'lanes')['text']
        assert '우리 오른쪽' not in ' '.join(o['headline'])


def _line_buckets(cls):
    from app.opponent_summary import new_opp
    o = new_opp()
    o['n7'], o['d']['n'], o['d']['cls'] = 300, sum(cls), list(cls)
    o['d']['back'], o['d']['front'] = 20.0 * sum(cls), 0.0
    return [{'n': 600, 'opp': o}]


def test_a_line_class_just_over_the_limit_is_said_with_the_next_one():
    o = summary(_line_buckets([165, 123, 12]))                            # 55 % low, 41 % middle (11-20): 14 points apart
    text = item(o, 'line')['text']
    assert text == '상대 수비 줄은 낮은 편이었습니다(중간일 때도 많았습니다).'
    assert o['headline'][0] == text and '뒤 공간' not in ' '.join(o['headline'])
    o = summary(_line_buckets([30, 130, 140]))                             # high 47 %: under half, not judged as a class
    assert item(o, 'line')['text'] == '상대 수비 줄의 높이가 자주 바뀌었습니다.'
    o = summary(_line_buckets([10, 120, 170]))                             # high 57 %, middle 40 %
    assert item(o, 'line')['text'] == '상대 수비 줄은 높은 편이었습니다(중간일 때도 많았습니다).'


def test_a_clearly_common_line_class_is_said_alone():
    o = summary(_line_buckets([210, 80, 10]))                              # 70 % low, 27 % middle
    assert item(o, 'line')['text'].startswith('상대 수비 줄이 낮았습니다')
    assert o['headline'] == ['상대는 수비 줄을 낮게 내렸습니다.']
    o = summary(_line_buckets([10, 50, 240]))
    assert o['headline'] == ['상대는 수비 줄을 높이 올렸습니다.']


def test_an_unclear_side_is_marked_so_the_bars_are_not_read_as_a_side(tmp_path):
    folder = make_session(tmp_path)
    acc = Accumulator('s1')
    acc.catch_up(folder / 'positions.jsonl', None)
    buckets = list(acc.state['halves']['1']['minutes'].values())
    assert summary(buckets, entry_side=2)['lanes']['unclear'] is False
    assert summary(buckets, entry_side=0)['lanes']['unclear'] is True