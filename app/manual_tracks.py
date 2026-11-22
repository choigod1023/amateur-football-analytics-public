"""Short-lived, user-confirmed roles for continuously visible tracking IDs.

The nonce prevents annotations made against an earlier incarnation of the same
ID from being applied after it disappears. It does not prove physical identity.
"""
import secrets
import threading
import time
import base64
from collections import Counter


class ManualTracks:
    def __init__(self, ttl_s=10, snapshot_ttl_s=None):
        self.ttl_s = ttl_s
        self.snapshot_ttl_s = ttl_s if snapshot_ttl_s is None else snapshot_ttl_s
        self.lock = threading.Lock()
        self.records = {}
        self.snapshots = {}
        self.latest_snapshot = None
        self._generation = 0

    def reset(self):
        with self.lock:
            self.records.clear()
            self.snapshots.clear()
            self.latest_snapshot = None
            self._generation += 1

    def generation(self):
        with self.lock:
            return self._generation

    def observe(self, ids):
        counts = Counter(ids)
        ids = {tid for tid, count in counts.items() if count == 1}
        with self.lock:
            for tid in set(self.records) - ids:
                del self.records[tid]
            for tid in ids:
                if tid not in self.records:
                    self.records[tid] = {'token': secrets.token_urlsafe(18), 'role': None, 'team': None, 'expires': 0.}

    def publish_snapshot(self, jpeg, players, captured_at):
        now = time.monotonic()
        with self.lock:
            entry = {'created': now, 'captured_at': captured_at,
                     'image_jpeg_base64': base64.b64encode(jpeg).decode('ascii'),
                     'players': [dict(p) for p in players if p.get('annotation_token')]}
            self.latest_snapshot = entry

    def get_snapshot(self):
        with self.lock:
            entry = self.latest_snapshot
            if not entry or time.monotonic()-entry['created'] > self.ttl_s:
                return None
            now = time.monotonic()
            self.snapshots = {k:v for k,v in self.snapshots.items() if now-v['created'] <= self.snapshot_ttl_s}
            if len(self.snapshots) >= 64:
                del self.snapshots[next(iter(self.snapshots))]
            token = secrets.token_urlsafe(18)
            self.snapshots[token] = entry
            return {'snapshot_token': token, 'captured_at': entry['captured_at'],
                    'image_jpeg_base64': entry['image_jpeg_base64'], 'players': [dict(p) for p in entry['players']],
                    'expires_in_s': round(max(0., self.snapshot_ttl_s-(now-entry['created'])), 2)}

    def assign(self, snapshot_token, tid, token, role, team):
        with self.lock:
            if not isinstance(token, str) or not token.isascii():
                return False
            snap = self.snapshots.get(snapshot_token)
            if not snap or time.monotonic()-snap['created'] > self.snapshot_ttl_s:
                return False
            if not any(p['id'] == tid and secrets.compare_digest(p['annotation_token'],token) for p in snap['players']):
                return False
            rec = self.records.get(tid)
            if rec is None or not secrets.compare_digest(rec['token'], token):
                return False
            rec.update(role=role, team=team, expires=time.monotonic()+self.ttl_s)
            return True

    def get(self, tid):
        with self.lock:
            rec = self.records.get(tid)
            if rec is None:
                return None, 'unknown', None
            if rec['expires'] <= time.monotonic():
                rec.update(role=None, team=None, expires=0.)
            return rec['token'], rec['team'] if rec['role'] in ('player', 'goalkeeper') else 'unknown', rec['role']
