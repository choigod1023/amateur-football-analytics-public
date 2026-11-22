"""Publish observed replay snapshots; presentation never feeds the analyser."""
import json
import uuid
import time
from datetime import datetime, timezone
from pathlib import Path
import cv2


def replace_snapshot(temp, target):
    """Bound retries for Windows readers temporarily denying delete sharing.

    Never truncate the published file: concurrent readers must see a complete
    old or new snapshot. Persistent permission failures still reach the caller.
    """
    for attempt in range(11):
        try:
            temp.replace(target)
            return
        except PermissionError:
            if attempt == 10:
                raise
            time.sleep(.01)


def dashboard_players(teams, pitch):
    """Pitch-map metres are centred; dashboard coordinates start at top left."""
    players = []
    for team, rows in teams.items():
        for tid, x, y in rows:
            nx, ny = .5 + float(x)/pitch['length'], .5 + float(y)/pitch['width']
            valid = 0 <= nx <= 1 and 0 <= ny <= 1
            players.append({'id': str(tid), 'team': team,
                            'x': nx if valid else None, 'y': ny if valid else None})
    return players


class LivePublisher:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.previous = None
        self.session = uuid.uuid4().hex

    def publish(self, frame, players, alerts, t, pitch, ready, fps, latency_ms, raw_players=None):
        now = datetime.now(timezone.utc).isoformat()
        name = 'frame-' + uuid.uuid4().hex + '.jpg'
        if not cv2.imwrite(str(self.directory / name), frame):
            raise IOError('Could not publish preview')
        metric_players = players if raw_players is None else raw_players
        own = [p for p in metric_players if p['team'] == 'home' and p['x'] is not None]
        over_capacity = any(sum(p['team'] == team for p in metric_players) > 11 for team in ('home', 'away'))
        coaching_ready = ready and not over_capacity
        if not coaching_ready:
            alerts = []
        reason_codes, reasons = [], []
        if not ready:
            reason_codes.append('calibration_unavailable')
            reasons.append('경기장 보정이 유효하지 않아 전술 지표와 코칭을 보류합니다.')
        if over_capacity:
            reason_codes.append('team_capacity_exceeded')
            reasons.append('한 팀의 위치 후보가 11명을 초과해 중복·팀 분류 확인이 필요합니다.')
        if coaching_ready and not alerts:
            reason_codes.append('no_recent_alerts')
            reasons.append('현재 표시할 알림이 없습니다. 연속 관측 조건과 재알림 대기 시간을 적용하며 알림은 8초간 표시합니다.')
        feedback = [{'observation': a.get('observation', a.get('title', '')),
                     'interpretation': a.get('interpretation', a.get('text', '')),
                     'suggestion': a.get('suggestion', a.get('text', '')),
                     'limitations': a.get('limitations', '녹화 재생 시험. 화면 내 관측 선수와 추정 경기장 크기 기반. 공 소유·화면 밖 위치·실제 위치 오차 미검증.')}
                    for a in alerts]
        for item, alert in zip(feedback, alerts):
            if 'directive' in alert:
                item['directive'] = alert['directive']
        data = {'timestamp': now, 'players': players, 'demo': False,
                'recovered_player_ids': [p['id'] for p in players if p.get('observation_kind') == 'low_confidence_recovery'],
                'raw_players': metric_players,
                'position_basis': 'bounded_filtered_observation' if raw_players is not None else 'observed',
                'coaching_diagnostics': {'state': 'blocked' if not coaching_ready else ('ready' if alerts else 'observing'),
                    'coaching_ready': coaching_ready, 'reason_codes': reason_codes, 'reasons': reasons,
                    'alert_display_seconds': 8,
                    'warnings': ['기존 수동 보정을 사용한 녹화 재생 시험이며 위치 정답 오차는 미검증입니다.']},
                'metrics': {'team_width_m': (max(p['y'] for p in own)-min(p['y'] for p in own))*pitch['width'] if len(own)>=3 else None,
                            'team_length_m': (max(p['x'] for p in own)-min(p['x'] for p in own))*pitch['length'] if len(own)>=3 else None},
                'feedback': feedback, 'own_team': 'home', 'replay': True,
                'source_time_s': t, 'session_id': self.session, 'stream_generation': self.session,
                'calibration_status': 'estimated_reference' if ready else 'camera_moved',
                'pitch_dimensions_are_estimates': True}
        if not coaching_ready:
            data['metrics'] = {'team_width_m': None, 'team_length_m': None}
        snapshot = {'updated_at': now, 'frame_file': name,
                    'status': {'status': 'running', 'source': 'recorded-match-replay', 'input_mode': 'file',
                               'replay': True, 'fps': fps, 'latency_ms': latency_ms,
                               'message': '녹화 영상 재생 시험 · 실제 SRT 송출 아님'}, 'analysis': data}
        temp = self.directory / 'snapshot.tmp'
        temp.write_text(json.dumps(snapshot, ensure_ascii=False, allow_nan=False), encoding='utf-8')
        replace_snapshot(temp, self.directory / 'snapshot.json')
        # Keep the preceding image to allow an in-flight reader to finish.
        old = self.previous
        self.previous = name
        for path in self.directory.glob('frame-*.jpg'):
            if path.name not in (name, old):
                try:
                    path.unlink()
                except OSError:
                    pass
        return data
