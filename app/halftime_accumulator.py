"""Adding up a live run while it runs, so that a half-time report needs no recalculation: the report is made from the sums in this file only.

The live run writes <store>/alerts/<session>/positions.jsonl (one line per second, app/live_positions.py) and alerts.jsonl. A thread of the server (app/halftime_report.HalftimeService.tick)
reads the new lines of both files every few seconds (from a saved byte offset, never the whole file again) and adds them into minute buckets:

  * per minute: how many seconds were seen; the shape of our team (length, width, the gaps between the three lines, height of the back line); the share of seconds in which the team stood in the
    opponent half; how often a lane was left empty by the four deepest players; the mean place of each of the 11 slots (the roles) of both teams
  * per half: the stretches without data, the runs into the box, the runs the other team made past our back line, the kinds of the alerts, the mean sides of the two teams

Players that are missing in a second (the tracker sees 9 or 10 of 11) are not left out of the picture: the 11 slots are the roles of the team (made from the first second with all 11 players in
view); every player that is seen goes to the closest free slot, and the slot of a missing player keeps its mean from the other seconds (the same stretch of the half). Two tracks closer than
1.5 m are one player; more than 11 players are cut to the 11 that fit the slots best.

The file <store>/service/halftime/<session>/accum.json holds everything (a few tens of KB) and is rewritten at most every 5 seconds. A process that died changes nothing: the file is read as it is.
The second half starts a second set of sums ('halves' 2): by a line {"type": "half", "half": 2, "direction": d, "time": t} that the live run writes when it is told to switch, or by the server (switch_half)
at the newest second it has seen. The first half stays as it was.
"""
import json
import math
import os
from pathlib import Path

from app.goalkeeper import without_goalkeeper
from app.report_scenes import second_metrics
from app.tactical_concepts import runs_in_behind
from app.team_tactics import MIN_PLAYERS, PITCH_WIDTH, open_side, shape

SLOTS = 11
HOLE_SECONDS = 11.0            # a step of this many seconds or more between two lines is a stretch without data
DOUBLE = 1.5                   # metres: two tracks this close are one player
WINDOW = 4                     # seconds: the window of a run in behind (app/tactical_concepts.runs_in_behind)
SAVE_EVERY = 5.0
BOX_DEPTH, BOX_HALF_WIDTH = 16.5, 20.16
ENTRY_DEPTH = 30.0             # metres from our goal line: our defensive third (wiki/live-startup-and-halftime.md, 4)
ENTRY_GAP = 10.0               # an entry within this many seconds of the last one is the same entry


def new_half(direction, start=None):
    return {'direction': direction, 'start_t': start, 'last_t': start, 'seconds': 0, 'minutes': {}, 'holes': [], 'box': [], 'box_open': None, 'conceded': [], 'conceded_last': {}, 'entries': [], 'entry_open': False, 'entry_last': -99.0,
            'recent': [], 'slots_all': {'team': [[0.0, 0.0, 0] for _ in range(SLOTS)], 'other': [[0.0, 0.0, 0] for _ in range(SLOTS)]}, 'mean_x': {'team': [0.0, 0], 'other': [0.0, 0]}}


def new_bucket():
    return {'n': 0, 'shape_n': 0, 'depth': 0.0, 'width': 0.0, 'g0': 0.0, 'g1': 0.0, 'back': 0.0, 'ahead': 0, 'open_n': 0, 'open': [0, 0, 0],
            'st': [[0.0, 0.0, 0] for _ in range(SLOTS)], 'so': [[0.0, 0.0, 0] for _ in range(SLOTS)]}


def merge_doubles(points):
    """[(id, x, y)] -> the same without a track that stands within DOUBLE metres of an earlier one."""
    kept = []
    for p in points:
        if all(math.hypot(p[1] - q[1], p[2] - q[2]) >= DOUBLE for q in kept):
            kept.append(p)
    return kept


def match_slots(points, reference, farthest=30.0):
    """Seen players [(u, v)] and the mean places of the 11 slots [(u, v)] -> the slot of every player (-1 for a player that gets none). The closest pairs are taken first,
    so a player keeps the slot he had (a role) while he moves around it; a player more than `farthest` metres from every free slot gets none (more than 11 players are cut this way)."""
    pairs = sorted((math.hypot(p[0] - r[0], p[1] - r[1]), i, j) for i, p in enumerate(points) for j, r in enumerate(reference))
    out, taken = [-1] * len(points), set()
    for distance, i, j in pairs:
        if distance > farthest:
            break
        if out[i] < 0 and j not in taken:
            out[i] = j
            taken.add(j)
    return out


class Accumulator:
    def __init__(self, session, state=None):
        self.session = session
        self.state = state or {'version': 1, 'header': {}, 'first': 0.0, 'pos_offset': 0, 'alert_offset': 0, 'last_t': None, 'half': 1, 'halves': {}, 'alerts': [], 'switch': None}
        self.dirty = False

    # ---- reading the new lines of the two files ---------------------------------------------------------------------------------------
    @staticmethod
    def _new_lines(path, offset):
        try:
            size = os.path.getsize(path)
        except OSError:
            return [], offset
        if size < offset:                                       # a file that was replaced: start again
            offset = 0
        with open(path, 'rb') as handle:
            handle.seek(offset)
            data = handle.read()
        end = data.rfind(b'\n')
        if end < 0:
            return [], offset
        return data[:end + 1].decode('utf-8', errors='replace').splitlines(), offset + end + 1

    def catch_up(self, positions_path, alerts_path):
        """Add every new complete line of the two files. Returns how many seconds of positions were added."""
        added = 0
        if positions_path and Path(positions_path).is_file():
            lines, offset = self._new_lines(positions_path, self.state['pos_offset'])
            if offset == 0 and self.state['pos_offset']:
                self.state = {**Accumulator(self.session).state}
            for line in lines:
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if isinstance(row, dict):
                    added += self._row(row)
            self.state['pos_offset'] = offset
            self.dirty = self.dirty or bool(lines)
        if alerts_path and Path(alerts_path).is_file():
            lines, offset = self._new_lines(alerts_path, self.state['alert_offset'])
            for line in lines:
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if (isinstance(row, dict) and row.get('polarity') != 'status' and row.get('kind') not in ('heartbeat', 'no_input', 'input_back', 'camera_moved', 'camera_back', None)
                        and row.get('type') != 'heartbeat' and isinstance(row.get('time'), (int, float))):
                    self.state['alerts'].append([float(row['time']), row['kind'], row.get('title') or row['kind'], self.state['half']])
            self.state['alert_offset'] = offset
            self.dirty = self.dirty or bool(lines)
        return added

    def _row(self, row):
        state = self.state
        if row.get('type') == 'header' and not state['header']:
            state['header'] = row
            state['first'] = float(row.get('first_second', 0.0))
            state['halves']['1'] = new_half(int(row['direction']))
            return 0
        if row.get('type') == 'half' and isinstance(row.get('time'), (int, float)):
            if state['half'] == 1 and state['header']:
                self.switch_half(float(row['time']), row.get('direction'))
            return 0
        if row.get('type') != 'second' or not state['header'] or not isinstance(row.get('time'), (int, float)):
            return 0
        t = float(row['time'])
        if state['last_t'] is not None and t <= state['last_t']:
            return 0
        self._second(t, [tuple(p) for p in row.get('team', [])], [tuple(p) for p in row.get('other', [])])
        return 1

    # ---- the halves ---------------------------------------------------------------------------------------------------------------------
    def switch_half(self, t=None, direction=None):
        """Start the sums of the second half (the first half stays as it is). t: the stream second of the switch (default: the newest second seen). Returns the new direction."""
        state = self.state
        if state['half'] != 1 or not state['header']:
            return None
        t = state['last_t'] if t is None else t
        direction = -state['halves']['1']['direction'] if direction not in (1, -1) else int(direction)
        state['half'] = 2
        state['halves']['2'] = new_half(direction)
        state['switch'] = {'t': t, 'direction': direction}
        self.dirty = True
        return direction

    @property
    def current(self):
        return self.state['halves'].get(str(self.state['half']))

    # ---- one second -------------------------------------------------------------------------------------------------------------------
    def _second(self, t, team_raw, other_raw):
        state = self.state
        half = self.current
        header = state['header']
        pitch_length = float(header.get('pitch_length', 89.0))
        direction = half['direction']
        if half['start_t'] is None:
            half['start_t'] = half['last_t'] = t
        elif t - half['last_t'] >= HOLE_SECONDS:
            half['holes'].append([half['last_t'], t])
        half['last_t'] = state['last_t'] = t
        half['seconds'] += 1
        team, other = merge_doubles(team_raw), merge_doubles(other_raw)
        ours = [(x * direction, y * direction) for _, x, y in team]
        theirs = [(-x * direction, -y * direction) for _, x, y in other]
        minute = str(int((t - half['start_t']) // 60))
        bucket = half['minutes'].setdefault(minute, new_bucket())
        bucket['n'] += 1
        for who, points, key in (('team', ours, 'st'), ('other', theirs, 'so')):
            self._slots(half, bucket, who, key, points)
        for who, points in (('team', team), ('other', other)):
            half['mean_x'][who][0] += sum(x for _, x, _y in points)
            half['mean_x'][who][1] += len(points)
        s = shape(ours)
        if s:
            bucket['shape_n'] += 1
            bucket['depth'] += s['depth']
            bucket['width'] += s['width']
            bucket['g0'] += s['gaps'][0]
            bucket['g1'] += s['gaps'][1]
            bucket['back'] += s['back'] + pitch_length / 2
            bucket['ahead'] += s['centre_u'] > 0
        lanes = open_side({0: {'ours_points': ours}})
        if lanes:
            bucket['open_n'] += 1
            for i, name in enumerate(('left', 'centre', 'right')):
                bucket['open'][i] += lanes[name] >= 100.0
        # entries of the other team into our defensive third: [second, side 0 left / 1 centre / 2 right in our team's view]
        zone = [v for u, v in theirs if u >= pitch_length / 2 - ENTRY_DEPTH]
        inside = bool(zone)
        if inside and not half.get('entry_open') and t - half.get('entry_last', -99.0) >= ENTRY_GAP:
            across = -sum(zone) / len(zone)                                   # their v turned into our team's view
            half.setdefault('entries', []).append([t, 0 if across < -PITCH_WIDTH / 6 else 2 if across > PITCH_WIDTH / 6 else 1])
            half['entry_last'] = t
        half['entry_open'] = inside
        # runs: the box (ours) and the runs the other team made past our back line
        in_box = sum(1 for u, v in ours if u >= pitch_length / 2 - BOX_DEPTH and abs(v) <= BOX_HALF_WIDTH)
        self._box(half, t, in_box)
        mt = second_metrics(team, other, direction, 6)
        mo = second_metrics(other, team, -direction, 6)
        half['recent'] = [r for r in half['recent'] if t - r[0] <= WINDOW + 1] + [[t, [(i, -x * direction, y) for i, x, y in other], mo['opponent_back_line'] if mo else None]]
        if mo and len(half['recent']) > WINDOW:
            self._conceded(half, t)

    def _slots(self, half, bucket, who, key, points):
        if not points:
            return
        allslots = half['slots_all'][who]
        if any(slot[2] == 0 for slot in allslots):                 # no complete picture yet: the first second with all 11 players makes the slots (in order of depth)
            if len(points) != SLOTS:
                return
            ordered = sorted(points)
            order = list(range(SLOTS))
        else:
            ordered = points
            order = match_slots(points, [(s[0] / s[2], s[1] / s[2]) for s in allslots])
        for (u, v), slot in zip(ordered, order):
            if slot < 0:
                continue
            for target in (bucket[key][slot], allslots[slot]):
                target[0] += u
                target[1] += v
                target[2] += 1

    def _box(self, half, t, count):
        current = half['box_open']
        if count >= 3:
            if current and t - current['last'] <= 1:
                current['last'], current['max'] = t, max(current['max'], count)
                if current['recorded']:
                    half['box'][-1][1] = current['max']
                elif current['last'] - current['start'] >= 1:      # two seconds in a row
                    half['box'].append([current['start'], current['max']])
                    current['recorded'] = True
            else:
                half['box_open'] = {'start': t, 'last': t, 'max': count, 'recorded': False}
        elif current and t - current['last'] > 1:
            half['box_open'] = None

    def _conceded(self, half, t):
        paths = {}
        back = {}
        for ft, points, line in half['recent']:
            for tid, u, y in points:
                paths.setdefault(tid, []).append((int(ft), u, y))
            if line is not None:
                back[int(ft)] = line
        for run in runs_in_behind(paths, back, 1.0, window=float(WINDOW)):
            if run['end'] == int(t) and t - half['conceded_last'].get(str(run['track']), -99) >= WINDOW:
                half['conceded_last'][str(run['track'])] = t
                if not half['conceded'] or t - half['conceded'][-1][0] >= 3.3:
                    half['conceded'].append([t, round(run['speed'] * 3.6)])

    # ---- the file ---------------------------------------------------------------------------------------------------------------------
    def save(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(self.state, ensure_ascii=False), encoding='utf-8')
        temporary.replace(path)
        self.dirty = False

    @classmethod
    def load(cls, session, path):
        try:
            state = json.loads(Path(path).read_text(encoding='utf-8'))
            if isinstance(state, dict) and state.get('version') == 1:
                return cls(session, state)
        except (OSError, ValueError):
            pass
        return cls(session)
