"""Local read-only dashboard preview using recorded observations, not live inference."""
import argparse
import json
import sys
from pathlib import Path
from datetime import datetime, timezone
from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
import uvicorn
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.evaluate_position_recovery import evaluate
from app.live_publish import dashboard_players


def create_preview(video, trace):
    rows = [json.loads(line) for line in Path(trace).read_text(encoding='utf-8').splitlines()]
    frames = evaluate(rows)['frames']
    root = Path(__file__).resolve().parents[1] / 'web'
    app = FastAPI()
    @app.get('/api/v1/status')
    def status():
        return dict(status='running',source='recorded-observation-preview',fps=5,latency_ms=None,
                    message='저장 관측값 재생 · 실시간 추론 아님',replay=True,input_mode='file')
    @app.get('/api/v1/analysis')
    def analysis(t: float = Query(0, ge=0, le=86400)):
        index = max((i for i, f in enumerate(frames) if f['time'] <= t), default=0)
        frame = frames[index]
        ready = rows[index].get('camera_ready', True)
        raw = dashboard_players(frame['accepted'], {'length':89,'width':60})
        players = dashboard_players(frame['display'], {'length':89,'width':60})
        excess = any(sum(p['team']==team for p in raw)>11 for team in ('home','away'))
        alerts = [a for f in frames[:index+1] for a in f['alerts'] if 0 <= t-a['time'] < 8] if ready and not excess else []
        feedback = [{k:a[k] for k in ('observation','interpretation','suggestion','limitations','directive') if k in a} for a in alerts[-5:]]
        own = [p for p in raw if p['team']=='home' and p['x'] is not None]
        valid = ready and not excess and len(own)>=3
        return dict(timestamp=datetime.now(timezone.utc).isoformat(),players=players,raw_players=raw,
                    source_time_s=frame['time'],demo=False,replay=True,own_team='home',
                    calibration_status='estimated_reference' if ready else 'camera_moved',
                    metrics=dict(team_width_m=(max(p['y'] for p in own)-min(p['y'] for p in own))*60 if valid else None,
                                 team_length_m=(max(p['x'] for p in own)-min(p['x'] for p in own))*89 if valid else None),
                    feedback=feedback,coaching_diagnostics=dict(reasons=['팀 후보가 11명을 초과해 코칭을 보류합니다.'] if excess else ['현재 장면의 연속 관측 조건을 충족한 알림이 없습니다.'] if not feedback else [],warnings=['녹화 관측값 재생 프리뷰 · 실제 위치와 전술 정답은 미검증입니다.']))
    @app.get('/recording.mp4')
    def recording():
        return FileResponse(video,media_type='video/mp4')
    @app.get('/')
    def index():
        html = (root/'index.html').read_text(encoding='utf-8')
        import re
        html = re.sub(r'<script src="(?:sequences|manual-confirmation|live-bookmarks|live-video|training-label|review-annotation)\.js"></script>', '', html)
        html = html.replace('<script src="app.js">','<script src="preview-recording.js"></script><script src="app.js">')
        html = html.replace('<section class="intro">', '<section class="intro"><div><h2>개선 버전 프리뷰</h2><p>실제 녹화 영상 + 저장 관측값 재생 · 운영 서버 아님 · 새 GPU 추론 아님</p><p>15초: 후퇴 후보 / 23초: 간격 경고 / 35초: 박스 배치</p><button onclick="document.getElementById(\'video-player\').currentTime=15">15초 코칭</button> <button onclick="document.getElementById(\'video-player\').currentTime=23">23초 간격</button> <button onclick="document.getElementById(\'video-player\').currentTime=35">35초 배치</button><p id="preview-time"></p></div></section><section class="intro" hidden>')
        html = html.replace('</head>','<style>.upload-panel,.access-panel{display:none}</style></head>')
        return HTMLResponse(html)
    app.mount('/',StaticFiles(directory=root),name='web')
    return app

if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('--video',type=Path,required=True);p.add_argument('--trace',type=Path,required=True);p.add_argument('--port',type=int,default=8766)
    a=p.parse_args();uvicorn.run(create_preview(a.video.resolve(),a.trace.resolve()),host='127.0.0.1',port=a.port)
