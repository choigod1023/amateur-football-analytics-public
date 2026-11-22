"""Bounded in-memory bookmarks of real, same-frame observations only."""
import copy
import threading
import time
import uuid


class LiveBookmarks:
    def __init__(self, limit=20, max_age_s=1.0):
        self.limit = limit
        self.max_age_s = max_age_s
        self._lock = threading.Lock()
        self._latest = None
        self._items = []

    def clear_latest(self):
        with self._lock:
            self._latest = None

    def publish(self, jpeg, decoded_at, decoded_monotonic, count, metrics, feedback):
        if not isinstance(jpeg, bytes) or not jpeg or len(jpeg) > 2_000_000:
            return
        with self._lock:
            self._latest = {'jpeg': jpeg, 'timestamp': decoded_at, 'monotonic': decoded_monotonic,
                            'people': count, 'metrics': copy.deepcopy(metrics),
                            'feedback': copy.deepcopy(feedback)}

    def mark(self):
        with self._lock:
            source = self._latest
            age = time.monotonic() - source['monotonic'] if source else None
            if source is None or age < 0 or age > self.max_age_s:
                raise ValueError('no_recent_frame')
            if len(self._items) >= self.limit:
                raise ValueError('limit_reached')
            item = dict(source, id=uuid.uuid4().hex, kind='user_marked')
            self._items.append(item)
            return self._public(item)

    @staticmethod
    def _public(item):
        return {key: copy.deepcopy(item[key]) for key in ('id', 'kind', 'timestamp', 'people', 'metrics', 'feedback')}

    def list(self):
        with self._lock:
            return [self._public(item) for item in reversed(self._items)]

    def image(self, identifier):
        with self._lock:
            return next((item['jpeg'] for item in self._items if item['id'] == identifier), None)
