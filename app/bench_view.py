"""Read-only data for the coach's bench screen (web/bench.html): the newest alert of a live run, the last few before it, the state of the input and,
per kind of alert, how many of the alerts rated by the reviewer were right.

Nothing here writes, and nothing leaves the computer: the rows come from <store>/alerts/<session>/alerts.jsonl (written by scripts/run_live_feedback.py) and the ratings from
<store>/alerts/labels/<session>-<number>.json (written by app/alert_review.py). The wording of an alert is shown as it is written.

Priority (wiki/live-operations-research.md, R3): red = act now (a run behind our line, players in the box), yellow = needed soon (an isolated forward, our own run),
grey = for information (line gap, line drop, which were right in only 3 of 6 and 1 of 3 rated alerts). 'run' is not named in that table: it is yellow here because it is an
opening for our own team, which is needed soon and not a danger. Kinds that are not known stay grey.

The age of an alert is counted from the moment this module first saw its line (rows that were already in the file when the module first read it get the time of the last change
of the file, which is only an upper bound for their age). The input state follows the status rows of app/live_input.py (no_input, input_back) and, when a run writes them,
heartbeat rows (a row with type or kind 'heartbeat'); without heartbeat rows an alerts file that does not change says nothing about the input, and the state is 'unknown'.
"""
import json
import re
import threading
import time
from pathlib import Path

from app.alert_picture import PictureCache, alert_segments, short_line

SESSION = re.compile(r'^[A-Za-z0-9_-]{1,40}$')
PRIORITY = {'conceded_run': 'urgent', 'box_attack': 'urgent', 'isolated': 'notice', 'run': 'notice', 'line_drop': 'info', 'gap_wide': 'info'}
PRIORITY_TEXT = {'urgent': '급함', 'notice': '주의', 'info': '참고'}
STATUS_KINDS = ('no_input', 'input_back')
NOT_LIVE = ('person_check',)          # review sessions made for rating pictures, not live runs
MIN_SAMPLE = 5                        # fewer rated alerts than this: the share is not shown as a number of its own
HEARTBEAT_STALE = 10.0                # seconds without a heartbeat row before the input counts as lost
RECENT = 5


def is_live_session(name):
    """False for hand-labelling sessions (label-...) and archives (_...): they must never be shown as the live run."""
    return not (name.startswith('label-') or name.startswith('_'))


def current_match(directory):
    """The match the person started on /setup (<store>/service/setup/match.json): (name, moment it was started) or None.
    From that moment the sessions of the matches before are not the live run any more, even though their files are the newest ones until the new analysis writes its first row."""
    try:
        value = json.loads((Path(directory) / 'service' / 'setup' / 'match.json').read_text(encoding='utf-8'))
        name = value['name']
        started = time.mktime(time.strptime(value['created'], '%Y-%m-%dT%H:%M:%S'))
    except (OSError, ValueError, KeyError, TypeError, OverflowError):
        return None
    return (name, started) if isinstance(name, str) and SESSION.match(name) and is_live_session(name) else None


def belongs_to_match(match, name, changed):
    """Whether a session may be the live one: no match started, the session is the match itself, or it was written to after the match was started (a run started by hand under another name)."""
    return match is None or name == match[0] or changed >= match[1]


def live_session(directory):
    """The one rule for "the match now" when an address names none (score board, half-time report): the most recently changed live session that belongs to the started
    match, whose alerts hold a row that is not a person-check row; else the started match itself (a new match whose analysis has written nothing yet); else None."""
    root = Path(directory) / 'alerts'
    if not root.is_dir():
        return None
    match = current_match(directory)
    pairs = []
    for p in root.iterdir():
        try:
            if p.is_dir() and SESSION.match(p.name) and is_live_session(p.name) and (p / 'alerts.jsonl').is_file():
                changed = (p / 'alerts.jsonl').stat().st_mtime
                if belongs_to_match(match, p.name, changed):          # the matches before a newly started one are not the live run
                    pairs.append((changed, p))
        except OSError:
            continue
    pairs.sort(key=lambda x: x[0], reverse=True)
    for _, folder in pairs:
        try:
            with open(folder / 'alerts.jsonl', encoding='utf-8') as handle:
                for line in handle:
                    try:
                        row = json.loads(line)
                    except ValueError:
                        continue
                    if isinstance(row, dict) and row.get('kind') not in NOT_LIVE:
                        return folder.name
        except OSError:
            continue
    if match and (root / match[0]).is_dir():
        return match[0]
    return None


def priority_of(row):
    """Row of alerts.jsonl -> 'urgent', 'notice' or 'info' (a status row of the input is urgent)."""
    if row.get('polarity') == 'status' or row.get('kind') in STATUS_KINDS:
        return 'urgent'
    return PRIORITY.get(row.get('kind'), 'info')


def accuracy_text(ok, total):
    """'n개 중 m개 맞음', or '표본 적음' when fewer than MIN_SAMPLE alerts of the kind were rated."""
    if total < MIN_SAMPLE:
        return f'표본 적음 (판정 {total}개 중 {ok}개 맞음)' if total else '표본 적음 (판정 없음)'
    return f'판정 {total}개 중 {ok}개 맞음'


def _is_heartbeat(row):
    return row.get('type') == 'heartbeat' or row.get('kind') == 'heartbeat'


def input_state(rows, seen, now, stale=HEARTBEAT_STALE):
    """rows of one session (None for a damaged line), seen[i] = moment row i was first seen -> {'state': 'ok' | 'no_input' | 'unknown', 'reason': text, 'since_s': seconds or None}."""
    last_status = None
    last_heartbeat = None
    for i, row in enumerate(rows):
        if not row:
            continue
        if row.get('kind') in STATUS_KINDS:
            last_status = (row['kind'], seen[i])
        elif _is_heartbeat(row):
            last_heartbeat = seen[i]
    if last_status and last_status[0] == 'no_input':
        return {'state': 'no_input', 'reason': '영상 입력이 끊겼다고 기록되었습니다', 'since_s': round(now - last_status[1], 1)}
    if last_heartbeat is not None:
        age = now - last_heartbeat
        if age > stale:
            return {'state': 'no_input', 'reason': f'{stale:.0f}초 넘게 하트비트가 없습니다', 'since_s': round(age, 1)}
        return {'state': 'ok', 'reason': '하트비트 정상', 'since_s': round(age, 1)}
    return {'state': 'unknown', 'reason': '하트비트 기록이 없어 입력 상태를 알 수 없습니다', 'since_s': None}


class BenchView:
    def __init__(self, directory, clock=time.time):
        self.root = Path(directory) / 'alerts'
        self.clock = clock
        self.lock = threading.Lock()
        self.first_seen = {}            # (session, row number) -> (moment, whether the moment is only the last change of the file)
        self.pictures = PictureCache(directory)   # picture of the current alert, computed again from the position record of the run (app/alert_picture.py)

    @staticmethod
    def _read(path):
        rows = []
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
                    rows.append(value if isinstance(value, dict) else None)
        except OSError:
            return []
        return rows

    def _sessions(self):
        if not self.root.is_dir():
            return []
        folders = [p for p in self.root.iterdir() if p.is_dir() and SESSION.match(p.name) and (p / 'alerts.jsonl').is_file()]
        return sorted(folders, key=lambda p: (p / 'alerts.jsonl').stat().st_mtime, reverse=True)

    @staticmethod
    def _is_live(rows):
        return any(r and r.get('kind') not in NOT_LIVE for r in rows)

    def accuracy(self):
        """{kind: {'total', 'ok', 'text', 'low_sample'}} from the rated alerts of every session that is not a picture-rating session."""
        folder = self.root / 'labels'
        kinds = {}
        rows_of = {}
        for path in (folder.glob('*.json') if folder.is_dir() else []):
            try:
                value = json.loads(path.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                continue
            match = re.match(r'^([A-Za-z0-9_-]{1,40})-(\d{1,5})$', path.stem)
            if not (isinstance(value, dict) and match and value.get('label') in ('ok', 'wrong', 'useless') and value.get('id') == path.stem):
                continue
            session, number = match.group(1), int(match.group(2))
            if session not in rows_of:
                rows_of[session] = self._read(self.root / session / 'alerts.jsonl') if SESSION.match(session) else []
            rows = rows_of[session]
            row = rows[number] if number < len(rows) else None
            if not row or row.get('kind') in NOT_LIVE or row.get('polarity') == 'status' or row.get('kind') in STATUS_KINDS:
                continue
            entry = kinds.setdefault(row.get('kind', ''), {'total': 0, 'ok': 0})
            entry['total'] += 1
            entry['ok'] += value['label'] == 'ok'
        for entry in kinds.values():
            entry['text'] = accuracy_text(entry['ok'], entry['total'])
            entry['low_sample'] = entry['total'] < MIN_SAMPLE
        return kinds

    def snapshot(self, session=None):
        """The whole screen in one answer. Never raises on a missing store: it says there is nothing to show."""
        now = self.clock()
        with self.lock:
            folders = self._sessions()
            chosen = None
            match = None if session else current_match(self.root.parent)
            for folder in folders:
                if session and folder.name != session:
                    continue
                if not session and not is_live_session(folder.name):
                    continue
                if not belongs_to_match(match, folder.name, (folder / 'alerts.jsonl').stat().st_mtime):
                    continue
                rows = self._read(folder / 'alerts.jsonl')
                if self._is_live(rows):
                    chosen = (folder, rows)
                    break
            if chosen is None and match and (self.root / match[0]).is_dir():      # a new match, the analysis has written nothing yet: the screen is empty, but it is this match's
                return {'session': match[0], 'now': now, 'state': {'state': 'unknown', 'reason': '새 경기입니다. 분석이 아직 기록을 쓰지 않았습니다', 'since_s': None},
                        'current': None, 'recent': [], 'accuracy': self.accuracy(), 'priority_text': PRIORITY_TEXT}
            if chosen is None:
                return {'session': None, 'now': now, 'state': {'state': 'unknown', 'reason': '실시간 알림 파일이 없습니다', 'since_s': None},
                        'current': None, 'recent': [], 'accuracy': self.accuracy(), 'priority_text': PRIORITY_TEXT}
            folder, rows = chosen
            modified = (folder / 'alerts.jsonl').stat().st_mtime
            seen = []
            first_read = not any(key[0] == folder.name for key in self.first_seen)
            for i in range(len(rows)):
                key = (folder.name, i)
                if key not in self.first_seen:
                    self.first_seen[key] = (modified, True) if first_read else (now, False)
                seen.append(self.first_seen[key][0])
            accuracy = self.accuracy()
            alerts = []
            for i, row in enumerate(rows):
                if not row or _is_heartbeat(row) or row.get('kind') in NOT_LIVE:
                    continue
                kind = row.get('kind', '')
                level = priority_of(row)
                alerts.append({'number': i, 'kind': kind, 'title': row.get('title') or kind, 'text': row.get('text') or '', 'priority': level, 'line': short_line(row),
                               'priority_text': PRIORITY_TEXT[level], 'status': row.get('polarity') == 'status' or kind in STATUS_KINDS,
                               'age_s': round(max(0.0, now - seen[i]), 1), 'age_estimated': self.first_seen[(folder.name, i)][1],
                               'accuracy': None if (kind in STATUS_KINDS or row.get('polarity') == 'status') else accuracy.get(kind, {'total': 0, 'ok': 0, 'text': accuracy_text(0, 0), 'low_sample': True})})
            alerts.reverse()
            if alerts:
                current = alerts[0]
                try:
                    number = current['number']
                    current['picture'] = None if current['status'] else self.pictures.get(folder.name, number, rows[number], alert_segments(rows)[number])
                except Exception:          # the picture is an addition: the screen works as before without it
                    current['picture'] = None
            return {'session': folder.name, 'now': now, 'file_age_s': round(now - modified, 1), 'state': input_state(rows, seen, now),
                    'current': alerts[0] if alerts else None, 'recent': alerts[1:1 + RECENT], 'accuracy': accuracy, 'priority_text': PRIORITY_TEXT}
