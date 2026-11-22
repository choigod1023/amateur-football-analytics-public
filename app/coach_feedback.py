"""The two buttons of the bench screen, "도움됨" and "아님", and the small map of where the players stand now.

Ratings of the coach are kept apart from the ratings of the reviewer (app/alert_review.py writes <store>/alerts/labels/<session>-<number>.json, and this module never writes, changes
or deletes there). A coach's rating is a file <store>/alerts/labels-coach/<session>-<number>.json with the mark "origin": "coach_button". Pressing again replaces the coach's own earlier answer.

When the same alert also has a rating of the reviewer, the reviewer's rating is the one that counts: the summary leaves the coach's answer out of the totals of that alert (and says how many were left out),
and the screen shows the rating of the reviewer instead of the buttons.

Input is checked on the server: the session name has to be a plain name, the number has to be a line of that session's alerts.jsonl that really is a coaching alert (not a status row, not a heartbeat, not a
picture-rating row), and the answer has to be one of two words. The routes are writes, so this is meant for the same wireless network only (no login), like the rest of the review server.
"""
import json
import re
import threading
import time
from pathlib import Path

from app.bench_view import NOT_LIVE, SESSION, STATUS_KINDS, BenchView
from app.team_tactics import open_side

LABELS = ('ok', 'wrong')
USER_LABELS = ('ok', 'wrong', 'useless')
MAX_NUMBER = 99999
STAMP = re.compile(r'^([A-Za-z0-9_-]{1,40})-(\d{1,5})$')


def _is_alert(row):
    return bool(row) and row.get('polarity') != 'status' and row.get('kind') not in STATUS_KINDS + NOT_LIVE + ('heartbeat', 'half_switch', 'camera_moved', 'camera_back', None) and row.get('type') != 'heartbeat'


class CoachFeedback:
    def __init__(self, directory, clock=time.time):
        self.root = Path(directory) / 'alerts'
        self.folder = self.root / 'labels-coach'
        self.clock = clock
        self.lock = threading.Lock()

    def _rows(self, session):
        return BenchView._read(self.root / session / 'alerts.jsonl')

    def user_label(self, session, number):
        """The rating of the reviewer (read only), or None."""
        try:
            value = json.loads((self.root / 'labels' / f'{session}-{number}.json').read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return None
        return value.get('label') if isinstance(value, dict) and value.get('label') in USER_LABELS else None

    def coach_label(self, session, number):
        try:
            value = json.loads((self.folder / f'{session}-{number}.json').read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return None
        return value.get('label') if isinstance(value, dict) and value.get('origin') == 'coach_button' and value.get('label') in LABELS else None

    def set(self, session, number, label):
        """Save the coach's answer. Raises ValueError for anything that is not a plain session name, a coaching alert of that session or one of the two answers."""
        if not isinstance(session, str) or not SESSION.match(session):
            raise ValueError('세션 이름이 맞지 않습니다.')
        if not isinstance(number, int) or isinstance(number, bool) or not 0 <= number <= MAX_NUMBER:
            raise ValueError('알림 번호가 맞지 않습니다.')
        if label not in LABELS:
            raise ValueError('의견은 "도움됨"이나 "아님" 두 가지뿐입니다.')
        rows = self._rows(session)
        if number >= len(rows) or not _is_alert(rows[number]):
            raise ValueError('이 번호에는 판정할 알림이 없습니다.')
        record = {'id': f'{session}-{number}', 'session': session, 'number': number, 'label': label, 'origin': 'coach_button', 'kind': rows[number].get('kind'), 'at': self.clock()}
        with self.lock:
            self.folder.mkdir(parents=True, exist_ok=True)
            temporary = self.folder / f'{session}-{number}.json.tmp'
            temporary.write_text(json.dumps(record, ensure_ascii=False), encoding='utf-8')
            temporary.replace(self.folder / f'{session}-{number}.json')
        return record

    def state(self, session, numbers):
        """{number: {'coach': 'ok' | 'wrong' | None, 'user': the reviewer's rating or None}} for the alerts the screen shows."""
        return {n: {'coach': self.coach_label(session, n), 'user': self.user_label(session, n)} for n in numbers if isinstance(n, int) and 0 <= n <= MAX_NUMBER}

    def summary(self, session):
        """Per kind of alert: how many coach answers count ('ok', 'wrong'), and how many were left out because the reviewer rated the same alert."""
        kinds, left_out = {}, 0
        if not self.folder.is_dir():
            return {'kinds': {}, 'left_out': 0}
        rows = self._rows(session) if SESSION.match(session) else []
        for path in self.folder.glob(f'{session}-*.json'):
            match = STAMP.match(path.stem)
            number = int(match.group(2)) if match and match.group(1) == session else None
            label = self.coach_label(session, number) if number is not None else None
            if label is None or number >= len(rows) or not _is_alert(rows[number]):
                continue
            if self.user_label(session, number) is not None:
                left_out += 1
                continue
            entry = kinds.setdefault(rows[number].get('kind', ''), {'ok': 0, 'wrong': 0})
            entry[label] += 1
        return {'kinds': kinds, 'left_out': left_out}


# ---- the small map ----------------------------------------------------------------------------------------------------------------------
TAIL_BYTES = 65536
RECENT_SECONDS = 20
EMPTY_SHARE = 50.0           # per cent of the last seconds in which a lane was left empty by the four deepest players


def read_header(path):
    try:
        with open(path, encoding='utf-8') as handle:
            row = json.loads(handle.readline())
        return row if isinstance(row, dict) and row.get('type') == 'header' else {}
    except (OSError, ValueError):
        return {}


def latest_positions(path, direction=None, clock=time.time):
    """The newest position line of a live run and what it says in the view of our team (our team attacks to the right): {'ours': [[u, v]], 'theirs': [[u, v]], 'empty': [sides], 'age_s', 'time'}, or None.
    Only the end of the file is read. Nothing but where the players stand is returned (no numbers for the screen to show)."""
    path = Path(path)
    try:
        size = path.stat().st_size
        with open(path, 'rb') as handle:
            handle.seek(max(0, size - TAIL_BYTES))
            tail = handle.read().decode('utf-8', errors='replace').splitlines()
        age = clock() - path.stat().st_mtime
    except OSError:
        return None
    rows = []
    for line in tail:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict) and row.get('type') == 'second' and isinstance(row.get('time'), (int, float)):
            rows.append(row)
    if not rows:
        return None
    header = read_header(path)
    direction = direction if direction in (1, -1) else int(header.get('direction', 1))
    last = rows[-1]
    to_view = lambda points, flip: [[round(x * direction * flip, 1), round(y * direction * flip, 1)] for _id, x, y in points]
    ours = to_view(last.get('team', []), 1)
    series = {i: {'ours_points': [(u, v) for u, v in to_view(r.get('team', []), 1)]} for i, r in enumerate(rows[-RECENT_SECONDS:])}
    shares = open_side(series)
    empty = [name for name in ('left', 'centre', 'right') if shares and shares[name] >= EMPTY_SHARE]
    return {'ours': ours, 'theirs': to_view(last.get('other', []), 1), 'empty': empty, 'age_s': round(age, 1), 'time': last['time'], 'team': header.get('team', 'B'), 'other': header.get('other', 'A'), 'direction': direction}
