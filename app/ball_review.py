"""Ball positions confirmed by a person on short continuous clips.

Clips, frames and candidate circles are prepared offline into <store>/ball/clips/<clip>/. The circles are
proposals from an unverified model; only a click by the reviewer becomes a label.
"""
import json
import math
import os
import re
import tempfile
import threading
import time
from pathlib import Path

CLIP_ID = re.compile(r'^b[0-9]{2,3}$')
FRAME_NAME = re.compile(r'^f_[0-9]{3}\.jpg$')
STATES = ('ball', 'none', 'unsure')
SOURCES = ('suggestion', 'tile', 'key', 'snap', 'manual')
VERDICTS = ('ok', 'rejected', 'moved')
WIDTH, HEIGHT = 1920, 1080


class BallReview:
    def __init__(self, directory):
        self.root = Path(directory) / 'ball'
        self.lock = threading.Lock()

    def _index(self):
        try:
            data = json.loads((self.root / 'index.json').read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def _clip(self, clip_id):
        if not isinstance(clip_id, str) or not CLIP_ID.match(clip_id):
            return None
        try:
            data = json.loads((self.root / 'clips' / clip_id / 'candidates.json').read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return None
        return data if isinstance(data, dict) else None

    def _labels(self, clip_id):
        try:
            data = json.loads((self.root / 'labels' / (clip_id + '.json')).read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def listing(self):
        with self.lock:
            clips = []
            for item in self._index().get('clips', []):
                clip = self._clip(item.get('id')) if isinstance(item, dict) else None
                if clip is None:
                    continue
                labels = self._labels(clip['id'])
                states = [v.get('state') for v in labels.values() if isinstance(v, dict)]
                balls = [v for v in labels.values() if isinstance(v, dict) and v.get('state') == 'ball']
                verdicts = [v.get('verified') for v in balls]
                clips.append({'id': clip['id'], 'camera': clip.get('camera'), 'start': clip.get('start'), 'fps': clip.get('fps'),
                              'frames': len(clip.get('frames', [])), 'labeled': len(states),
                              'ball': states.count('ball'), 'none': states.count('none'), 'unsure': states.count('unsure'),
                              'verified_ok': verdicts.count('ok'), 'verified_moved': verdicts.count('moved'),
                              'verified_rejected': verdicts.count('rejected'),
                              'unverified': sum(1 for v in verdicts if v not in VERDICTS)})
            return {'clips': clips, 'note': self._index().get('note')}

    def clip(self, clip_id):
        with self.lock:
            data = self._clip(clip_id)
            if data is None:
                return None
            return {'id': data['id'], 'camera': data.get('camera'), 'start': data.get('start'), 'fps': data.get('fps'),
                    'width': WIDTH, 'height': HEIGHT, 'frames': data.get('frames', []), 'labels': self._labels(clip_id)}

    def set_label(self, clip_id, frame, state, x=None, y=None, source=None):
        """Save, or with state 'clear' remove, the answer for one frame."""
        if not isinstance(frame, str) or not FRAME_NAME.match(frame):
            raise ValueError('Invalid frame')
        if state != 'clear' and state not in STATES:
            raise ValueError('Unknown state')
        if state == 'ball':
            if any(type(v) not in (int, float) or not math.isfinite(v) for v in (x, y)) or not (0 <= x <= WIDTH and 0 <= y <= HEIGHT):
                raise ValueError('The ball position is outside the frame')
        with self.lock:
            data = self._clip(clip_id)
            if data is None or frame not in {f.get('file') for f in data.get('frames', [])}:
                raise ValueError('Unknown clip or frame')
            labels = self._labels(clip_id)
            if state == 'clear':
                labels.pop(frame, None)
            else:
                labels[frame] = {'state': state, 'updated': time.strftime('%Y-%m-%d %H:%M:%S')}
                if state == 'ball':
                    labels[frame].update(x=round(float(x), 1), y=round(float(y), 1))
                    if source in SOURCES:
                        labels[frame]['source'] = source
            folder = self.root / 'labels'
            folder.mkdir(parents=True, exist_ok=True)
            temp_name = None
            try:
                with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=folder, suffix='.tmp', delete=False) as output:
                    temp_name = output.name
                    json.dump(labels, output, ensure_ascii=False)
                os.replace(temp_name, folder / (clip_id + '.json'))
            finally:
                if temp_name and os.path.exists(temp_name):
                    os.unlink(temp_name)
            return labels.get(frame)

    def verify(self, clip_id, frame, verdict, x=None, y=None):
        """Mark a saved ball position as right, wrong or moved. The earlier position stays in the history."""
        if verdict not in VERDICTS:
            raise ValueError('Unknown verdict')
        if verdict == 'moved' and (any(type(v) not in (int, float) or not math.isfinite(v) for v in (x, y)) or
                                   not (0 <= x <= WIDTH and 0 <= y <= HEIGHT)):
            raise ValueError('The corrected position is outside the frame')
        with self.lock:
            if self._clip(clip_id) is None:
                raise ValueError('Unknown clip or frame')
            labels = self._labels(clip_id)
            label = labels.get(frame)
            if not isinstance(label, dict) or label.get('state') != 'ball':
                raise ValueError('There is no saved ball position to check')
            now = time.strftime('%Y-%m-%d %H:%M:%S')
            if verdict == 'moved':
                label.setdefault('history', []).append(
                    {'x': label.get('x'), 'y': label.get('y'), 'source': label.get('source'), 'at': label.get('updated')})
                label.update(x=round(float(x), 1), y=round(float(y), 1), source='verify_click')
            label['verified'] = verdict
            label['verified_at'] = now
            labels[frame] = label
            folder = self.root / 'labels'
            temp_name = None
            try:
                with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=folder, suffix='.tmp', delete=False) as output:
                    temp_name = output.name
                    json.dump(labels, output, ensure_ascii=False)
                os.replace(temp_name, folder / (clip_id + '.json'))
            finally:
                if temp_name and os.path.exists(temp_name):
                    os.unlink(temp_name)
            return label

    def media(self, clip_id, name):
        if not isinstance(clip_id, str) or not CLIP_ID.match(clip_id) or not isinstance(name, str) or not FRAME_NAME.match(name):
            return None
        path = self.root / 'clips' / clip_id / name
        return path if path.is_file() else None
