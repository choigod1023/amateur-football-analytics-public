"""The score board of the bench screen (web/bench.html, web/score.js): "우리 N : M 상대", filled by a person with buttons, and ready for a goal guess of the analysis to be confirmed with one press.

One append-only file per live session, <store>/alerts/<session>/score.jsonl, one event per line:
  {"id": 0, "t": 1764061000.5, "utc": "2026-11-25T10:30:00.512Z", "analysis": {...}, "kind": "goal" | "undo" | "candidate" | "dismiss", "team": "ours" | "opp" | "unknown", "source": "manual" | "auto", "ref": id of a candidate}
The score is always counted again from the first line, so a wrong press can never delete anything: an undo is a new line that cancels the latest goal.
  goal       team ours or opp. With "ref" it confirms that candidate (the candidate leaves the waiting list).
  undo       cancels the latest goal that is not cancelled yet. Only the one before it: it is refused when the last score event already is an undo (a second press cannot erase a second goal).
  candidate  "looks like a goal" (team ours, opp or unknown), written by the analysis later or by a test. Waits until a person confirms (goal with ref) or closes it (dismiss with ref).
  dismiss    closes the candidate "ref" without a goal.
Every line also carries what only the server knows: "t" and "utc" (the moment the server received it; nothing the screen sends is trusted) and "analysis", the place the live run had reached then, with the
field names of its own files: {"positions_time": "time" of the newest "second" line of positions.jsonl, "alerts_time": "time" of the newest row of alerts.jsonl, "alerts_wall": "wall" of the newest heartbeat row},
null when the run has written nothing yet. (The run writes no frame number and no match clock; "time" is the stream time in seconds.) A goal that confirms a candidate also carries "candidate_id", "candidate_t"
and "candidate_utc" (when the guess was made, to be compared later with the moment of the press). "source" says who made the line: "manual" = a person pressed it (a human judgement), "auto" = the analysis.
A goal is normally pressed some seconds AFTER the ball went in, so a reader looks for the goal in a stretch BEFORE the "utc" / "analysis" of the line. confirmed_goals() lists the goals.
Nothing here touches alerts.jsonl, positions.jsonl, the ratings or any label store, and a failure of this module never reaches the other routes (they are separate routes).
Like the rest of the review server there is no login (Host and Origin are checked by the middleware of review_public.py), so anybody who can open the page can change the score.
"""
import json
import datetime
import threading
import time
from pathlib import Path
from typing import Literal, Optional

from fastapi import HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from app.bench_view import SESSION, live_session

KINDS = ('goal', 'undo', 'candidate', 'dismiss')
TEAMS = ('ours', 'opp')
MAX_EVENTS = 2000              # a file that long is not a match: refuse more lines
MAX_PENDING_SHOWN = 3
DUPLICATE_WINDOW = 2.0         # seconds: the same goal of the same team pressed twice (a double tap) counts once
FILE = 'score.jsonl'


def _valid(event):
    if not isinstance(event, dict) or event.get('kind') not in KINDS or not isinstance(event.get('id'), int):
        return False
    team = event.get('team')
    if event['kind'] == 'goal':
        return team in TEAMS
    if event['kind'] == 'candidate':
        return team in TEAMS + ('unknown',)
    if event['kind'] == 'dismiss':
        return isinstance(event.get('ref'), int)
    return True


def _tail_rows(path, size=65536):
    try:
        with open(path, 'rb') as handle:
            handle.seek(0, 2)
            end = handle.tell()
            handle.seek(max(0, end - size))
            text = handle.read().decode('utf-8', errors='replace').splitlines()
    except OSError:
        return []
    rows = []
    for line in text:
        try:
            value = json.loads(line)
        except ValueError:
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def analysis_position(folder):
    """Where the live run of this session had got to, from the ends of its own files; None when it has written nothing."""
    seconds = [r for r in _tail_rows(Path(folder) / 'positions.jsonl') if r.get('type') == 'second' and isinstance(r.get('time'), (int, float))]
    rows = [r for r in _tail_rows(Path(folder) / 'alerts.jsonl') if isinstance(r.get('time'), (int, float))]
    wall = [r['wall'] for r in rows if (r.get('kind') == 'heartbeat' or r.get('type') == 'heartbeat') and isinstance(r.get('wall'), (int, float))]
    if not seconds and not rows:
        return None
    return {'positions_time': seconds[-1]['time'] if seconds else None, 'alerts_time': rows[-1]['time'] if rows else None, 'alerts_wall': wall[-1] if wall else None}


def utc_text(t):
    return datetime.datetime.fromtimestamp(t, datetime.timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def _goal_rows(events):
    """Goal events in file order with 'undone' set by the undo lines (nothing is removed)."""
    goals = []
    for event in events:
        if event['kind'] == 'goal':
            goals.append({'event': event, 'undone': False})
        elif event['kind'] == 'undo':
            for goal in reversed(goals):
                if not goal['undone']:
                    goal['undone'] = True
                    break
    return goals


def confirmed_goals(path, include_cancelled=False):
    """Score file -> the goals a person gave, oldest first: [{'id', 'team', 'utc', 't', 'source', 'analysis', 'candidate_id', 'candidate_utc', 'candidate_t', 'cancelled'}].
    Cancelled goals (undone) are left out unless include_cancelled; they stay in the file either way."""
    events = read_events(path)
    made = {e['id']: e for e in events if e['kind'] == 'candidate'}
    out = []
    for goal in _goal_rows(events):
        e = goal['event']
        if goal['undone'] and not include_cancelled:
            continue
        c = made.get(e.get('ref')) if isinstance(e.get('ref'), int) else None
        out.append({'id': e['id'], 'team': e['team'], 'utc': e.get('utc'), 't': e.get('t'), 'source': e.get('source', 'manual'), 'analysis': e.get('analysis'),
                    'candidate_id': c['id'] if c else None, 'candidate_utc': c.get('utc') if c else None, 'candidate_t': c.get('t') if c else None, 'cancelled': goal['undone']})
    return out


def read_events(path):
    """Events of one score file (damaged or unknown lines are skipped; a missing file gives an empty list)."""
    events = []
    try:
        with open(path, encoding='utf-8') as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    value = json.loads(line)
                except ValueError:
                    continue
                if _valid(value):
                    events.append(value)
    except OSError:
        return []
    return events


def compute(events, now=None):
    """Events -> {'ours', 'opp', 'pending': [candidates waiting], 'can_undo', 'last': team of the goal an undo would cancel}."""
    goals = []
    pending = {}
    last_scoring = None
    for event in events:
        kind = event['kind']
        if kind == 'candidate':
            pending[event['id']] = event
        elif kind == 'dismiss':
            pending.pop(event['ref'], None)
        elif kind == 'goal':
            if isinstance(event.get('ref'), int):
                pending.pop(event['ref'], None)
            goals.append({'team': event['team'], 'undone': False})
            last_scoring = 'goal'
        elif kind == 'undo':
            for goal in reversed(goals):
                if not goal['undone']:
                    goal['undone'] = True
                    break
            last_scoring = 'undo'
    live = [g for g in goals if not g['undone']]
    waiting = sorted(pending.values(), key=lambda e: e['id'], reverse=True)[:MAX_PENDING_SHOWN]
    return {'ours': sum(g['team'] == 'ours' for g in live), 'opp': sum(g['team'] == 'opp' for g in live),
            'pending': [{'id': e['id'], 'team': e['team'], 'source': e.get('source', 'manual'),
                         'age_s': None if now is None or not isinstance(e.get('t'), (int, float)) else round(max(0.0, now - e['t']), 1)} for e in waiting],
            'pending_count': len(pending),
            'can_undo': last_scoring == 'goal', 'last': next((g['team'] for g in reversed(goals) if not g['undone']), None) if last_scoring == 'goal' else None}


class ScoreBoard:
    def __init__(self, directory, clock=time.time):
        self.root = Path(directory) / 'alerts'
        self.clock = clock
        self.lock = threading.RLock()

    def file_of(self, session):
        return self.root / session / FILE

    def live_session(self):
        """The session the bench screen shows: the one rule of app/bench_view.live_session (also used by the half-time report)."""
        return live_session(self.root.parent)

    def state(self, session=None):
        session = session or self.live_session()
        if not session:
            return {'session': None, 'ours': 0, 'opp': 0, 'pending': [], 'pending_count': 0, 'can_undo': False, 'last': None}
        with self.lock:
            events = read_events(self.file_of(session))
        return {'session': session, **compute(events, self.clock())}

    def add(self, session, kind, team=None, source='manual', ref=None):
        """Appends one event after checking it against the events before it. Raises ValueError (text for the screen) when it makes no sense, FileNotFoundError when the session has no folder."""
        folder = self.root / session
        if not folder.is_dir():
            raise FileNotFoundError(session)
        path = self.file_of(session)
        with self.lock:
            events = read_events(path)
            if len(events) >= MAX_EVENTS:
                raise ValueError('점수 기록이 너무 많습니다.')
            now = self.clock()
            current = compute(events, now)
            waiting = {e['id']: e for e in events if e['kind'] == 'candidate'}
            closed = {e['ref'] for e in events if e['kind'] == 'dismiss'} | {e['ref'] for e in events if e['kind'] == 'goal' and isinstance(e.get('ref'), int)}
            record = {'id': (max((e['id'] for e in events), default=-1) + 1), 't': round(now, 3), 'utc': utc_text(now), 'kind': kind, 'source': source, 'analysis': analysis_position(folder)}
            if kind == 'goal':
                if team not in TEAMS:
                    raise ValueError('어느 팀의 골인지 정해 주세요.')
                if ref is not None:
                    if ref not in waiting or ref in closed:
                        raise ValueError('이미 처리된 후보입니다.')
                    record['ref'] = ref
                    record['candidate_id'], record['candidate_utc'], record['candidate_t'] = ref, waiting[ref].get('utc'), waiting[ref].get('t')
                else:
                    for e in reversed(events):
                        if e['kind'] == 'goal' and e['team'] == team and e.get('ref') is None and now - e.get('t', 0) < DUPLICATE_WINDOW and e.get('source') == source:
                            return {**self.state(session), 'duplicate': True}
                        if e['kind'] != 'candidate' and e['kind'] != 'dismiss':
                            break
                record['team'] = team
            elif kind == 'undo':
                if not current['can_undo']:
                    raise ValueError('되돌릴 골이 없습니다.')
            elif kind == 'candidate':
                if team not in TEAMS + ('unknown',):
                    raise ValueError('팀은 우리, 상대, 모름 중 하나입니다.')
                record['team'] = team
            elif kind == 'dismiss':
                if ref is None or ref not in waiting or ref in closed:
                    raise ValueError('이미 처리된 후보입니다.')
                record['ref'] = ref
            else:
                raise ValueError('알 수 없는 종류입니다.')
            line = json.dumps(record, ensure_ascii=False) + '\n'
            try:
                needs_break = path.is_file() and path.stat().st_size > 0 and not path.read_bytes().endswith(b'\n')
            except OSError:
                needs_break = False
            with open(path, 'a', encoding='utf-8', newline='\n') as handle:
                handle.write(('\n' if needs_break else '') + line)
        return {**self.state(session), 'duplicate': False}


class ScoreEvent(BaseModel):
    model_config = ConfigDict(extra='forbid')
    session: str = Field(min_length=1, max_length=40)
    kind: Literal['goal', 'undo', 'candidate', 'dismiss']
    team: Optional[Literal['ours', 'opp', 'unknown']] = None
    source: Literal['manual', 'auto'] = 'manual'
    ref: Optional[int] = Field(default=None, ge=0, le=1000000)


def install(app, directory, web_root, clock=time.time):
    board = ScoreBoard(directory, clock)
    root = Path(web_root).resolve()

    @app.get('/score.js')
    def score_js():
        path = root / 'score.js'
        if not path.is_file():
            raise HTTPException(404)
        return FileResponse(path)

    @app.get('/api/v1/score')
    def score_state(session: str = None):
        if session is not None and not SESSION.match(session):
            raise HTTPException(400, 'Bad session')
        return board.state(session)

    @app.post('/api/v1/score')
    def score_add(data: ScoreEvent):
        if not SESSION.match(data.session):
            raise HTTPException(400, 'Bad session')
        try:
            return board.add(data.session, data.kind, data.team, data.source, data.ref)
        except FileNotFoundError as exc:
            raise HTTPException(404, '이 경기의 기록 폴더가 없습니다.') from exc
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
    return board
