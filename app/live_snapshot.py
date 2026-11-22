"""Read-only, expiring bridge for a local analysis producer.

The producer writes a generation-specific JPEG, then atomically replaces
snapshot.json. This module never starts analysis or modifies review labels.
"""
import json
import re
from datetime import datetime, timezone
from pathlib import Path


def empty_analysis():
    return {'timestamp': None, 'players': [],
            'metrics': {'team_width_m': None, 'team_length_m': None},
            'feedback': [], 'demo': False}


def unavailable_status():
    return {'status': 'error', 'source': None, 'fps': None, 'latency_ms': None,
            'message': '라이브 분석 결과가 없거나 갱신이 중단됐습니다.'}


class LiveSnapshot:
    def __init__(self, directory, max_age_s=3.0):
        self.directory = Path(directory).resolve()
        self.max_age_s = max_age_s

    def read(self, now=None):
        try:
            path = self.directory / 'snapshot.json'
            if path.stat().st_size > 2_000_000:
                return None
            value = json.loads(path.read_text(encoding='utf-8'),
                               parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite')))
            timestamp = datetime.fromisoformat(value['updated_at'].replace('Z', '+00:00'))
            if timestamp.tzinfo is None:
                return None
            age = ((now or datetime.now(timezone.utc)) - timestamp).total_seconds()
            if not 0 <= age < self.max_age_s:
                return None
            status, analysis = value['status'], value['analysis']
            if not isinstance(status, dict) or status.get('status') not in ('idle', 'running', 'error'):
                return None
            if not isinstance(analysis, dict) or not isinstance(analysis.get('players'), list) or not isinstance(analysis.get('feedback'), list):
                return None
            if not isinstance(analysis.get('metrics'), dict) or not isinstance(analysis.get('demo'), bool):
                return None
            name = value.get('frame_file')
            if not isinstance(name, str) or not re.fullmatch(r'frame-[A-Za-z0-9_-]{1,80}\.jpg', name):
                return None
            frame = (self.directory / name).resolve()
            if frame.parent != self.directory:
                return None
            # Never expose a producer's local filename or stream credentials.
            status = dict(status, source='recorded_replay' if status.get('source') else None)
            return {'status': status, 'analysis': analysis, 'frame': frame,
                    'timestamp': value['updated_at'], 'age_ms': age * 1000}
        except (OSError, ValueError, TypeError, KeyError, AttributeError, OverflowError):
            return None

    def frame(self):
        value = self.read()
        if value is None or value['status']['status'] != 'running':
            return None
        try:
            if value['frame'].stat().st_size > 2_000_000:
                return None
            data = value['frame'].read_bytes()
            if not data.startswith(b'\xff\xd8'):
                return None
            return data, {'X-Frame-Timestamp': value['timestamp'],
                          'X-Frame-Age-Ms': str(round(value['age_ms'], 2)),
                          'Cache-Control': 'no-store'}
        except OSError:
            return None
