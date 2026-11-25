"""The picture-first half-time report (/halftime): seven blocks, each one picture, one short line and one line of evidence, made from the records the live run already wrote.

Inputs (all read on the review server, never inside the live analysis, no GPU):
  * <store>/alerts/<session>/positions.jsonl  one line per analysed second (app/live_positions.py): our points 'team', theirs 'other', screen metres; 'half' rows turn the direction
  * <store>/alerts/<session>/alerts.jsonl     the coaching alerts and the heartbeats ('time' = analysis time, 'wall' = clock time: the heartbeats give the offset clock -> analysis)
  * <store>/alerts/<session>/score.jsonl      goals and undos (app/score_board.py), 'analysis.positions_time' = the analysis second of the press
  * <store>/analyst-tags/tags.jsonl           kick-off / end marks and scene marks (epoch clock time; mapped with the heartbeat offset, kept only when inside this session's seconds)
  * <store>/alerts/labels-coach/...           the coach's "도움됨" / "아님" (app/coach_feedback.py)
  * <store>/service/lineup/<session>.json, else <store>/service/lineup.json   (optional) the starting line-up typed in before the match
Reading everything again costs well under a second for a 23-minute half (measured in wiki/features/halftime-report-1124.md), so the report is simply made again on request.

Frame: u toward the goal our team attacks (own goal line at -L/2), v across with our left negative (u = x * d, v = y * d), as app/alert_picture.py. The other team is drawn in our frame.
Rules (fixed before the report was looked at; the values and why are in the wiki page):
  * a second counts for our shape when 7 or more of our points are seen (app.team_tactics.MIN_PLAYERS) after merging doubles (1.5 m) and dropping the other team's keeper read as ours
    (rule A10 of wiki/team-role-exclusion-1122.md: in u >= L/2 - 24.5, |v| <= 12, the most advanced of our points with no other of our points within 10 m);
  * our own keeper: app.goalkeeper.without_goalkeeper (deepest player near the own goal line and behind the rest); the same for the other team in its own frame;
  * lines: the outfield players sorted by depth and cut into thirds (as app.team_tactics.shape); heights are metres from the own goal line;
  * an item whose usable seconds are under 25 % of the half is not judged; a stretch (third of the half) under 25 % of its own seconds is shown as "자료 부족";
  * names: only from the typed line-up, only by place (formation line and left-to-right order), only in seconds with exactly as many outfield points as the line-up has; never by track.
"""
import json
import math
import os
import statistics
import time
from pathlib import Path

from app.bench_view import SESSION, current_match as _bench_current_match, live_session
from app.coach_feedback import CoachFeedback, _is_alert
from app.goalkeeper import without_goalkeeper
from app.halftime_accumulator import ENTRY_DEPTH, ENTRY_GAP, match_slots, merge_doubles
from app.opponent_summary import NOT_JUDGED, add_second as add_opponent_second, new_opp, summary as opponent_summary
from app.team_tactics import MIN_PLAYERS

SHARE_MIN = 0.25            # an item / a stretch needs this share of its seconds usable
MINUTE_MIN = 15             # usable seconds a minute needs to get a point on the graph
OPP_MAX = 11                # more of their points than this is a colour mix-up (app/opponent_summary.py)
A10_FROM_GOAL, A10_HALF_WIDTH, A10_ALONE = 24.5, 12.0, 10.0
LOOK_BEFORE, LOOK_AFTER = 2.0, 0.6     # the positions row of an alert (app/alert_picture.py)
GOAL_TAG_SAME = 15.0        # a goal tag within this many seconds of a goal on the score board is the same goal (app/replay_routes.py)
FIELD_SLOTS = 10            # outfield slots when no line-up says otherwise (11 a side)
SLOT_SECONDS = 30           # seconds with exactly the line-up's outfield count a stretch needs before the places (and names) are drawn

# rules of the suggestions for the second half: threshold, the value suggested, and the per-rule text (wiki/features/halftime-report-1124.md, 4)
DROP_MIN = 5.0              # m: the back line of the last stretch lower than the first by this much
GAP_MAX = 18.0              # m: mean distance between two lines (app/halftime_report.GAP_FAR)
GAP_TARGET = 15.0           # m: the upper end of 10-15 m between lines (wiki/research-position-metrics.md)
SIDE_DIFF = 15.0            # %p: our (left - right) differs from the other team's (left - right) by this much; both teams lean to the camera side because far players are missed
SWING = 20.0                # m: a swing of the per-minute back line this large counts as a clear change (only for choosing the lines of "한눈에")
LONG_SHARE, LONG_TARGET = 0.5, 0.4     # team length >= L/2 is "long" (app/opponent_summary.py); the suggestion draws 0.4 L
MAX_SUGGESTIONS = 3

KIND_NAMES = {'conceded_run': '상대 침투 허용', 'line_drop': '수비 줄 내려앉음', 'run': '우리 침투', 'box_attack': '박스 침투', 'isolated': '앞선 선수 고립', 'gap_wide': '줄 간격 벌어짐'}
EVENT_TAGS = {'shot_ours': '우리 슛', 'shot_theirs': '상대 슛', 'goal_ours': '우리 골', 'goal_theirs': '상대 골', 'corner_ours': '우리 코너킥', 'corner_theirs': '상대 코너킥'}
STRETCH = ['초', '중', '후']
SIDE = ['왼쪽', '가운데', '오른쪽']
NO_DATA = '자료 부족으로 판단하지 않음'

# ---- places: the one table of position abbreviations ---------------------------------------------------------------------------------
# Per formation, the outfield lines from the back, each line from LEFT to RIGHT as seen by our team facing the goal it attacks (v < 0 is left; not the top or bottom of
# the screen). A line-up file uses these same codes; a shape that is not here gets no abbreviation and no name (dots only).
FORMATIONS = {
    '4-2-3-1': [['LB', 'LCB', 'RCB', 'RB'], ['LDM', 'RDM'], ['LW', 'AM', 'RW'], ['ST']],
    '4-4-2': [['LB', 'LCB', 'RCB', 'RB'], ['LM', 'LCM', 'RCM', 'RM'], ['LS', 'RS']],
    '4-3-3': [['LB', 'LCB', 'RCB', 'RB'], ['LCM', 'CM', 'RCM'], ['LW', 'ST', 'RW']],
    '4-1-4-1': [['LB', 'LCB', 'RCB', 'RB'], ['DM'], ['LM', 'LCM', 'RCM', 'RM'], ['ST']],
    '4-4-1-1': [['LB', 'LCB', 'RCB', 'RB'], ['LM', 'LCM', 'RCM', 'RM'], ['AM'], ['ST']],
    '4-5-1': [['LB', 'LCB', 'RCB', 'RB'], ['LM', 'LCM', 'CM', 'RCM', 'RM'], ['ST']],
    '4-3-2-1': [['LB', 'LCB', 'RCB', 'RB'], ['LCM', 'CM', 'RCM'], ['LAM', 'RAM'], ['ST']],
    '3-5-2': [['LCB', 'CB', 'RCB'], ['LWB', 'LCM', 'CM', 'RCM', 'RWB'], ['LS', 'RS']],
    '3-4-3': [['LCB', 'CB', 'RCB'], ['LM', 'LCM', 'RCM', 'RM'], ['LW', 'ST', 'RW']],
    '3-4-1-2': [['LCB', 'CB', 'RCB'], ['LM', 'LCM', 'RCM', 'RM'], ['AM'], ['LS', 'RS']],
    '3-4-2-1': [['LCB', 'CB', 'RCB'], ['LM', 'LCM', 'RCM', 'RM'], ['LAM', 'RAM'], ['ST']],
    '5-3-2': [['LWB', 'LCB', 'CB', 'RCB', 'RWB'], ['LCM', 'CM', 'RCM'], ['LS', 'RS']],
    '5-4-1': [['LWB', 'LCB', 'CB', 'RCB', 'RWB'], ['LM', 'LCM', 'RCM', 'RM'], ['ST']],
}
NAME_NOTE = '이름은 선발 라인업의 자리 기준입니다. 교체와 자리 바꿈은 반영되지 않습니다.'
ROLE_NOTE = '자리는 평균 위치로 나눈 것입니다.'


def _clean(value, limit):
    return ''.join(ch for ch in value if ch >= ' ').strip()[:limit] if isinstance(value, str) else ''


def read_lineup(directory, session):
    """The typed line-up as places (see places()), or None when there is no usable file."""
    for path in (Path(directory) / 'service' / 'lineup' / f'{session}.json', Path(directory) / 'service' / 'lineup.json'):
        try:
            if path.stat().st_size > 20000:
                continue
            data = json.loads(path.read_text(encoding='utf-8-sig'))       # a file saved by Notepad starts with a byte-order mark
        except (OSError, ValueError):
            continue
        if isinstance(data, dict) and isinstance(data.get('players'), list):
            return places(data)
    return None


def places(data):
    """{'formation', 'groups': [[{'role', 'name'}] left to right] back line first, 'field', 'unknown': [roles of the file not in the formation]} or None for a formation
    that is not in FORMATIONS. A place whose code is not in the file keeps its code and no name."""
    formation = _clean(data.get('formation'), 12)
    rows = FORMATIONS.get(formation)
    if not rows:
        return None
    names = {}
    for item in data['players'][:18]:
        if isinstance(item, dict):
            role = _clean(item.get('role'), 6).upper()
            if role and role != 'GK':
                names[role] = _clean(item.get('name'), 20)
    codes = {r for row in rows for r in row}
    return {'formation': formation, 'groups': [[{'role': r, 'name': names.get(r, '')} for r in row] for row in rows], 'field': len(codes),
            'unknown': sorted(r for r in names if r not in codes)}


def shape_of(outfield, gaps_for=(3, 4)):
    """A formation read from mean places without a line-up: the points sorted by depth are cut at the largest depth gaps into 3 (then 4) lines; the line sizes must
    make a formation of FORMATIONS. Returns its name or None."""
    us = sorted(p[0] for p in outfield)
    for lines in gaps_for:
        if len(us) < lines:
            continue
        cuts = sorted(sorted(range(1, len(us)), key=lambda i: us[i] - us[i - 1])[-(lines - 1):])
        sizes = [b - a for a, b in zip([0] + cuts, cuts + [len(us)])]
        name = '-'.join(str(x) for x in sizes)
        if name in FORMATIONS:
            return name
    return None


def assign_places(outfield, sizes):
    """Outfield points [(u, v)] and the line sizes of the formation -> [(group, index left to right)] per point (same order as given), or None when the count differs.
    Left to right = v from negative to positive = from our left to our right facing the goal we attack."""
    if len(outfield) != sum(sizes):
        return None
    order = sorted(range(len(outfield)), key=lambda i: outfield[i][0])
    out = [None] * len(outfield)
    start = 0
    for g, size in enumerate(sizes):
        members = sorted(order[start:start + size], key=lambda i: outfield[i][1])
        for k, i in enumerate(members):
            out[i] = (g, k)
        start += size
    return out


def slot_dots(slots, slot_seconds, lineup, length):
    """The mean place of each outfield role slot in a stretch -> [{'u', 'v', 'line' 0 back / 1 middle / 2 front, 'role', 'name'}], or None.
    A slot needs to be filled in a quarter of the stretch's seconds. With a line-up the dots must be exactly its outfield count: they are put into its formation lines by
    depth and given the codes (and names) left to right. Without a line-up (or a count that differs) the formation is read from the dots (shape_of) and only codes are given;
    a shape not in FORMATIONS gives no code."""
    if slot_seconds < SLOT_SECONDS:
        return None
    outfield = [(acc[0] / acc[2], acc[1] / acc[2]) for acc in slots.values() if acc[2] >= SHARE_MIN * slot_seconds]   # outfield slots already (keeper left out per second)
    if len(outfield) < MIN_PLAYERS - 1:
        return None
    if lineup and len(outfield) == lineup['field']:
        groups, named = lineup['groups'], True
    else:
        shape = shape_of(outfield)
        groups, named = ([[{'role': r, 'name': ''} for r in row] for row in FORMATIONS[shape]] if shape else None), False
    placed = assign_places(outfield, [len(g) for g in groups]) if groups else None
    dots = []
    if placed:
        last = len(groups) - 1
        for (u, v), (g, k) in zip(outfield, placed):
            place = groups[g][k]
            dots.append({'u': _r(u), 'v': _r(v), 'line': 0 if g == 0 else 2 if g == last else 1, 'role': place['role'], 'name': place['name'] if named else ''})
        return dots
    order = sorted(range(len(outfield)), key=lambda i: outfield[i][0])
    n = len(outfield)
    for rank, i in enumerate(order):
        dots.append({'u': _r(outfield[i][0]), 'v': _r(outfield[i][1]), 'line': 0 if rank < n // 3 else 2 if rank >= n - n // 3 else 1, 'role': '', 'name': ''})
    return dots


# ---- reading the records ----------------------------------------------------------------------------------------------------------------
def _lines(path):
    try:
        with open(path, encoding='utf-8') as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    value = json.loads(line)
                except ValueError:
                    value = None
                yield value if isinstance(value, dict) else None
    except OSError:
        return


RUN_JUMP = 30.0        # s: a heartbeat whose wall - time moves by more than this belongs to a new run of the analysis (a restart takes about a minute)


def read_position_runs(path):
    """-> [{'header', 'rows': [(t, direction, team, other)], 'halves': [(t, direction)]}], one per header line. Every run of the analysis (a start, a restart) writes its own
    header and counts its time from 0 again; its direction is the one of its own header (turned by its 'half' lines). Lines going back in time inside a run are skipped."""
    runs, direction, last, switched = [], 1, None, False
    for row in _lines(path) if path else []:
        if row is None:
            continue
        if row.get('type') == 'header':
            if not switched:          # after the half switch the second half keeps the switch's direction (as app/halftime_accumulator.py)
                direction = int(row['direction']) if row.get('direction') in (1, -1) else (direction if runs else 1)
            runs.append({'header': row, 'rows': [], 'halves': []})
            last = None
        elif not runs or not isinstance(row.get('time'), (int, float)):
            continue
        elif row.get('type') == 'half':
            switched = True
            direction = int(row['direction']) if row.get('direction') in (1, -1) else -direction
            runs[-1]['halves'].append((float(row['time']), direction))
        elif row.get('type') == 'second':
            t = float(row['time'])
            if last is not None and t <= last:
                continue
            last = t
            pts = lambda key: [(p[0], float(p[1]), float(p[2])) for p in row.get(key, []) if isinstance(p, (list, tuple)) and len(p) >= 3]
            runs[-1]['rows'].append((t, direction, pts('team'), pts('other')))
    return runs


def merge_runs(runs, shifts=None):
    """Runs -> (header or None, rows, halves) on one time line: run k moved by shifts[k] seconds (0 when not given). Rows not after the last kept one are skipped."""
    header, rows, halves, last = None, [], [], None
    for k, run in enumerate(runs):
        header = header or run['header']
        shift = (shifts[k] if shifts and k < len(shifts) else 0.0) or 0.0
        halves += [(t + shift, d) for t, d in run['halves']]
        for t, d, team, other in run['rows']:
            t += shift
            if last is not None and t <= last:
                continue
            last = t
            rows.append((t, d, team, other))
    if runs:
        header = runs[-1]['header']           # the newest run's pitch size and teams
    return header, rows, halves


def read_positions(path):
    """-> (header or None, [(t, direction, team, other)], [(t, direction) of 'half' rows]), all runs on their own times (see read_position_runs)."""
    return merge_runs(read_position_runs(path))


def alert_runs(alert_rows):
    """alerts.jsonl rows -> [{'numbers': [row numbers], 'offset': median wall - time of its heartbeats or None}], one per run of the analysis. A restart before the kick-off
    moves positions.jsonl to the archive but not alerts.jsonl, so the warm-up run and the new run share this file and must not share one offset."""
    # A new run is seen at a heartbeat whose wall - time differs from the one before by more than RUN_JUMP (the new run counts from 0 again). Rows without a wall belong to
    # the run of the heartbeat above them in the file (alert rows are not always written in time order).
    runs, last_off = [], None
    for number, r in enumerate(alert_rows):
        if not r or not isinstance(r.get('time'), (int, float)):
            continue
        off = r['wall'] - float(r['time']) if isinstance(r.get('wall'), (int, float)) else None
        if not runs or (off is not None and last_off is not None and abs(off - last_off) > RUN_JUMP):
            runs.append({'numbers': [], 'diffs': []})
        runs[-1]['numbers'].append(number)
        if off is not None:
            runs[-1]['diffs'].append(off)
            last_off = off
    return [{'numbers': r['numbers'], 'offset': statistics.median(r['diffs']) if r['diffs'] else None} for r in runs]


def clock_offset(alert_rows):
    """Median of wall - time over the heartbeats of the newest run (clock seconds -> analysis seconds), or None."""
    runs = [r for r in alert_runs(alert_rows) if r['offset'] is not None]
    return runs[-1]['offset'] if runs else None


def line_up_runs(position_runs, alert_rows):
    """The position runs matched to the newest runs of alerts.jsonl (the older alert runs are warm-ups whose positions went to the archive).
    -> (shifts per position run, offset of the first position run, {alert row number: shift} for the rows of the matched alert runs)."""
    found = alert_runs(alert_rows)
    n = len(position_runs)
    matched = found[-n:] if n and found else []
    matched = [None] * (n - len(matched)) + matched
    base = next((a['offset'] for a in matched if a and a['offset'] is not None), None)
    shifts, numbers, end = [], {}, None
    for k, (run, a) in enumerate(zip(position_runs, matched)):
        if a and a['offset'] is not None and base is not None:
            shift = a['offset'] - base
        elif end is not None and run['rows']:
            shift = end + 1.0 - run['rows'][0][0]           # no heartbeat in that run: right after the run before
        else:
            shift = 0.0
        shifts.append(shift)
        if run['rows']:
            end = run['rows'][-1][0] + shift
        for number in (a['numbers'] if a else []):
            numbers[number] = shift
    if not position_runs and found:
        numbers = {number: 0.0 for number in found[-1]['numbers']}
    return shifts, base, numbers


def read_goals(path, offset, by_clock=False):
    """score.jsonl -> [(analysis second or None, 'ours' | 'opp')] after the undos (an undo takes back the latest goal).
    by_clock: the server time of the press comes first (several runs of the analysis, whose own seconds all start at 0)."""
    goals = []
    for row in _lines(path):
        if row is None:
            continue
        if row.get('kind') == 'goal' and row.get('team') in ('ours', 'opp'):
            at = (row.get('analysis') or {}).get('positions_time') if isinstance(row.get('analysis'), dict) else None
            if by_clock and offset is not None and isinstance(row.get('t'), (int, float)):
                at = None
            if not isinstance(at, (int, float)) and offset is not None and isinstance(row.get('t'), (int, float)):
                at = row['t'] - offset
            goals.append((float(at) if isinstance(at, (int, float)) else None, row['team']))
        elif row.get('kind') == 'undo' and goals:
            goals.pop()
    return goals


def read_tags(path, offset):
    """tags.jsonl -> {id: (analysis second, kind)} after the deletes; nothing without an offset."""
    tags = {}
    if offset is None:
        return {}
    for row in _lines(path):
        if row is None:
            continue
        if row.get('op') == 'add' and isinstance(row.get('epoch'), (int, float)):
            tags[row.get('id')] = (row['epoch'] - offset, row.get('kind'))
        elif row.get('op') == 'delete':
            tags.pop(row.get('id'), None)
    return tags


# ---- one second -------------------------------------------------------------------------------------------------------------------------
def drop_other_keeper(ours, length):
    """Rule A10: the most advanced of our points inside u >= L/2 - 24.5, |v| <= 12 with no other of our points within 10 m is the other team's keeper."""
    found = [p for p in ours if p[0] >= length / 2 - A10_FROM_GOAL and abs(p[1]) <= A10_HALF_WIDTH
             and all(math.hypot(p[0] - q[0], p[1] - q[1]) >= A10_ALONE for q in ours if q is not p)]
    if not found:
        return ours
    keeper = max(found, key=lambda p: p[0])
    return [p for p in ours if p is not keeper]


def lines_of(points, length):
    """Points [(u, v)] in the team's own frame -> {'outfield', 'def', 'mid', 'att' (m from the own goal line), 'width', 'length', 'centre_v'} or None (fewer than 7)."""
    if len(points) < MIN_PLAYERS:
        return None
    outfield, _ = without_goalkeeper(points, key=lambda p: p[0], pitch_length=length)
    us = [p[0] for p in outfield]
    vs = sorted(p[1] for p in outfield)
    n = len(outfield)
    cut1, cut2 = n // 3, n - n // 3
    groups = [us[:cut1] or us[:1], us[cut1:cut2] or us[:1], us[cut2:] or us[-1:]]
    means = [sum(g) / len(g) + length / 2 for g in groups]
    pct = lambda s: vs[min(n - 1, max(0, int(round(s * (n - 1)))))]
    # width: the full spread of the outfield players seen in this second (the coach's 'team width'); width_p: 10th to 90th percentile (app.team_tactics.shape)
    return {'outfield': outfield, 'def': means[0], 'mid': means[1], 'att': means[2], 'width': vs[-1] - vs[0], 'width_p': pct(0.9) - pct(0.1), 'length': us[-1] - us[0],
            'centre_v': sum(vs) / n, 'vmin': vs[0], 'vmax': vs[-1]}


def lane(v, width):
    return 0 if v < -width / 6 else 2 if v > width / 6 else 1


# ---- the report -------------------------------------------------------------------------------------------------------------------------
def _mmss(seconds):
    seconds = max(0, int(round(seconds)))
    return f'{seconds // 60}분 {seconds % 60:02d}초' if seconds % 60 else f'{seconds // 60}분'


def _minutes(seconds):
    return f'{seconds / 60:.0f}분' if seconds >= 60 else f'{int(seconds)}초'


def _r(x):
    return round(x, 1)


def _mean(values):
    return sum(values) / len(values) if values else None


def half_range(rows, halves, tags, half, end_s, offset):
    """(start, end, how the end was found) of the half in analysis seconds."""
    if not rows:
        return None, None, 'none'
    first, last = rows[0][0], rows[-1][0]
    marks = sorted(tags.values())
    if half == 1:
        # only from the "전반 시작" mark: the analysis is started during the warm-up, and nothing before the kick-off may count (the latest mark wins, a re-press after a false start)
        starts = [t for t, k in marks if k == 'start_h1' and first - 5 <= t <= last]
        if not starts:
            return None, None, 'not_started'
        start = starts[-1]
        if end_s is not None and float(end_s) <= start:
            end_s = None
        halves = [x for x in halves if x[0] > start]
        if end_s is not None:
            return start, min(float(end_s), last), 'button'
        # the "전반 끝" mark comes before the switch to the second half: 2026-11-25 rehearsal, a first half of 12:02 became 19:44 once the second half was
        # started, because the switch (made after the half-time break) was taken as the end when the analysis had been started several times
        limit = halves[0][0] if halves else last
        end_tags = [t for t, k in marks if k == 'end_h1' and start < t <= limit]
        if end_tags:
            return start, end_tags[0], 'tag'
        if halves:
            return start, halves[0][0], 'switch'
        return start, last, 'running'
    switch = halves[0][0] if halves else None
    start = next((t for t, k in marks if k == 'start_h2' and first <= t <= last), switch)
    if start is None:
        return None, None, 'none'
    end_tag = next((t for t, k in marks if k == 'end_h2' and start < t <= last), None)
    return (start, end_tag, 'tag') if end_tag else (start, last, 'running')


def suggestions(m, length, width):
    """The second-half suggestions from the half's numbers. m: {'def_first', 'def_last' (None when that stretch is short), 'gap_dm', 'gap_ma', 'left', 'right', 'length', 'usable_ok'}.
    Returns at most three [{key, text, evidence, ratio, draw}] in the order of ratio = value / threshold (largest first). Nothing when a rule's number stays under its threshold."""
    out = []
    if not m.get('usable_ok'):
        return out
    if m.get('def_first') is not None and m.get('def_last') is not None and m['def_first'] - m['def_last'] >= DROP_MIN:
        drop = m['def_first'] - m['def_last']
        out.append({'key': 'raise_line', 'ratio': drop / DROP_MIN, 'text': f'수비 줄을 초반 높이({m["def_first"]:.0f} m)까지 함께 올리기',
                    'evidence': f'수비 줄 초반 {m["def_first"]:.0f} m → 후반부 {m["def_last"]:.0f} m ({drop:.0f} m 내려옴, 기준 {DROP_MIN:.0f} m)',
                    'draw': {'group': 'def', 'du': drop}})
    for key, gap, group, word in (('close_dm', m.get('gap_dm'), 'mid', '미드필드 줄을 수비 줄 쪽으로'), ('close_ma', m.get('gap_ma'), 'att', '공격 줄을 미드필드 쪽으로')):
        if gap is not None and gap >= GAP_MAX:
            out.append({'key': key, 'ratio': gap / GAP_MAX, 'text': f'{word} {gap - GAP_TARGET:.0f} m 당겨 간격 {GAP_TARGET:.0f} m',
                        'evidence': f'줄 사이 평균 {gap:.0f} m (기준 {GAP_MAX:.0f} m 이상이면 제안)', 'draw': {'group': group, 'du': -(gap - GAP_TARGET)}})
    if None not in (m.get('left'), m.get('right'), m.get('opp_left'), m.get('opp_right')):
        lean = (m['left'] - m['right']) - (m['opp_left'] - m['opp_right'])      # our lean beyond the other team's (the camera side shows in both)
        if abs(lean) >= SIDE_DIFF:
            empty = 2 if lean > 0 else 0
            shift = width / 6 * (-1 if empty == 0 else 1)
            out.append({'key': 'use_side', 'ratio': abs(lean) / SIDE_DIFF, 'text': f'비어 있던 {SIDE[empty]}도 함께 쓰기',
                        'evidence': f'왼쪽-오른쪽 차 우리 {m["left"] - m["right"]:+.0f}%p, 상대 {m["opp_left"] - m["opp_right"]:+.0f}%p (기준 {SIDE_DIFF:.0f}%p)',
                        'draw': {'group': 'all', 'dv': shift}})
    if m.get('length') is not None and m['length'] >= LONG_SHARE * length:
        target = LONG_TARGET * length
        out.append({'key': 'shorter', 'ratio': m['length'] / (LONG_SHARE * length), 'text': f'위아래 길이를 {target:.0f} m 안으로 줄이기',
                    'evidence': f'팀 길이 평균 {m["length"]:.0f} m (기준 {LONG_SHARE * length:.0f} m 이상)', 'draw': {'group': 'att', 'du': -(m['length'] - target)}})
    out.sort(key=lambda s: -s['ratio'])
    return out[:MAX_SUGGESTIONS]


LOOK_FOR = {'conceded_run': '수비 뒷공간을 보세요', 'line_drop': '수비 줄 높이를 보세요', 'run': '같이 뛰어드는지 보세요', 'box_attack': '박스 안 자리를 보세요',
            'isolated': '앞선 선수 지원을 보세요', 'gap_wide': '줄 사이 간격을 보세요'}


def highlights(candidates, proposals=()):
    """The three lines of "한눈에" as [{'text' (a coach's sentence, at most 40 characters), 'evidence' (the numbers, small)}].
    The first second-half suggestion (block 7) comes first when there is one; then the judged candidates with the largest score (score = the item's change divided by the size
    that counts as a clear change, see each block). The per-minute lowest and highest back line is not a candidate (attack and defence are mixed in it)."""
    out = [{'text': p['text'], 'evidence': p['evidence']} for p in list(proposals)[:1]]
    skip = {'raise_line': 'thirds'}.get(proposals[0]['key'] if proposals else None)     # the same fact twice is one line
    ranked = sorted((c for c in candidates if c and c.get('score') is not None and c.get('glance') and c.get('key') != skip), key=lambda c: -c['score'])
    for c in ranked:
        if len(out) >= 3:
            break
        out.append({'text': c['glance'], 'evidence': c.get('glance_ev', '')})
    return out


def build(directory, session, half=1, end_s=None, final=False, clock=time.time):
    started = time.perf_counter()
    directory = Path(directory)
    folder = directory / 'alerts' / session
    position_runs = read_position_runs(folder / 'positions.jsonl' if (folder / 'positions.jsonl').is_file() else None)
    raw_alerts = list(_lines(folder / 'alerts.jsonl'))
    shifts, offset, alert_shift = line_up_runs(position_runs, raw_alerts)
    header, rows, halves = merge_runs(position_runs, shifts)
    # only the alert rows of the runs whose positions are here, on the same time line (a warm-up run before a restart keeps its rows in alerts.jsonl; its times start at 0 too)
    alert_rows = [({**r, 'time': r['time'] + alert_shift[i]} if i in alert_shift and isinstance(r.get('time'), (int, float)) else None) if r else None
                  for i, r in enumerate(raw_alerts)]
    if len(position_runs) > 1:
        end_s = None                          # the button's end is a second of one run; with several runs the end mark (written by the same button) is used
    tags = read_tags(directory / 'analyst-tags' / 'tags.jsonl', offset)
    word = '전반' if half == 1 else '후반'
    report = {'session': session, 'half': half, 'word': word, 'generated_at': clock(), 'blocks': {}}
    if header is None or not rows:
        report.update({'state': 'empty', 'status_text': f'{word} 위치 기록이 아직 없습니다.'})
        report['blocks'] = {k: {'judged': False, 'text': '기록에 없음', 'evidence': '위치 기록이 없습니다.'} for k in ('glance', 'thirds', 'line', 'sides', 'alerts', 'opponent', 'next')}
        report['build_seconds'] = round(time.perf_counter() - started, 3)
        return report
    length, width = float(header.get('pitch_length', 89.0)), float(header.get('pitch_width', 62.0))
    start, end, how = half_range(rows, halves, tags, half, end_s, offset)
    if start is None:
        text = f'{word} 시작을 누르면 집계가 시작됩니다'
        report.update({'state': 'not_started', 'status_text': text})
        report['blocks'] = {}
        report['build_seconds'] = round(time.perf_counter() - started, 3)
        return report
    running = how == 'running' and not final
    span = max(1.0, end - start)
    cuts = [start + span * i / 3 for i in range(4)]
    lineup = read_lineup(directory, session)
    if half == 2 and not halves:
        # the switch was pressed but the live run wrote no 'half' line (it was not running, or not yet): the second half uses the direction the server sent it
        # (<session>/control.jsonl, app/halftime_report.switch_second_half), as the band's sums and the bench mini map do
        sent = next((int(r['direction']) for r in reversed(list(_lines(folder / 'control.jsonl'))) if r and r.get('cmd') == 'second_half' and r.get('direction') in (1, -1)), None)
        if sent is not None:
            rows = [(t, sent if t >= start else d, team, other) for t, d, team, other in rows]
    direction_now = rows[-1][1]

    seconds = [r for r in rows if start <= r[0] <= end]
    total = len(seconds)
    third_n = [0, 0, 0]
    usable = [[], [], []]                  # our shape per stretch
    opp_usable = [[], [], []]
    lanes_ours, lanes_opp = [0, 0, 0], [0, 0, 0]
    minutes = {}
    slots = [dict() for _ in range(3)]     # stretch -> {slot: [su, sv, n]}
    n_slots = lineup['field'] if lineup else FIELD_SLOTS
    ref = [[0.0, 0.0, 0] for _ in range(n_slots)]
    slot_seconds = [0, 0, 0]
    opp_bucket = {'n': 0, 'opp': new_opp()}
    entries, entry_open, entry_last = [], False, -99.0
    seen = {}
    for t, d, team, other in seconds:
        i = min(2, int((t - start) / span * 3)) if span > 0 else 0
        third_n[i] += 1
        ours_raw = [(x * d, y * d) for _, x, y in merge_doubles(team)]
        theirs = [(x * d, y * d) for _, x, y in merge_doubles(other)]
        seen[t] = (ours_raw, theirs)
        opp_bucket['n'] += 1
        add_opponent_second(opp_bucket['opp'], ours_raw, theirs, length, width)
        zone = [v for u, v in theirs if u <= -length / 2 + ENTRY_DEPTH]
        inside = bool(zone)
        if inside and not entry_open and t - entry_last >= ENTRY_GAP:
            across = sum(zone) / len(zone)
            entries.append(0 if across < -width / 6 else 2 if across > width / 6 else 1)
            entry_last = t
        entry_open = inside
        ours = drop_other_keeper(ours_raw, length)
        s = lines_of(ours, length)
        if s:
            usable[i].append(s)
            minutes.setdefault(int((t - start) // 60), []).append(s['def'])
            for _u, v in s['outfield']:
                lanes_ours[lane(v, width)] += 1
            # outfield role slots (the keeper is left out: our own keeper is in our points in under 5 % of the seconds, so an 11th slot was filled by someone else):
            # made from the first second with exactly the line-up's outfield count, then every seen outfield player goes to the closest free slot (app/halftime_accumulator.match_slots)
            field = s['outfield']
            if any(r[2] == 0 for r in ref):
                if len(field) == n_slots:
                    for r, (u, v) in zip(ref, sorted(field)):
                        r[0], r[1], r[2] = u, v, 1
            else:
                order = match_slots(field, [(r[0] / r[2], r[1] / r[2]) for r in ref])
                slot_seconds[i] += 1
                for (u, v), j in zip(field, order):
                    if j < 0:
                        continue
                    for acc in (ref[j], slots[i].setdefault(j, [0.0, 0.0, 0])):
                        acc[0] += u
                        acc[1] += v
                        acc[2] += 1
        if MIN_PLAYERS <= len(theirs) <= OPP_MAX:
            o = lines_of([(-u, -v) for u, v in theirs], length)
            if o:
                opp_usable[i].append(o)
                for _u, v in o['outfield']:
                    lanes_opp[lane(-v, width)] += 1

    n_usable = sum(len(u) for u in usable)
    n_opp = sum(len(u) for u in opp_usable)
    usable_ok = total > 0 and n_usable >= SHARE_MIN * total
    opp_ok = total > 0 and n_opp >= SHARE_MIN * total
    sample = f'우리 7명 이상 보인 시간 {_minutes(total)} 중 {_minutes(n_usable)}'

    # ---- 2. the shape in three stretches -------------------------------------------------------------------------------------------------
    def stretch_means(group, n_sec):
        if not group or len(group) < SHARE_MIN * max(1, n_sec):
            return None
        return {k: _r(_mean([g[k] for g in group])) for k in ('def', 'mid', 'att', 'width', 'width_p', 'length', 'centre_v', 'vmin', 'vmax')}
    stretches = []
    for i in range(3):
        means = stretch_means(usable[i], third_n[i])
        dots = slot_dots(slots[i], slot_seconds[i], lineup, length) if means else None
        stretches.append({'name': STRETCH[i], 'from_text': _mmss(cuts[i] - start), 'to_text': _mmss(cuts[i + 1] - start), 'seconds': third_n[i], 'usable': len(usable[i]),
                          'means': means, 'dots': dots, 'dot_seconds': slot_seconds[i]})
    judged = [s for s in stretches if s['means']]
    block2 = {'judged': usable_ok and len(judged) >= 2, 'stretches': stretches, 'evidence': sample}
    if block2['judged']:
        a, b = judged[0], judged[-1]
        delta = b['means']['def'] - a['means']['def']
        block2['delta'] = _r(delta)
        if abs(delta) < 2:
            block2['text'] = f'수비 줄 높이는 {word} 내내 비슷했습니다'
        else:
            block2['text'] = f'수비 줄이 {word} 끝으로 갈수록 {abs(delta):.0f} m {"내려왔습니다" if delta < 0 else "올라갔습니다"}'
        block2['evidence'] = '수비 줄 ' + ' · '.join(f'{s["name"]} {s["means"]["def"]:.0f} m' if s['means'] else f'{s["name"]} 부족' for s in stretches) + f' ({sample})'
        block2['score'] = abs(delta) / DROP_MIN
        block2['names'] = any(d['name'] for s in stretches for d in (s['dots'] or []))
        block2['roles'] = any(d['role'] for s in stretches for d in (s['dots'] or []))
    else:
        block2.update({'text': NO_DATA})

    # ---- 3. the back line per minute -------------------------------------------------------------------------------------------------------
    points = [{'minute': k, 'def': _r(_mean(v))} for k, v in sorted(minutes.items()) if len(v) >= MINUTE_MIN]
    offset_end = end - start
    marks = []
    goals = read_goals(folder / 'score.jsonl', offset, by_clock=len(position_runs) > 1)
    goal_times = [(t, team) for t, team in goals if t is not None and start <= t <= end]
    for t, team in goal_times:
        marks.append({'at': _r((t - start) / 60), 'kind': 'goal_ours' if team == 'ours' else 'goal_theirs', 'label': '우리 골' if team == 'ours' else '상대 골'})
    for t, kind in tags.values():
        if kind in EVENT_TAGS and start <= t <= end:
            team = 'ours' if kind.endswith('_ours') else 'opp'
            if kind.startswith('goal_') and any(abs(t - g) <= GOAL_TAG_SAME and gt == team for g, gt in goal_times):
                continue
            marks.append({'at': _r((t - start) / 60), 'kind': kind, 'label': EVENT_TAGS[kind]})
    minute_count = int(offset_end // 60) + 1
    block3 = {'judged': usable_ok and len(points) >= 2, 'points': points, 'marks': sorted(marks, key=lambda m: m['at']), 'minutes': minute_count}
    if block3['judged']:
        low = min(points, key=lambda p: p['def'])
        high = max(points, key=lambda p: p['def'])
        block3['text'] = f'수비 줄 가장 낮음 {low["minute"]}분대 {low["def"]:.0f} m · 가장 높음 {high["minute"]}분대 {high["def"]:.0f} m'
        block3['evidence'] = f'1분마다 평균 (우리 7명 이상 {MINUTE_MIN}초 넘게 보인 분 {len(points)}개 / {minute_count}개)'
        block3['score'] = (high['def'] - low['def']) / SWING
    else:
        block3.update({'text': NO_DATA, 'evidence': sample})

    # ---- 4. left, centre, right -----------------------------------------------------------------------------------------------------------
    share = lambda c: [_r(100.0 * x / sum(c)) for x in c] if sum(c) else None
    ours_share, opp_share = share(lanes_ours), share(lanes_opp)
    block4 = {'judged': usable_ok and ours_share is not None, 'ours': ours_share, 'theirs': opp_share if opp_ok else None}
    if block4['judged']:
        ours_lean = ours_share[0] - ours_share[2]
        opp_lean = opp_share[0] - opp_share[2] if opp_ok else None
        lean = ours_lean - opp_lean if opp_lean is not None else None
        side = SIDE[0 if ours_lean > 0 else 2]
        if lean is not None and abs(lean) >= SIDE_DIFF:
            block4['text'] = f'상대보다 우리가 {SIDE[0 if lean > 0 else 2]}에 더 몰렸습니다'
        elif abs(ours_lean) >= SIDE_DIFF and opp_lean is not None and abs(opp_lean) >= SIDE_DIFF and ours_lean * opp_lean > 0:
            block4['text'] = f'두 팀 모두 {side}에 많이 보였습니다(카메라 쪽 치우침 가능)'
        elif abs(ours_lean) >= SIDE_DIFF:
            block4['text'] = f'우리는 {side}에 더 많이 섰습니다'
        else:
            block4['text'] = '우리는 좌우 고르게 섰습니다'
        block4['evidence'] = (f'왼·가운데·오른 우리 {ours_share[0]:.0f}·{ours_share[1]:.0f}·{ours_share[2]:.0f}% ({_minutes(n_usable)}), 상대 '
                              + (f'{opp_share[0]:.0f}·{opp_share[1]:.0f}·{opp_share[2]:.0f}% ({_minutes(n_opp)})' if opp_ok else '판단 안 함'))
        block4['score'] = abs(lean if lean is not None else 0.0) / SIDE_DIFF
        block4['lean'] = lean
    else:
        block4.update({'text': NO_DATA, 'evidence': sample})

    # ---- 5. the alerts -----------------------------------------------------------------------------------------------------------------
    feedback = CoachFeedback(directory)
    kinds = {}
    for number, row in enumerate(alert_rows):
        if not _is_alert(row) or not isinstance(row.get('time'), (int, float)) or not start <= row['time'] <= end:
            continue
        k = row.get('kind') or ''
        entry = kinds.setdefault(k, {'kind': k, 'name': KIND_NAMES.get(k, str(row.get('title') or k)), 'count': 0, 'stretch': [0, 0, 0], 'ok': 0, 'wrong': 0, 'rows': []})
        entry['count'] += 1
        entry['stretch'][min(2, int((row['time'] - start) / span * 3))] += 1
        label = feedback.coach_label(session, number)
        if label in ('ok', 'wrong'):
            entry[label] += 1
        entry['rows'].append((float(row['time']), number))
    ordered = sorted(kinds.values(), key=lambda e: (-e['count'], e['rows'][0][0]))
    times = sorted(seen)
    for e in ordered[:2]:
        best = None
        for t, _number in e['rows']:
            near = [s for s in times if t - LOOK_BEFORE <= s <= t + LOOK_AFTER]
            if near:
                s = near[-1]
                n = len(seen[s][0]) + len(seen[s][1])
                if best is None or n > best[0]:
                    best = (n, t, s)
        if best:
            ours_pts, theirs_pts = seen[best[2]]
            e['moment'] = {'at_text': _mmss(best[1] - start), 'ours': [[_r(u), _r(v)] for u, v in ours_pts], 'theirs': [[_r(u), _r(v)] for u, v in theirs_pts]}
    block5 = {'judged': bool(ordered), 'kinds': [{k: v for k, v in e.items() if k != 'rows'} for e in ordered], 'replay': None}
    if ordered:
        top = ordered[0]
        block5['text'] = f'가장 많이 나온 알림: {top["name"]} {top["count"]}번'
        block5['evidence'] = ' · '.join(f'{e["name"]} {e["count"]}' for e in ordered[:4]) + f' (알림 {sum(e["count"] for e in ordered)}개)'
        block5['score'] = top['count'] / max(1.0, span / 300.0)
    else:
        block5.update({'text': f'{word}에 나온 알림이 없습니다', 'evidence': f'{word} {_minutes(span)} 동안'})

    # ---- 6. the other team ---------------------------------------------------------------------------------------------------------------
    named = None
    if len(entries) >= 4:
        shares = [entries.count(k) / len(entries) for k in range(3)]
        best_side = max(range(3), key=lambda k: shares[k])
        named = best_side if shares[best_side] >= (0.5 if best_side == 1 else 0.45) else -1
    try:
        opp = opponent_summary([opp_bucket], length, width, half, entry_side=named)
    except Exception:                                                     # noqa: BLE001 - the block must not cost the coach the report
        opp = opponent_summary([], half=half)
    opp_stretches = []
    for i in range(3):
        means = stretch_means(opp_usable[i], third_n[i])
        if means:
            means = {**means, 'centre_v': -means['centre_v'], 'vmin': -means['vmax'], 'vmax': -means['vmin']}   # their own frame -> ours
        opp_stretches.append({'name': STRETCH[i], 'means': means, 'usable': len(opp_usable[i]), 'seconds': third_n[i]})
    block6 = {'judged': bool(opp['judged']) and opp_ok, 'summary': opp, 'stretches': opp_stretches}
    if block6['judged']:
        block6['text'] = opp['headline'][0]
        oj = [s for s in opp_stretches if s['means']]
        block6['evidence'] = f'{opp["seen_text"]} (상대 7~11명 보인 시간 {_minutes(n_opp)} / {_minutes(total)})'
        if len(oj) >= 2:
            block6['score'] = abs(oj[-1]['means']['def'] - oj[0]['means']['def']) / DROP_MIN
            block6['glance'] = block6['delta_text'] = f'상대 수비 줄 {oj[0]["name"]} {oj[0]["means"]["def"]:.0f} m → {oj[-1]["name"]} {oj[-1]["means"]["def"]:.0f} m'
    else:
        block6.update({'text': NOT_JUDGED, 'evidence': f'상대 7~11명 보인 시간 {_minutes(n_opp)} / {_minutes(total)} (25% 미만이면 판단 안 함)'})

    # ---- 7. the second half ---------------------------------------------------------------------------------------------------------------
    first_dir = rows[0][1]
    for t, d, _team, _other in rows:
        if t >= start:
            first_dir = d
            break
    next_dir = halves[0][1] if half == 1 and halves else -first_dir
    late = judged[-1] if judged else None
    all_usable = [s for group in usable for s in group]
    metrics = {'usable_ok': usable_ok, 'def_first': judged[0]['means']['def'] if len(judged) >= 2 else None, 'def_last': late['means']['def'] if len(judged) >= 2 else None,
               'gap_dm': _mean([s['mid'] - s['def'] for s in all_usable]), 'gap_ma': _mean([s['att'] - s['mid'] for s in all_usable]),
               'left': ours_share[0] if ours_share else None, 'right': ours_share[2] if ours_share else None, 'length': _mean([s['length'] for s in all_usable]),
               'opp_left': opp_share[0] if opp_share and opp_ok else None, 'opp_right': opp_share[2] if opp_share and opp_ok else None}
    proposals = suggestions(metrics, length, width) if half == 1 else []
    for p in proposals:
        p['base'] = late['means'] if late else None
        p['dots'] = late['dots'] if late else None
    side_word = '오른쪽' if next_dir > 0 else '왼쪽'
    block7 = {'judged': usable_ok, 'items': proposals, 'direction': next_dir,
              'direction_text': f'후반 기준 그림입니다: 우리는 화면 {side_word}으로 공격합니다 (전반과 반대).', 'rules_checked': ['raise_line', 'close_dm', 'close_ma', 'use_side', 'shorter']}
    if not usable_ok:
        block7.update({'text': NO_DATA, 'evidence': sample})
    elif not proposals:
        block7.update({'text': '뚜렷한 문제 없음', 'evidence': f'수비 줄 하락 {DROP_MIN:.0f} m, 줄 간격 {GAP_MAX:.0f} m, 좌우 차 {SIDE_DIFF:.0f}%p, 길이 {LONG_SHARE * length:.0f} m 기준에 못 미침'})
    else:
        block7.update({'text': f'후반에 할 일 {len(proposals)}가지', 'evidence': sample})

    # ---- 1. at a glance ---------------------------------------------------------------------------------------------------------------
    ours_goals = sum(1 for t, team in goals if team == 'ours' and (t is None or (start <= t <= end if half == 1 else t <= end)))
    opp_goals = sum(1 for t, team in goals if team == 'opp' and (t is None or (start <= t <= end if half == 1 else t <= end)))
    def glance_of(key, block):
        """One candidate line of "한눈에": what changed and what to look at (a coach's sentence), the numbers as a small line, and the score that ranks it."""
        if not block or not block.get('judged') or block.get('score') is None:
            return None
        out = {'key': key, 'score': block['score']}
        if key == 'thirds':
            a, b = judged[0]['means']['def'], judged[-1]['means']['def']
            if abs(b - a) < 2:
                return None
            out['glance'] = f'수비 줄이 끝으로 갈수록 {abs(b - a):.0f} m {"내려왔습니다" if b < a else "올라갔습니다"}, 높이를 보세요'
            out['glance_ev'] = f'{judged[0]["name"]} {a:.0f} m → {judged[-1]["name"]} {b:.0f} m (우리 골라인에서)'
        elif key == 'sides':
            lean = block.get('lean')
            if lean is None or abs(lean) < SIDE_DIFF:
                return None
            out['glance'] = f'상대보다 우리가 {SIDE[0 if lean > 0 else 2]}에 몰렸습니다, 반대쪽을 보세요'
            out['glance_ev'] = block['evidence']
        elif key == 'alerts':
            top = ordered[0]
            out['glance'] = f'{top["name"]} 알림이 가장 많았습니다, {LOOK_FOR.get(top["kind"], "그 장면을 보세요")}'
            out['glance_ev'] = f'{top["count"]}번 (초 {top["stretch"][0]} · 중 {top["stretch"][1]} · 후 {top["stretch"][2]})'
        elif key == 'opponent':
            oj = [s for s in block['stretches'] if s['means']]
            a, b = oj[0]['means']['def'], oj[-1]['means']['def']
            if abs(b - a) < 2:
                return None
            out['glance'] = (f'상대 수비 줄이 끝으로 갈수록 {abs(b - a):.0f} m 올라왔습니다, 뒷공간을 보세요' if b > a
                             else f'상대 수비 줄이 끝으로 갈수록 {abs(b - a):.0f} m 내려왔습니다, 앞 공간을 보세요')
            out['glance_ev'] = f'{oj[0]["name"]} {a:.0f} m → {oj[-1]["name"]} {b:.0f} m (상대 골라인에서)'
        return out

    block1 = {'judged': True, 'score': {'ours': ours_goals, 'opp': opp_goals}, 'length_text': _mmss(span),
              'lines': highlights([glance_of('thirds', block2), glance_of('sides', block4), glance_of('alerts', block5), glance_of('opponent', block6)], proposals),
              'stretches': [{'name': s['name'], 'from_text': s['from_text'], 'to_text': s['to_text']} for s in stretches],
              'goals': [m for m in block3['marks'] if m['kind'].startswith('goal')], 'minutes': span / 60}
    block1['text'] = f'{word} {_mmss(span)} · 우리 {ours_goals} : {opp_goals} 상대'
    block1['evidence'] = sample
    if not block1['lines']:
        block1['lines'] = [{'text': '자료가 부족해 고를 것이 없습니다', 'evidence': sample}]

    report.update({'state': 'running' if running else 'final', 'how_end': how, 'start_s': _r(start), 'end_s': _r(end), 'length': length, 'width': width,
                   'direction': first_dir, 'direction_now': direction_now, 'names_note': NAME_NOTE, 'role_note': ROLE_NOTE, 'formation': lineup['formation'] if lineup else None,
                   'status_text': f'{word} 진행 중, {_mmss(span)}까지' if running else f'{word} {_mmss(span)} 전체',
                   'blocks': {'glance': block1, 'thirds': block2, 'line': block3, 'sides': block4, 'alerts': block5, 'opponent': block6, 'next': block7}})
    report['build_seconds'] = round(time.perf_counter() - started, 3)
    return report


def current_match(directory):
    """The match started on /setup: app/bench_view.current_match (one rule for every screen)."""
    return _bench_current_match(directory)


def current_session(directory):
    """The match the page shows when the address names none: app/bench_view.live_session, the rule of the score board."""
    return live_session(directory)


class RichReports:
    """Made again on request; the last result per (session, half, end) is kept while the files have not changed."""
    def __init__(self, directory):
        self.directory = Path(directory)
        self.cache = {}

    def _stamp(self, session):
        out = []
        for path in (self.directory / 'alerts' / session / 'positions.jsonl', self.directory / 'alerts' / session / 'alerts.jsonl', self.directory / 'alerts' / session / 'score.jsonl',
                     self.directory / 'analyst-tags' / 'tags.jsonl'):
            try:
                st = os.stat(path)
                out.append((st.st_size, st.st_mtime_ns))
            except OSError:
                out.append(None)
        coach = self.directory / 'alerts' / 'labels-coach'
        out.append(coach.stat().st_mtime_ns if coach.is_dir() else None)
        return tuple(out)

    def get(self, session, half=1, end_s=None, final=False):
        key = (session, half, end_s, final)
        stamp = self._stamp(session)
        hit = self.cache.get(key)
        if hit and hit[0] == stamp:
            return hit[1]
        report = build(self.directory, session, half, end_s, final)
        self.cache[key] = (stamp, report)
        return report
