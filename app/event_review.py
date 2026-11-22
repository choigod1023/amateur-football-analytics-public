"""Reviewer-confirmed events (kickoffs, goals, set pieces) for a dedicated review store.

Candidates and their short silent clips are produced offline (scripts/build_event_candidates.py) into
<store>/events. A candidate is only a suggestion; a saved label is the reviewer's answer. Nothing here
detects events or changes any model.
"""
import json
import math
import os
import re
import secrets
import tempfile
import threading
import time
from pathlib import Path

LABELS = ('kickoff', 'goal', 'set_piece', 'shot', 'other', 'none', 'unsure')
CANDIDATE_ID = re.compile(r'^c[0-9]{3,4}$')
MANUAL_ID = re.compile(r'^m[0-9a-f]{12}$')
MEDIA_NAME = re.compile(r'^c[0-9]{3,4}\.(mp4|jpg)$')
MAX_TIME = 20000.0


def _valid_time(value):
    return value is None or (type(value) in (int, float) and math.isfinite(value) and 0 <= value <= MAX_TIME)


class EventReview:
    def __init__(self, directory):
        self.root = Path(directory) / 'events'
        self.lock = threading.Lock()

    def _candidates(self):
        try:
            data = json.loads((self.root / 'candidates.json').read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def _read_labels(self):
        labels = {}
        folder = self.root / 'labels'
        for path in (folder.glob('*.json') if folder.is_dir() else []):
            try:
                label = json.loads(path.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                continue
            if isinstance(label, dict) and label.get('label') in LABELS and path.stem == label.get('id'):
                labels[path.stem] = label
        return labels

    def listing(self):
        with self.lock:
            data = self._candidates()
            labels = self._read_labels()
            items = []
            for item in data.get('items', []):
                if not isinstance(item, dict) or not CANDIDATE_ID.match(str(item.get('id', ''))):
                    continue
                items.append({'id': item['id'], 't': item.get('t'), 'start': item.get('start'), 'end': item.get('end'),
                              'reasons': [str(r)[:160] for r in item.get('reasons', [])][:4], 'score': item.get('score'),
                              'label': labels.get(item['id'])})
            manual = sorted((v for k, v in labels.items() if MANUAL_ID.match(k)), key=lambda v: v.get('event_time') or 0)
            return {'basis': data.get('time_basis'), 'method': data.get('method'), 'generated': data.get('generated'),
                    'candidates': items, 'manual': manual, 'labels': sorted(LABELS)}

    def _write(self, label):
        folder = self.root / 'labels'
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / (label['id'] + '.json')
        temp_name = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=folder, suffix='.tmp', delete=False) as output:
                temp_name = output.name
                json.dump(label, output, ensure_ascii=False)
            os.replace(temp_name, target)
        finally:
            if temp_name and os.path.exists(temp_name):
                os.unlink(temp_name)

    def set_label(self, event_id, label, event_time=None, note=''):
        """Save the answer for a candidate or manual event; label 'clear' removes it (manual events vanish)."""
        if not isinstance(event_id, str) or not (CANDIDATE_ID.match(event_id) or MANUAL_ID.match(event_id)):
            raise ValueError('Invalid event id')
        if label != 'clear' and label not in LABELS:
            raise ValueError('Unknown label')
        if not _valid_time(event_time):
            raise ValueError('Invalid event time')
        if not isinstance(note, str) or len(note) > 200:
            raise ValueError('Note is too long')
        with self.lock:
            known = {i.get('id') for i in self._candidates().get('items', []) if isinstance(i, dict)}
            existing = self._read_labels()
            if event_id not in known and event_id not in existing:
                raise ValueError('Unknown event')
            if label == 'clear':
                path = self.root / 'labels' / (event_id + '.json')
                if path.is_file():
                    path.unlink()
                return None
            record = {'id': event_id, 'label': label, 'event_time': None if event_time is None else float(event_time),
                      'note': note.strip(), 'manual': bool(MANUAL_ID.match(event_id)),
                      'updated': time.strftime('%Y-%m-%d %H:%M:%S')}
            self._write(record)
            return record

    def add_manual(self, time_sec, label, note=''):
        if label not in LABELS or label == 'none':
            raise ValueError('Unknown label')
        if not _valid_time(time_sec) or time_sec is None:
            raise ValueError('Invalid event time')
        if not isinstance(note, str) or len(note) > 200:
            raise ValueError('Note is too long')
        with self.lock:
            record = {'id': 'm' + secrets.token_hex(6), 'label': label, 'event_time': float(time_sec), 'note': note.strip(),
                      'manual': True, 'updated': time.strftime('%Y-%m-%d %H:%M:%S')}
            self._write(record)
            return record

    def media(self, name):
        if not isinstance(name, str) or not MEDIA_NAME.match(name):
            return None
        path = self.root / 'media' / name
        return path if path.is_file() else None
