"""One small picture per bench alert: which of our players to look at (yellow), the state now (solid lines) and the suggested move (dashed arrows, at most 3).

The live run (scripts/run_live_feedback.py, app/live_feedback.py) writes no coordinates into an alert, so the picture is computed again here from the position
record of the same run (<store>/alerts/<session>/positions.jsonl, one 'second' row per second: our points 'team' and the other team's points 'other', screen metres).
Only what the kind of the alert and the positions of that moment show is drawn:

- line_drop: our back line now (solid) and where it stood within the 10 seconds before (thin line); dashed arrows from the deepest players up to that earlier line,
  which is the base line of the alert ("the line sank N metres in 10 s ... raise it together"). Without the 'retreat_supported' evidence the alert itself withholds
  the instruction, and so does the picture (text only).
- conceded_run: the opponent who ran past our back line in the last 6 s (solid arrow, his path), our back line (solid), and a dashed arrow from our nearest player to
  where the runner is now ("the nearest player follows first"). Without opponent points the runner cannot be found: text only.
- run: our player who ran forward in the last 6 s (yellow, solid arrow of his path) and dashed arrows for up to two teammates behind him, forward to the depth he reached
  ("the other players of the attack line start at the same time").
- box_attack: the penalty area (solid outline), our players in it (yellow) and dashed arrows to the three places the alert names (near post, far post, the back), each
  player to one place by the shortest total distance; when the alert says they already stand spread, no arrows.

Only the kinds in SHOWN are sent (the others failed or could not be put through the video check); their rules stay here for the next check.
Every other kind, and every alert without enough points at its moment, gets no picture and only the short line. Nothing here names a player: the points have no names.

Position map (2026-11-25, type 'position'): the alerts above that get no arrow picture (conceded_run, box_attack, a line_drop without the retreat evidence, run, isolated, gap_wide)
get a plain picture of where both teams stood at that moment, with ONE area marked ("look here", never an instruction: no arrows, no moves):
conceded_run = the space between our back line and our goal line (filled) and the opponents inside it (yellow ring); box_attack = the penalty area of the goal we attack (filled)
and every point inside it (yellow ring); the others = our back line as one solid line. Only the newest position row at or before the alert's time (at most 2 s before) is used.
Without a row, or with fewer than 4 of our points, there is no picture. Coordinates returned are in the team's view, as /api/v1/bench/minimap gives them: u toward the goal our team attacks, v = y * direction.
"""
import itertools
import json
import math
from pathlib import Path

LINES = {   # the one line under the picture (at most 15 characters, coaching words only)
    'line_drop': '수비 줄을 함께 올리세요',
    'line_drop_unconfirmed': '수비선 확인 필요',
    'conceded_run': '가까운 수비 따라붙기',
    'run': '같이 뛰어 들어가세요',
    'box_attack': '두 포스트와 뒤로 나눠 서기',
    'box_attack_spread': '박스 안 자리 지키기',
    'isolated': '앞선 선수 지원하기',
    'gap_wide': '줄 간격 좁히기',
    'no_input': '영상 입력 없음',
    'input_back': '영상 입력 복구',
    'half_switch': '후반 전환',
}
LOOK_BEFORE = 2.0       # seconds: the position row used for an alert at time t is the newest one in [t - LOOK_BEFORE, t + LOOK_AFTER]
LOOK_AFTER = 0.6
DROP_WINDOW = 10        # seconds before the alert in which the earlier back line is looked for (the window of the line_drop rule)
DROP_MIN = 5.0          # metres the recomputed back line must have sunk for the picture to be drawn (the rule needs 14 on its smoothed line)
RUN_WINDOW = 6          # seconds of path looked at for a run (the rule looks at the last 6 s)
RUN_MIN = 8.0           # metres moved toward a goal within RUN_WINDOW to count as the run
BOX_DEPTH, BOX_HALF_WIDTH = 16.5, 20.16
SPREAD_WIDTH, SPREAD_DEPTH = 12.0, 8.0          # as app/live_feedback.py: the alert then says they already stand spread
MOVE_MIN = 3.0          # metres: a suggested move shorter than this is not drawn
KEEPER_NEAR_GOAL, KEEPER_GAP = 14.0, 3.0
MAX_ARROWS = 3
POSITION_LOOK_BEFORE = 2.0      # the position map uses a row in [t - 2 s, t]: never a row after the alert
POSITION_MIN_OURS = 4           # fewer of our points than this: no map
POSITION_KINDS = ('conceded_run', 'box_attack', 'line_drop', 'run', 'isolated', 'gap_wide')   # kinds that get a position map; drop a kind here to turn its map off
CAPTIONS = {         # the one explaining line under a position map (what the fill, the ring and the line mean)
    'behind': '칠함 = 수비 뒤 공간 · 노랑 테두리 = 그 안의 상대',
    'box': '칠함 = 상대 박스 · 노랑 테두리 = 그 안의 선수',
    'line': '노랑 선 = 우리 수비 줄',
}


def short_line(row):
    """The short line of any alert row (also for alerts without a picture)."""
    kind = row.get('kind', '')
    if kind == 'line_drop' and not _retreat_supported(row):
        return LINES['line_drop_unconfirmed']
    if kind == 'box_attack' and _spread(row):
        return LINES['box_attack_spread']
    if kind in LINES:
        return LINES[kind]
    title = str(row.get('title') or kind)
    return title if len(title) <= 15 else title[:14] + '…'


def _evidence(row):
    value = row.get('evidence')
    return value if isinstance(value, dict) else {}


def _retreat_supported(row):
    directive = row.get('directive') if isinstance(row.get('directive'), dict) else {}
    return bool(_evidence(row).get('retreat_supported')) and directive.get('status') != 'review_required'


def _spread(row):
    ev = _evidence(row)
    try:
        return float(ev.get('width', 0)) >= SPREAD_WIDTH and float(ev.get('depth', 0)) >= SPREAD_DEPTH
    except (TypeError, ValueError):
        return False


# ---- the position record ------------------------------------------------------------------------------------------------------------
def read_segments(path):
    """positions.jsonl -> list of runs of the live analysis: [{'direction', 'length', 'width', 'rows': [(time, ours, theirs)]}] in file order.
    ours / theirs: {track id: (x, y)} in screen metres. A new header or a time going back starts a new run; a 'half' row changes the direction from its time on."""
    segments = []
    current = None
    try:
        handle = open(path, encoding='utf-8')
    except OSError:
        return []
    with handle:
        for line in handle:
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if not isinstance(row, dict):
                continue
            kind = row.get('type')
            if kind == 'header':
                current = {'direction': int(row.get('direction', 1)) if row.get('direction') in (1, -1) else 1, 'length': float(row.get('pitch_length', 89.0)),
                           'width': float(row.get('pitch_width', 62.0)), 'rows': [], 'switches': []}
                segments.append(current)
            elif kind == 'half' and current is not None and row.get('direction') in (1, -1):
                current['switches'].append((float(row.get('time', 0.0)), int(row['direction'])))
            elif kind == 'second' and current is not None and isinstance(row.get('time'), (int, float)):
                if current['rows'] and row['time'] < current['rows'][-1][0] - 1.0:
                    current = {**current, 'rows': [], 'switches': list(current['switches'])}
                    segments.append(current)
                pts = lambda key: {p[0]: (float(p[1]), float(p[2])) for p in row.get(key, []) if isinstance(p, (list, tuple)) and len(p) >= 3}
                current['rows'].append((float(row['time']), pts('team'), pts('other')))
    return [s for s in segments if s['rows']]


def alert_segments(rows):
    """alerts.jsonl rows -> for every row the index of its run counted from the END (0 = the last run), so it can be matched with read_segments from the end."""
    index, last, marks = 0, None, []
    for row in rows:
        t = row.get('time') if isinstance(row, dict) else None
        if isinstance(t, (int, float)):
            if last is not None and t < last - 1.0:
                index += 1
            last = t
        marks.append(index)
    return [index - m for m in marks]


def _direction_at(segment, t):
    direction = segment['direction']
    for at, d in segment['switches']:
        if at <= t + 0.01:
            direction = d
    return direction


def _row_at(rows, t):
    best = None
    for row in rows:
        if t - LOOK_BEFORE <= row[0] <= t + LOOK_AFTER:
            best = row
    return best


def _view(points, direction):
    return {k: (x * direction, y * direction) for k, (x, y) in points.items()}


def back_line(ours, length):
    """Our back line in the team's view (u toward the attacked goal): the mean depth of the three deepest outfield players, and those players.
    The deepest player is taken as the goalkeeper when he stands within 14 m of our goal line and 3 m behind the next one. None for fewer than 4 outfield points."""
    order = sorted(ours.items(), key=lambda item: item[1][0])
    if len(order) >= 2 and order[0][1][0] + length / 2 <= KEEPER_NEAR_GOAL and order[1][1][0] - order[0][1][0] >= KEEPER_GAP:
        order = order[1:]
    if len(order) < 4:
        return None
    deepest = order[:3]
    return sum(p[0] for _, p in deepest) / len(deepest), [k for k, _ in deepest]


def _r(p):
    return [round(p[0], 1), round(p[1], 1)]


def _base(ours, theirs, direction, t, line):
    return {'time': round(t, 1), 'line': line, 'direction': direction, 'ours': [_r(p) for p in ours.values()], 'theirs': [_r(p) for p in theirs.values()],
            'focus': [], 'threat': [], 'lines': [], 'zones': [], 'arrows': []}


# ---- one rule per kind --------------------------------------------------------------------------------------------------------------
def _line_drop(row, segment, t, direction):
    now = _row_at(segment['rows'], t)
    if now is None:
        return None
    ours = _view(now[1], direction)
    current = back_line(ours, segment['length'])
    if current is None:
        return None
    earlier = []
    for time, pts, _ in segment['rows']:
        if t - DROP_WINDOW <= time < now[0]:
            line = back_line(_view(pts, direction), segment['length'])
            if line:
                earlier.append(line[0])
    if not earlier:
        return None
    before = max(earlier)
    if before - current[0] < DROP_MIN:
        return None
    pic = _base(ours, _view(now[2], direction), direction, now[0], LINES['line_drop'])
    pic['focus'] = [_r(ours[k]) for k in current[1]]
    pic['lines'] = [{'u': round(before, 1), 'style': 'before'}, {'u': round(current[0], 1), 'style': 'now'}]
    pic['arrows'] = [{'from': _r(ours[k]), 'to': [round(before, 1), round(ours[k][1], 1)], 'style': 'dashed'} for k in current[1]][:MAX_ARROWS]
    pic['drop_m'] = round(before - current[0], 1)
    return pic


def _paths(segment, t, side, direction):
    paths = {}
    for time, ours, theirs in segment['rows']:
        if t - RUN_WINDOW <= time <= t + LOOK_AFTER:
            for k, p in _view(ours if side == 'ours' else theirs, direction).items():
                paths.setdefault(k, []).append((time, p))
    return paths


def _conceded_run(row, segment, t, direction):
    now = _row_at(segment['rows'], t)
    if now is None:
        return None
    ours, theirs = _view(now[1], direction), _view(now[2], direction)
    line = back_line(ours, segment['length'])
    if line is None or not theirs:
        return None
    best = None
    for k, path in _paths(segment, t, 'theirs', direction).items():
        if k not in theirs or len(path) < 3 or path[-1][0] - path[0][0] < 2.5:
            continue
        start = max(path, key=lambda item: item[1][0])            # the point of the path farthest from our goal
        moved = start[1][0] - path[-1][1][0]
        if moved >= RUN_MIN and path[-1][1][0] <= line[0] + 2.0 and start[0] < path[-1][0] and (best is None or moved > best[0]):
            best = (moved, start[1], path[-1][1])
    if best is None:
        return None
    end = best[2]
    pic = _base(ours, theirs, direction, now[0], LINES['conceded_run'])
    pic['threat'] = [_r(end)]
    pic['lines'] = [{'u': round(line[0], 1), 'style': 'now'}]
    pic['arrows'] = [{'from': _r(best[1]), 'to': _r(end), 'style': 'solid', 'side': 'theirs'}]
    near = min(ours.values(), key=lambda p: math.hypot(p[0] - end[0], p[1] - end[1]))
    pic['focus'] = [_r(near)]
    if math.hypot(near[0] - end[0], near[1] - end[1]) >= MOVE_MIN:
        pic['arrows'].append({'from': _r(near), 'to': _r(end), 'style': 'dashed'})
    return pic


def _run(row, segment, t, direction):
    now = _row_at(segment['rows'], t)
    if now is None:
        return None
    ours, theirs = _view(now[1], direction), _view(now[2], direction)
    best = None
    for k, path in _paths(segment, t, 'ours', direction).items():
        if k not in ours or len(path) < 3 or path[-1][0] - path[0][0] < 2.5:
            continue
        start = min(path, key=lambda item: item[1][0])
        moved = path[-1][1][0] - start[1][0]
        if moved >= RUN_MIN and start[0] < path[-1][0] and (best is None or moved > best[0]):
            best = (moved, k, start[1], path[-1][1])
    if best is None:
        return None
    _, runner, start, end = best
    pic = _base(ours, theirs, direction, now[0], LINES['run'])
    pic['focus'] = [_r(end)]
    pic['arrows'] = [{'from': _r(start), 'to': _r(end), 'style': 'solid'}]
    line = back_line(ours, segment['length'])
    keep_back = set(line[1]) if line else set()
    others = [p for k, p in sorted(ours.items(), key=lambda item: -item[1][0]) if k != runner and k not in keep_back and p[0] < end[0] - 5.0][:2]
    for p in others:
        pic['arrows'].append({'from': _r(p), 'to': [round(end[0], 1), round(p[1], 1)], 'style': 'dashed'})
    if len(theirs) >= 4:
        deepest = sorted(theirs.values(), key=lambda p: -p[0])
        if len(deepest) >= 2 and segment['length'] / 2 - deepest[0][0] <= KEEPER_NEAR_GOAL and deepest[0][0] - deepest[1][0] >= KEEPER_GAP:
            deepest = deepest[1:]
        if len(deepest) >= 3:
            pic['lines'].append({'u': round(sum(p[0] for p in deepest[:3]) / 3, 1), 'style': 'theirs'})
    return pic


def _box_attack(row, segment, t, direction):
    now = _row_at(segment['rows'], t)
    if now is None:
        return None
    ours = _view(now[1], direction)
    half = segment['length'] / 2
    inside = [p for p in ours.values() if half - BOX_DEPTH <= p[0] <= half and abs(p[1]) <= BOX_HALF_WIDTH]
    if len(inside) < 2:
        return None
    spread = _spread(row)
    pic = _base(ours, _view(now[2], direction), direction, now[0], LINES['box_attack_spread' if spread else 'box_attack'])
    pic['zones'] = [{'u0': round(half - BOX_DEPTH, 1), 'u1': round(half, 1), 'v0': -BOX_HALF_WIDTH, 'v1': BOX_HALF_WIDTH}]
    pic['focus'] = [_r(p) for p in inside]
    if spread:
        return pic
    places = [(half - 4.0, -6.0), (half - 4.0, 6.0), (half - 12.0, 0.0)]       # the two posts and the back (around the penalty spot)
    chosen = sorted(inside, key=lambda p: -p[0])[:3]
    best = None
    for order in itertools.permutations(places, len(chosen)):
        cost = sum(math.hypot(p[0] - q[0], p[1] - q[1]) for p, q in zip(chosen, order))
        if best is None or cost < best[0]:
            best = (cost, order)
    for p, q in zip(chosen, best[1]):
        if math.hypot(p[0] - q[0], p[1] - q[1]) >= MOVE_MIN:
            pic['arrows'].append({'from': _r(p), 'to': [round(q[0], 1), round(q[1], 1)], 'style': 'dashed'})
    return pic


# ---- the position map ---------------------------------------------------------------------------------------------------------------
def _row_before(rows, t):
    """Newest position row with t - 2 s <= time <= t (a row after the alert is never used)."""
    best = None
    for row in rows:
        if t - POSITION_LOOK_BEFORE <= row[0] <= t + 1e-6:
            best = row
    return best


def _named(row, ours):
    """Our points the alert itself names (directive.target.track_ids), when the record carries any (the live rules write none yet)."""
    directive = row.get('directive') if isinstance(row.get('directive'), dict) else {}
    target = directive.get('target') if isinstance(directive.get('target'), dict) else {}
    ids = target.get('track_ids') if isinstance(target.get('track_ids'), list) else []
    return [ours[k] for k in ids if k in ours]


def position_picture(row, segment, t, direction):
    """-> (picture dict or None, reason when None). See the module docstring."""
    now = _row_before(segment['rows'], t)
    if now is None:
        return None, 'no_position_row'
    ours, theirs = _view(now[1], direction), _view(now[2], direction)
    if len(ours) < POSITION_MIN_OURS:
        return None, 'few_ours'
    kind = row.get('kind')
    half = segment['length'] / 2
    width = segment['width'] / 2
    pic = _base(ours, theirs, direction, now[0], LINES.get(kind, ''))
    pic['type'] = 'position'
    if kind == 'box_attack':
        u0 = half - BOX_DEPTH
        pic['zones'] = [{'u0': round(u0, 1), 'u1': round(half, 1), 'v0': -BOX_HALF_WIDTH, 'v1': BOX_HALF_WIDTH}]
        pic['focus'] = [_r(p) for p in list(ours.values()) + list(theirs.values()) if p[0] >= u0 and abs(p[1]) <= BOX_HALF_WIDTH]
        pic['legend'] = CAPTIONS['box']
        pic['marked'] = 'box'
    else:
        line = back_line(ours, segment['length'])
        if line is None:
            return None, 'no_back_line'
        pic['lines'] = [{'u': round(line[0], 1), 'style': 'back'}]
        if kind == 'conceded_run':
            pic['zones'] = [{'u0': round(-half, 1), 'u1': round(line[0], 1), 'v0': -round(width, 1), 'v1': round(width, 1)}]
            pic['focus'] = [_r(p) for p in theirs.values() if p[0] < line[0]]
            pic['legend'] = CAPTIONS['behind']
            pic['marked'] = 'behind'
        else:
            pic['legend'] = CAPTIONS['line']
            pic['marked'] = 'line'
    named = _named(row, ours)
    if named:        # the alert names players: they are the ones circled
        pic['focus'] = [_r(p) for p in named]
        pic['legend'] = '노랑 테두리 = 알림이 가리킨 선수'
    return pic, None


RULES = {'line_drop': _line_drop, 'conceded_run': _conceded_run, 'run': _run, 'box_attack': _box_attack}
# Kinds whose picture is sent to the bench. Video check of 2026-11-24 (work/overnight-1124/bench-arrows/results.md, model judgement, not a person):
# line_drop 2 of 2 sampled pictures matched the video. conceded_run: in 1 of 2 the real back line and the nearest defender were players the detector missed
# (the picture pointed at the wrong player); box_attack: in 1 of 2 a highlighted point was the opponent goalkeeper (the 11-20 records count him as ours);
# run: both samples lie after the input cut of the test, where the video could not be matched to the record. Those three stay text only until checked again.
SHOWN = ('line_drop',)


def picture_with_reason(row, segment):
    """Alert row and the run of the position record it belongs to -> (picture dict, None) or (None, reason): the reason says why only the short line is shown.
    The arrow picture comes first (type 'arrows'); an alert it does not fit gets the position map (type 'position') if its kind has one."""
    if not isinstance(row, dict) or row.get('polarity') == 'status':
        return None, 'status'
    kind = row.get('kind')
    t = row.get('time')
    if kind not in POSITION_KINDS and not (kind in RULES and kind in SHOWN):
        return None, 'other_kind'
    if not isinstance(t, (int, float)):
        return None, 'no_time'
    if not segment:
        return None, 'no_record'
    direction = _direction_at(segment, float(t))
    try:
        pic = None
        if kind in RULES and kind in SHOWN and not (kind == 'line_drop' and not _retreat_supported(row)):
            pic = RULES[kind](row, segment, float(t), direction)
        if pic:
            # dashed suggestions at most MAX_ARROWS; one solid arrow of what happened may come with them
            dashed = [a for a in pic['arrows'] if a['style'] == 'dashed'][:MAX_ARROWS]
            pic['arrows'] = [a for a in pic['arrows'] if a['style'] != 'dashed'] + dashed
            pic['type'] = 'arrows'
            pic['length'], pic['width'] = segment['length'], segment['width']
            return pic, None
        if kind not in POSITION_KINDS:
            return None, 'no_arrow_picture'
        pic, reason = position_picture(row, segment, float(t), direction)
    except (ValueError, KeyError, TypeError, IndexError, ZeroDivisionError):
        return None, 'error'
    if pic:
        pic['length'], pic['width'] = segment['length'], segment['width']
    return pic, reason


def picture(row, segment):
    """Alert row and the run of the position record it belongs to -> picture dict, or None (no picture: show the short line only)."""
    return picture_with_reason(row, segment)[0]


class PictureCache:
    """Pictures of one store, kept per (session, row number) once the record has reached past the alert's moment (they never change after that)."""
    def __init__(self, store):
        self.store = Path(store)
        self.done = {}
        self.segments = {}      # session -> (mtime, size, segments)

    def positions_path(self, session):
        for path in (self.store / 'alerts' / session / 'positions.jsonl', self.store / 'positions' / f'{session}.jsonl'):
            if path.is_file():
                return path
        return None

    def _segments(self, session):
        path = self.positions_path(session)
        if path is None:
            return []
        try:
            stat = path.stat()
        except OSError:
            return []
        key = (stat.st_mtime, stat.st_size)
        cached = self.segments.get(session)
        if cached and cached[0] == key:
            return cached[1]
        segments = read_segments(path)
        self.segments[session] = (key, segments)
        return segments

    def get(self, session, number, row, from_end):
        """row of alerts.jsonl at `number`, from_end = alert_segments(rows)[number]."""
        key = (session, number)
        if key in self.done:
            return self.done[key]
        segments = self._segments(session)
        if from_end >= len(segments):
            return None
        segment = segments[len(segments) - 1 - from_end]
        pic = picture(row, segment)
        t = row.get('time') if isinstance(row, dict) else None
        if isinstance(t, (int, float)) and segment['rows'][-1][0] >= t + LOOK_AFTER:
            self.done[key] = pic         # the record is past the moment: final
        return pic
