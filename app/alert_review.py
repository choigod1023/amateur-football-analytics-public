"""Review of the live alerts: a coach marks every alert as right, wrong or right but useless, and the marks are kept next to the alerts.

scripts/run_live_feedback.py writes the alerts of one run into <store>/alerts/<session>/ (alerts.jsonl and a picture of the passing lanes for every alert that has
one). This module lists them with their marks and counts the marks per kind of alert; those counts are the only ground truth there is for tuning the thresholds
of app/live_feedback.py (see docs/live-feedback.md). One small file per marked alert, so two coaches marking at the same time never overwrite each other.
"""
import json
import re
import threading
from datetime import datetime
from pathlib import Path

LABELS = ('ok', 'wrong', 'useless')
LABEL_TEXT = {'ok': '맞음', 'wrong': '틀림', 'useless': '맞지만 쓸모없음'}
SESSION = re.compile(r'^[A-Za-z0-9_-]{1,40}$')
ALERT_ID = re.compile(r'^([A-Za-z0-9_-]{1,40})-(\d{1,5})$')
IMAGE = re.compile(r'^[A-Za-z0-9_-]{1,60}\.(jpg|mp4)$')          # alerts_NNNN.jpg (picture of the run) and alerts_NNNN.mp4 (short clip of the scene, made after the match)
MAX_ALERTS = 300


class AlertReview:
    def __init__(self, directory):
        self.root = Path(directory) / 'alerts'
        self.lock = threading.Lock()

    def _sessions(self):
        if not self.root.is_dir():
            return []
        folders = [p for p in self.root.iterdir() if p.is_dir() and SESSION.match(p.name) and (p / 'alerts.jsonl').is_file()]
        return sorted(folders, key=lambda p: (p / 'alerts.jsonl').stat().st_mtime, reverse=True)

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
                    rows.append(value if isinstance(value, dict) else None)      # a damaged line keeps its place so that the numbers of the others do not move
        except OSError:
            return []
        return rows

    def _labels(self):
        found = {}
        folder = self.root / 'labels'
        for path in (folder.glob('*.json') if folder.is_dir() else []):
            try:
                value = json.loads(path.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                continue
            if isinstance(value, dict) and value.get('label') in LABELS and value.get('id') == path.stem:
                found[path.stem] = value
        return found

    def listing(self):
        with self.lock:
            labels = self._labels()
            items, sessions = [], []
            for folder in self._sessions():
                rows = self._read(folder / 'alerts.jsonl')
                sessions.append({'session': folder.name, 'count': sum(1 for r in rows if r)})
                first = len(items)
                for number, row in enumerate(rows):
                    if not row or row.get('polarity') == 'status':          # a loss or recovery of the video input (app/live_input.py) is a note of the run, not an alert to rate
                        continue
                    detail = row.get('detail') if isinstance(row.get('detail'), dict) else {}
                    image = folder / f'alerts_{number:04d}.jpg'
                    video = folder / f'alerts_{number:04d}.mp4'
                    ident = f'{folder.name}-{number}'
                    label = labels.get(ident, {})
                    items.append({'id': ident, 'session': folder.name, 'time': row.get('time'), 'kind': row.get('kind'), 'title': row.get('title'), 'text': row.get('text'),
                                  'polarity': row.get('polarity'), 'line': detail.get('line'), 'scene': detail.get('scene') or [], 'space': detail.get('space') or [],
                                  'advice': detail.get('advice') or [], 'image': f'/alert-files/{folder.name}/{image.name}' if image.is_file() else None,
                                  'video': f'/alert-files/{folder.name}/{video.name}' if video.is_file() else None,
                                  'label': label.get('label'), 'note': label.get('note', '')})
                items[first:] = sorted(items[first:], key=lambda a: -(a['time'] or 0))          # the newest alert of a session first; the newest session first
            items = items[:MAX_ALERTS]
            stats = {}
            for item in items:
                row = stats.setdefault(item['kind'], {'kind': item['kind'], 'title': item['title'], 'total': 0, 'ok': 0, 'wrong': 0, 'useless': 0})
                row['total'] += 1
                if item['label']:
                    row[item['label']] += 1
            for row in stats.values():
                done = row['ok'] + row['wrong'] + row['useless']
                row['labelled'] = done
                row['useful_share'] = round(row['ok'] / done, 3) if done else None
            return {'alerts': items, 'stats': sorted(stats.values(), key=lambda r: -r['total']), 'sessions': sessions, 'label_text': LABEL_TEXT}

    def _exists(self, ident):
        match = ALERT_ID.match(ident or '')
        if not match:
            return False
        path = self.root / match.group(1) / 'alerts.jsonl'
        if not path.is_file():
            return False
        rows = self._read(path)
        number = int(match.group(2))
        return number < len(rows) and rows[number] is not None

    def set_label(self, ident, label, note=''):
        """Mark an alert (label in LABELS), or clear the mark with label None or ''. Raises ValueError for an unknown alert or label."""
        with self.lock:
            if not self._exists(ident):
                raise ValueError('Unknown alert')
            if label not in (None, '') + LABELS:
                raise ValueError('Unknown label')
            folder = self.root / 'labels'
            target = folder / f'{ident}.json'
            if label in (None, ''):
                target.unlink(missing_ok=True)
                return None
            folder.mkdir(parents=True, exist_ok=True)
            value = {'id': ident, 'label': label, 'note': (note or '')[:200], 'updated': datetime.now().isoformat(timespec='seconds')}
            temporary = target.with_suffix('.tmp')
            temporary.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
            temporary.replace(target)
            return value

    def image(self, session, name):
        """The path of a picture of an alert, or None (names are checked, nothing outside the session folder is ever served)."""
        if not SESSION.match(session or '') or not IMAGE.match(name or ''):
            return None
        path = self.root / session / name
        return path if path.is_file() else None
