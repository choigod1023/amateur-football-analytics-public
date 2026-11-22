"""A stable human review queue. Answers never mutate source labels or train models."""
import hashlib
import json
from pathlib import Path
import re
import threading
from datetime import datetime, timezone

IDENT = re.compile(r'^d[0-9]{4,6}$')
MEDIA = re.compile(r'^d[0-9]{4,6}(?:-[a-z0-9]+)?\.(?:mp4|jpg|png)$')
VERDICTS = {'tracking': ('same', 'different', 'unclear'),
            'coaching': ('before', 'after', 'both_wrong', 'unclear')}


def read(path, default):
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        return data if isinstance(data, type(default)) else default
    except (OSError, ValueError):
        return default


def fingerprint(item):
    return hashlib.sha256(json.dumps(item, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class DifferenceReview:
    def __init__(self, directory):
        self.root = Path(directory) / 'differences'
        self.lock = threading.Lock()

    def items(self):
        data = read(self.root / 'queue.json', {})
        rows = data.get('items', [])
        if not isinstance(rows, list):
            return {}
        result = {}
        for row in rows:
            if isinstance(row, dict) and IDENT.fullmatch(str(row.get('id', ''))) and row.get('kind') in VERDICTS:
                if row['id'] in result:
                    raise ValueError('Duplicate review id')
                result[row['id']] = row
        return result

    def listing(self, include_answered=False, scope=None):
        with self.lock:
            items = self.items()
            if scope is not None:
                items = {key:row for key,row in items.items() if row.get('review_scope') == scope}
            output, completed, retired = [], 0, 0
            inactive = read(self.root / 'inactive.json', {})
            preferences = {v: 0 for v in VERDICTS['coaching']}
            invalid = 0
            for ident, row in items.items():
                answer = read(self.root / 'answers' / f'{ident}.json', {})
                current = bool(answer and answer.get('fingerprint') == fingerprint(row)
                               and answer.get('id') == ident and answer.get('source') == 'human'
                               and answer.get('verdict') in VERDICTS[row['kind']])
                invalid += bool(answer and not current)
                if current and row['kind'] == 'coaching':
                    preferences[answer['verdict']] += 1
                completed += current
                retired += bool(ident in inactive and not current)
                if (current or ident in inactive) and not include_answered:
                    continue
                media = lambda name: '/difference-files/' + name if isinstance(name, str) and self.media(name) else None
                output.append({**{k: row.get(k) for k in ('id', 'kind', 'title', 'reason', 'before', 'after', 'time', 'half')},
                               'video': media(row.get('video')), 'images': [url for name in row.get('images', []) if (url := media(name))],
                               'answer': answer or None, 'answer_is_current': current,
                               'retired_reason': inactive.get(ident), 'verdicts': VERDICTS[row['kind']]})
            judged = preferences['before'] + preferences['after'] + preferences['both_wrong']
            return {'items': output, 'total': len(items), 'completed': completed, 'retired': retired, 'remaining': len(items) - completed - retired,
                    'review_summary': {'preferences': preferences, 'judged': judged, 'invalid_or_stale': invalid,
                                       'after_preference_rate': preferences['after'] / judged if judged else None,
                                       'scope': 'reviewed_changed_scenes_only', 'is_accuracy': False}}

    def answer(self, ident, verdict, note=''):
        if not isinstance(ident, str) or not IDENT.fullmatch(ident):
            raise ValueError('Unknown review item')
        with self.lock:
            row = self.items().get(ident)
            if ident in read(self.root / 'inactive.json', {}):
                raise ValueError('This comparison is superseded; its earlier records are preserved')
            if row is None or verdict not in VERDICTS[row['kind']]:
                raise ValueError('Unknown item or verdict')
            path = self.root / 'answers' / f'{ident}.json'
            value = {'id': ident, 'verdict': verdict, 'note': str(note)[:500], 'fingerprint': fingerprint(row),
                     'saved_at': datetime.now(timezone.utc).isoformat(), 'source': 'human'}
            existing = read(path, {})
            if existing:
                if all(existing.get(k) == value[k] for k in ('verdict', 'note', 'fingerprint')):
                    return existing
                raise ValueError('A saved answer already exists; it has not been overwritten')
            path.parent.mkdir(parents=True, exist_ok=True)
            # Exclusive creation also protects against another server instance.
            try:
                with path.open('x', encoding='utf-8') as handle:
                    json.dump(value, handle, ensure_ascii=False)
            except FileExistsError as exc:
                raise ValueError('A saved answer already exists') from exc
            return value

    def media(self, name):
        if not isinstance(name, str) or not MEDIA.fullmatch(name):
            return None
        allowed = {n for row in self.items().values() for n in [row.get('video'), *row.get('images', [])] if isinstance(n, str)}
        path = (self.root / name).resolve()
        if name not in allowed or path.parent != self.root.resolve() or not path.is_file():
            return None
        return path
