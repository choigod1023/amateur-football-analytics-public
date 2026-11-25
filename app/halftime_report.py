"""The half-time report of a live run, written in the words of a coach, from the sums of app/halftime_accumulator.py and from nothing else.

While the run goes on, HalftimeService.tick() (a thread of the server) adds the new lines of positions.jsonl and alerts.jsonl to the sums. When the input stops (or the coach presses the button) the
report is made from those sums in a few milliseconds: no replay of the half, no video, no live process needed (a process that died changes nothing).

When the report is made:
  * the coach presses "전반 끝" (source 'coach');
  * the input stops while the run is at least EARLIEST of a half long (a half of 45 minutes unless <store>/service/config.json says {"half_minutes": n}): the report is made at once as a draft
    (source 'auto') and the page asks whether the first half really ended ("맞음" keeps it, "아님" throws it away);
  * a stretch of a minute or more without positions late in the run is offered as the end (a person confirms).
The second half has its own button (switch_second_half): the direction turns round, the live run is told by <store>/alerts/<session>/control.jsonl (scripts/run_live_feedback.py reads it), a
new set of sums starts, the first half stays, and the colours of the teams have to be checked again.

The page is for a coach: no counts of detections, no metres, no methods. Both teams are drawn with 11 players (players that were not seen are filled from the shape the team had in the same
stretch of the half), gaps and problems are said in words ("the defence and the midfield were far apart"), and every claim is an observation, not an order. Nobody is named.
"""
import json
import threading
import time
from pathlib import Path

from app.bench_view import SESSION
from app.halftime_accumulator import SLOTS, Accumulator
from app.lineup import load_lineup
from app.opponent_summary import summary as opponent_summary
from app.service_watch import clock_text, length_text

HALF_SECONDS = 45 * 60.0
BREAK_SECONDS = 60.0              # a stretch this long without positions, late enough in the run, is offered as the half-time break
EARLIEST = 0.75                   # share of a half after which a stop can be the break
GAP_FAR = 18.0                    # metres between two lines of the team that is called "far apart" (a rule of thumb, not a measured limit)
WIDTH_NARROW, WIDTH_WIDE = 22.0, 40.0
DEPTH_LONG, DEPTH_SHORT = 45.0, 26.0
BACK_HIGH, BACK_LOW = 38.0, 24.0  # distance of the back line from the own goal line
AHEAD_MORE, AHEAD_LESS = 58.0, 42.0
SIDE_OFTEN = 35.0                 # per cent of the seconds in which a lane was left empty
SIDES = {0: '왼쪽', 1: '가운데', 2: '오른쪽'}
ENTRY_OFTEN, ENTRY_SOMETIMES = 6.0, 3.0   # entries of the other team per 10 minutes
ENTRY_CENTRE, ENTRY_SIDE = 0.5, 0.45      # the share of the entries that makes a way in the usual one


def stamp(t):
    return f'{int(t) // 60}분 {int(t) % 60:02d}초'


def _often(fraction):
    return '계속' if fraction >= 0.5 else '자주' if fraction >= 0.25 else '가끔' if fraction >= 0.1 else None


def _bands(keys):
    count = 1 if len(keys) < 6 else 2 if len(keys) < 12 else 3
    size = len(keys) / count
    return [keys[round(i * size):round((i + 1) * size)] for i in range(count)]


def _band_names(count, half):
    word = '전반' if half == 1 else '후반'
    return [f'{word} 전체'] if count == 1 else [f'{word} 앞쪽', f'{word} 뒤쪽'] if count == 2 else [f'{word} 초반', f'{word} 중반', f'{word} 후반']


def _slots(buckets, key, fallback, seconds):
    out = []
    for j in range(SLOTS):
        su = sv = c = 0
        for b in buckets:
            su, sv, c = su + b[key][j][0], sv + b[key][j][1], c + b[key][j][2]
        if c >= max(3, 0.2 * seconds):
            out.append([round(su / c, 1), round(sv / c, 1)])
        elif fallback[j][2]:
            out.append([round(fallback[j][0] / fallback[j][2], 1), round(fallback[j][1] / fallback[j][2], 1)])
        else:
            out.append(None)
    return out if all(out) else None


def build_report(state, half=1, end_s=None, source='coach', clock=time.time, lineup=None):
    """The report of one half as a dict from the sums of an Accumulator state. end_s: only minutes that start before it (the half ended earlier than the newest second)."""
    started = time.monotonic()
    h = state['halves'].get(str(half))
    if not h or not h['seconds']:
        raise ValueError('아직 이 구간의 자료가 쌓이지 않았습니다.')
    header = state['header']
    team, other = header.get('team', 'B'), header.get('other', 'A')
    direction = h['direction']
    start = h['start_t']
    last = h['last_t'] if end_s is None else min(h['last_t'], end_s)
    word = '전반' if half == 1 else '후반'
    keys = sorted((k for k in h['minutes'] if start + int(k) * 60 <= last), key=int)
    if not keys:
        raise ValueError('아직 이 구간의 자료가 쌓이지 않았습니다.')
    buckets = [h['minutes'][k] for k in keys]
    seconds = sum(b['n'] for b in buckets)

    def mean(field, group):
        n = sum(b['shape_n'] for b in group)
        return sum(b[field] for b in group) / n if n else None

    # the whole half in words
    shape_n = sum(b['shape_n'] for b in buckets)
    ahead = 100.0 * sum(b['ahead'] for b in buckets) / shape_n if shape_n else None
    back = mean('back', buckets)
    open_n = sum(b['open_n'] for b in buckets)
    open_shares = [100.0 * sum(b['open'][i] for b in buckets) / open_n for i in range(3)] if open_n else None
    shaped = [b for b in buckets if b['shape_n'] >= 10]
    names = _band_names(len(_bands(keys)), half)
    problems = []
    for field, text in (('g0', '수비 줄과 미드필드 줄 사이가 너무 벌어졌습니다'), ('g1', '미드필드 줄과 공격 줄 사이가 너무 벌어졌습니다')):
        flags = [b[field] / b['shape_n'] >= GAP_FAR for b in shaped]
        if flags and _often(sum(flags) / len(flags)):
            worst = max(range(len(_bands(keys))), key=lambda i: sum(1 for k in _bands(keys)[i] if h['minutes'][k]['shape_n'] >= 10 and h['minutes'][k][field] / h['minutes'][k]['shape_n'] >= GAP_FAR))
            problems.append(f'{text} ({_often(sum(flags) / len(flags))}, 특히 {names[worst]}).')
    width, depth = mean('width', buckets), mean('depth', buckets)
    if width is not None and width <= WIDTH_NARROW:
        problems.append('팀이 옆으로 좁게 섰습니다. 옆 공간을 상대에게 내주기 쉬운 모양입니다.')
    elif width is not None and width >= WIDTH_WIDE:
        problems.append('팀이 옆으로 넓게 퍼져 서로 도와주기 어려운 모양이었습니다.')
    if depth is not None and depth >= DEPTH_LONG:
        problems.append('팀이 위아래로 길게 늘어졌습니다.')
    elif depth is not None and depth <= DEPTH_SHORT:
        problems.append('팀이 위아래로 촘촘하게 모여 있었습니다.')
    if open_shares:
        side = max(range(3), key=lambda i: open_shares[i])
        if open_shares[side] >= SIDE_OFTEN:
            problems.append(f'수비 줄이 {SIDES[side]}을 자주 비웠습니다.')
        sides_open = [SIDES[i] for i in (0, 2) if open_shares[i] >= SIDE_OFTEN]
        if len(sides_open) == 2:
            problems = [p for p in problems if '자주 비웠습니다' not in p] + ['수비 줄이 가운데로 모여 양쪽 옆을 자주 비웠습니다.']
    if not problems:
        problems.append('눈에 띄게 반복된 문제는 없었습니다.')

    # how the other team came into our defensive third (positions only: where they stood, never where the ball was)
    entries = [e for e in h.get('entries', []) if e[0] <= last]
    minutes_run = max(1.0, (last - start) / 60.0)
    rate = 10.0 * len(entries) / minutes_run
    opponent = []
    if not entries:
        opponent.append('상대가 우리 수비 지역 가까이 들어오는 일은 거의 없었습니다.')
    else:
        opponent.append(f'상대가 우리 수비 지역에 {"자주" if rate >= ENTRY_OFTEN else "가끔" if rate >= ENTRY_SOMETIMES else "드물게"} 들어왔습니다.')
        share = [sum(1 for e in entries if e[1] == i) / len(entries) for i in range(3)]
        best = max(range(3), key=lambda i: share[i])
        if len(entries) >= 4 and share[best] >= (ENTRY_CENTRE if best == 1 else ENTRY_SIDE):
            opponent.append(f'들어올 때는 {SIDES[best]}{"로" if best == 1 else "으로"} 가장 많이 들어왔습니다.' + (' (우리 팀 기준 왼쪽과 오른쪽)' if best != 1 else ''))
        elif len(entries) >= 4:
            opponent.append('들어오는 쪽이 한쪽에 몰리지는 않았습니다.')
    box = [e for e in h['box'] if e[0] <= last]
    conceded = [e for e in h['conceded'] if e[0] <= last]
    holes = [x for x in h['holes'] if x[0] < last]
    missing_seconds = sum(b - a - 1 for a, b in holes)
    total = max(1.0, last - start + 1)
    parts = []
    if ahead is not None:
        parts.append(f'{word}에는 우리 팀이 ' + ('상대 진영에서 더 오래 머물렀습니다.' if ahead >= AHEAD_MORE else '우리 진영에서 더 오래 머물렀습니다.' if ahead <= AHEAD_LESS else '두 진영에서 비슷하게 머물렀습니다.'))
    if back is not None:
        parts.append('수비 줄은 ' + ('높은 편이었습니다.' if back >= BACK_HIGH else '낮은 편이었습니다.' if back <= BACK_LOW else '가운데쯤에 서 있었습니다.'))
    parts.append(f'상대 박스 안에 우리 선수가 여럿 들어간 장면이 {len(box)}번, 상대가 우리 수비 줄 뒤로 뛰어든 장면이 {len(conceded)}번 있었습니다.')
    parts.append(opponent[0])
    if holes:
        parts.append(f'영상이 끊긴 구간이 {len(holes)}곳 있어 그 시간은 요약에 들어 있지 않습니다.')

    # the picture of both teams: 11 players each, in up to three stretches of the half
    groups = _bands(keys)
    drawn = []
    for name, group in zip(names, groups):
        group_buckets = [h['minutes'][k] for k in group]
        sec = sum(b['n'] for b in group_buckets)
        ours = _slots(group_buckets, 'st', h['slots_all']['team'], sec)
        theirs = _slots(group_buckets, 'so', h['slots_all']['other'], sec)
        if ours and theirs:
            drawn.append({'name': name, 'ours': ours, 'theirs': [[-u, -v] for u, v in theirs]})

    # the two lines for the second half
    mx = {w: h['mean_x'][w][0] / h['mean_x'][w][1] for w in ('team', 'other') if h['mean_x'][w][1]}
    attack_now = '화면 왼쪽' if direction < 0 else '화면 오른쪽'
    attack_next = '화면 오른쪽' if direction < 0 else '화면 왼쪽'
    line_direction = (f'공격 방향 확인: {word}에 {team}팀은 {attack_now}으로 공격했습니다. ' + (f'후반에는 방향이 바뀌어 {attack_next}으로 공격해야 합니다. 후반 시작 버튼으로 방향을 바꾸고, 선수들이 서 있는 쪽이 맞는지 화면으로 확인해 주세요.' if half == 1 else '방향이 위치와 맞는지 화면으로 확인해 주세요.'))
    if len(mx) == 2 and abs(mx['team'] - mx['other']) >= 1.0 and (mx['team'] - mx['other']) * direction >= 0:
        line_direction += f' 다만 선수들의 위치로 보면 {team}팀이 입력한 방향과 반대쪽에 더 많이 서 있었습니다. 방향 입력을 다시 확인해 주세요.'
    line_colour = f'팀 색 재확인: 후반 시작 직후 {team}팀과 {other}팀이 옷 색대로 제대로 나뉘어 표시되는지 한 번 확인해 주세요.' if half == 1 else f'팀 색 재확인: {team}팀과 {other}팀이 옷 색대로 나뉘어 표시되는지 확인해 주세요.'
    notes = [p.rstrip('.') + '. 후반에도 이 부분이 반복되는지 지켜봐 주세요.' for p in problems + opponent[1:] if '눈에 띄게' not in p and '몰리지는' not in p][:2]

    counts = {}
    for t, kind, title, which in state['alerts']:
        if which == half and t <= last:
            entry = counts.setdefault(kind, [title, 0])
            entry[1] += 1
    report = {'session': state.get('session'), 'half': half, 'team': team, 'other': other, 'direction': direction, 'attack_text': attack_now, 'end_text': stamp(last), 'end_s': round(last, 1),
              'source': source, 'source_text': {'coach': '코치가 버튼을 눌러 만들었습니다', 'auto': '영상이 끊겨서 자동으로 만들었습니다. 전반이 끝난 것이 맞는지 확인해 주세요',
                                                'confirmed': '전반 끝을 사람이 확인했습니다'}.get(source, ''),
              'summary': parts, 'problems': problems, 'opponent': opponent, 'pictures': drawn,
              'box_attacks': [{'time_text': stamp(t), 'text': f'우리 선수 {n}명이 상대 박스 안에 들어갔습니다'} for t, n in box[:12]], 'box_total': len(box),
              'conceded': [{'time_text': stamp(t), 'text': '상대 선수가 우리 수비 줄 뒤로 빠르게 뛰어들었습니다'} for t, _v in conceded[:12]], 'conceded_total': len(conceded),
              'alerts': [{'title': title, 'count': n} for title, n in sorted(counts.values(), key=lambda x: -x[1])],
              'missing': {'ranges': [{'from_text': stamp(a + 1), 'to_text': stamp(b), 'length_text': length_text(b - a - 1)} for a, b in holes], 'total_text': length_text(missing_seconds),
                          'share_word': '조금' if missing_seconds / total < 0.1 else '꽤 많이'},
              'second_half': [line_direction, line_colour] + notes,
              'generated_at': clock(), 'generated_text': clock_text(clock())}
    if lineup:                                                                   # typed in by a person before the match; shown as typed, no name is attached to a dot or a measurement
        report['lineup'] = lineup
        if lineup['formation']:
            report['second_half'].insert(2, f'계획한 모양은 {lineup["formation"]}입니다. 후반에도 선수들이 이 모양대로 서 있는지 지켜봐 주세요.')
    try:                                                                         # the other team's block: a new field, the rest of the report never depends on it
        named = None if len(entries) < 4 else best if share[best] >= (ENTRY_CENTRE if best == 1 else ENTRY_SIDE) else -1   # the side "상대가 들어온 곳" names (-1: none)
        report['opponent_team'] = opponent_summary(buckets, float(header.get('pitch_length', 89.0)), float(header.get('pitch_width', 62.0)), half, entry_side=named)
    except Exception:                                                            # noqa: BLE001 - an odd bucket must not cost the coach the whole report
        report['opponent_team'] = opponent_summary([], half=half)
    report['build_seconds'] = round(time.monotonic() - started, 3)
    return report


class HalftimeService:
    def __init__(self, directory, watch=None, clock=time.time, half_seconds=None):
        self.directory = Path(directory)
        self.watch, self.clock = watch, clock
        self._half_seconds = half_seconds
        self.lock = threading.RLock()
        self.accumulators = {}
        self.saved_at = {}
        self.thread = None

    # ---- files --------------------------------------------------------------------------------------------------------------------------
    def _folder(self, session):
        return self.directory / 'service' / 'halftime' / session

    @property
    def half_seconds(self):
        if self._half_seconds:
            return self._half_seconds
        try:
            return float(json.loads((self.directory / 'service' / 'config.json').read_text(encoding='utf-8'))['half_minutes']) * 60.0
        except (OSError, ValueError, KeyError, TypeError):
            return HALF_SECONDS

    def _state(self, session):
        try:
            return json.loads((self._folder(session) / 'state.json').read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return None

    def _save(self, session, state):
        folder = self._folder(session)
        folder.mkdir(parents=True, exist_ok=True)
        temporary = folder / 'state.json.tmp'
        temporary.write_text(json.dumps(state, ensure_ascii=False), encoding='utf-8')
        temporary.replace(folder / 'state.json')

    def report(self, session, half=1):
        name = 'report.json' if half == 1 else f'report-{half}.json'
        try:
            return json.loads((self._folder(session) / name).read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return None

    def positions_file(self, session):
        for path in (self.directory / 'alerts' / session / 'positions.jsonl', self.directory / 'positions' / f'{session}.jsonl'):
            if path.is_file():
                return path
        return None

    # ---- the sums -----------------------------------------------------------------------------------------------------------------------
    def accumulator(self, session):
        with self.lock:
            if session not in self.accumulators:
                self.accumulators[session] = Accumulator.load(session, self._folder(session) / 'accum.json')
            return self.accumulators[session]

    def refresh(self, session, force=False):
        """Add the new lines of the two files; the sums are written to disk at most every 5 seconds (always with force)."""
        with self.lock:
            acc = self.accumulator(session)
            added = acc.catch_up(self.positions_file(session), self.directory / 'alerts' / session / 'alerts.jsonl')
            if acc.dirty and (force or self.clock() - self.saved_at.get(session, 0) >= 5.0):
                acc.save(self._folder(session) / 'accum.json')
                self.saved_at[session] = self.clock()
            return added

    def _live_session(self):
        found = self.watch._newest_live() if self.watch else None
        return found[0].name if found else None

    def tick(self):
        """One round of the thread: add the new lines of the newest live session, and make the draft report when the input stopped late in the first half."""
        session = self._live_session()
        if session is None or not self.positions_file(session):
            return None
        self.refresh(session)
        acc = self.accumulator(session)
        state = self._state(session) or {}
        outage = self.watch.open.get(session) if self.watch else None
        h = acc.state['halves'].get('1')
        if (outage is not None and acc.state['half'] == 1 and h and h['start_t'] is not None and h['last_t'] - h['start_t'] >= EARLIEST * self.half_seconds
                and state.get('auto_outage') != outage and state.get('status') != 'ready'):
            try:
                self.start(session, None, 'auto', outage=outage)
            except ValueError:
                pass
        return session

    def start_thread(self, interval=2.0):
        if self.thread is not None:
            return

        def loop():
            while True:
                try:
                    self.tick()
                except Exception:                         # the sums must outlive any single odd line
                    pass
                time.sleep(interval)
        self.thread = threading.Thread(target=loop, name='halftime-sums', daemon=True)
        self.thread.start()

    # ---- what a person sees and does ----------------------------------------------------------------------------------------------------
    def status(self, session=None):
        """{'session', 'status': 'waiting' | 'suggested' | 'ready' | 'failed' | 'no_positions', ...}; 'second_half' when the switch was pressed."""
        session = session or self._live_session()
        if session is None or not SESSION.match(session):
            return {'session': None, 'status': 'waiting', 'text': '진행 중인 라이브 실행이 없습니다.'}
        state = self._state(session) or {}
        extra = {'second_half': state['second_half']} if state.get('second_half') else {}
        acc0 = self.accumulator(session)
        first = acc0.state['halves'].get('1')
        if first and acc0.state['half'] == 1:                                  # what the button of the second half is going to ask
            extra['next_second_half'] = {'team': acc0.state['header'].get('team', 'B'), 'attack_text': '화면 오른쪽' if first['direction'] < 0 else '화면 왼쪽'}
        if state.get('status') in ('ready', 'failed'):
            return {'session': session, **state, **extra, 'link': f'/halftime?session={session}'}
        if self.positions_file(session) is None:
            return {'session': session, 'status': 'no_positions', **extra, 'text': '위치 기록이 없어 하프타임 보고서를 만들 수 없습니다. 라이브 실행을 --positions 옵션으로 시작해야 합니다.'}
        acc = self.accumulator(session)
        h = acc.state['halves'].get('1')
        if not h or h['start_t'] is None:
            return {'session': session, 'status': 'waiting', **extra, 'text': '위치 기록이 아직 비어 있습니다.'}
        if acc.state['half'] == 1:
            for a, b in h['holes']:
                if b - a >= BREAK_SECONDS and a - h['start_t'] >= EARLIEST * self.half_seconds and state.get('dismissed') != round(a):
                    return {'session': session, 'status': 'suggested', **extra, 'end_s': round(a, 1), 'end_text': stamp(a),
                            'text': f'입력이 오래 끊긴 구간이 있습니다. {stamp(a)}까지를 전반으로 보고 보고서를 만들까요?'}
        return {'session': session, 'status': 'waiting', **extra, 'text': '전반이 끝나면 "전반 끝" 버튼을 눌러 주세요.', 'latest_text': stamp(h['last_t'])}

    def start(self, session, end_s=None, source='coach', outage=None, wait=True):
        """Make the report of the first half from the sums (milliseconds). source: 'coach', 'confirmed' or 'auto' (a draft made when the input stopped)."""
        if not SESSION.match(session or ''):
            raise ValueError('세션 이름이 맞지 않습니다.')
        with self.lock:
            self.refresh(session, force=True)
            state = self._state(session) or {}
            try:
                report = build_report({**self.accumulator(session).state, 'session': session}, 1, end_s, source, self.clock, load_lineup(self.directory))
            except ValueError as error:
                done = {**state, 'status': 'failed', 'text': str(error)}
                self._save(session, done)
                raise
            self._folder(session).mkdir(parents=True, exist_ok=True)
            (self._folder(session) / 'report.json').write_text(json.dumps(report, ensure_ascii=False), encoding='utf-8')
            done = {**state, 'status': 'ready', 'source': source, 'end_s': report['end_s'], 'end_text': report['end_text'], 'generated_text': report['generated_text'],
                    'build_seconds': report['build_seconds']}
            done.pop('dismissed', None)
            if outage is not None:
                done['auto_outage'] = outage
            self._save(session, done)
            return {'session': session, **done, 'link': f'/halftime?session={session}'}

    def confirm(self, session):
        """A person said that the draft is right: the report stays as it is and is no longer marked as a draft."""
        with self.lock:
            report, state = self.report(session), self._state(session)
            if not report or not state:
                return False
            report['source'], report['source_text'] = 'confirmed', '전반 끝을 사람이 확인했습니다'
            (self._folder(session) / 'report.json').write_text(json.dumps(report, ensure_ascii=False), encoding='utf-8')
            self._save(session, {**state, 'source': 'confirmed'})
            return True

    def dismiss(self, session, end_s=None):
        """A person said that this is not the end of the first half: a draft is thrown away and a suggested end is not offered again."""
        with self.lock:
            state = self._state(session) or {}
            if state.get('status') == 'ready' and state.get('source') == 'auto':
                try:
                    (self._folder(session) / 'report.json').unlink()
                except OSError:
                    pass
                state = {k: v for k, v in state.items() if k not in ('status', 'source', 'end_s', 'end_text', 'generated_text', 'build_seconds')}
            if end_s is not None:
                state['dismissed'] = round(float(end_s))
            self._save(session, state)
            return True

    # ---- the second half ----------------------------------------------------------------------------------------------------------------
    def switch_second_half(self, session):
        """The button of the second half: the sums of the first half are kept, a new set starts with the opposite direction, the live run is told through control.jsonl,
        and the teams' colours have to be checked again. Returns the new direction (None when the switch was done before)."""
        if not SESSION.match(session or ''):
            raise ValueError('세션 이름이 맞지 않습니다.')
        with self.lock:
            self.refresh(session, force=True)
            acc = self.accumulator(session)
            if not acc.state['header']:
                raise ValueError('위치 기록이 없어 후반으로 넘길 수 없습니다.')
            if acc.state['half'] != 1:
                return None
            direction = acc.switch_half()
            acc.save(self._folder(session) / 'accum.json')
            control = self.directory / 'alerts' / session / 'control.jsonl'
            control.parent.mkdir(parents=True, exist_ok=True)
            seq = (sum(1 for _ in open(control, encoding='utf-8')) if control.is_file() else 0) + 1
            with open(control, 'a', encoding='utf-8') as handle:
                handle.write(json.dumps({'seq': seq, 'cmd': 'second_half', 'direction': direction, 'at': self.clock()}) + '\n')
            state = self._state(session) or {}
            self._save(session, {**state, 'second_half': {'at_text': clock_text(self.clock()), 'direction': direction, 'colour_checked': False,
                                                         'attack_text': '화면 왼쪽' if direction < 0 else '화면 오른쪽'}})
            return direction

    def colour_checked(self, session):
        with self.lock:
            state = self._state(session) or {}
            if not state.get('second_half'):
                return False
            state['second_half']['colour_checked'] = True
            self._save(session, state)
            return True

    def second_half_report(self, session):
        """A report of the second half so far (made on request from the sums)."""
        with self.lock:
            self.refresh(session)
            return build_report({**self.accumulator(session).state, 'session': session}, 2, None, 'coach', self.clock, load_lineup(self.directory))
