"""Loopback-only SRT -> MediaMTX -> RTSP -> API smoke test; no real credentials.

Usage: python -m tests.secure_stream_smoke --ffmpeg PATH --mediamtx PATH
Add --video PATH for a local input instead of generated test frames. Test secrets
are random, exist only in memory/process arguments and an automatically removed
temporary config. Run on a trusted machine; process arguments can be inspected
by other local processes while the test is running.
"""
import argparse
import secrets
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.parse import urlencode

from fastapi.testclient import TestClient
from app.main import app

parser = argparse.ArgumentParser()
parser.add_argument('--ffmpeg', required=True)
parser.add_argument('--mediamtx', required=True)
parser.add_argument('--video')
args = parser.parse_args()
password, phrase = secrets.token_hex(12), secrets.token_hex(12)
config = f'''logLevel: error
rtsp: true
rtspAddress: 127.0.0.1:18554
rtspTransports: [tcp]
rtmp: false
hls: false
webrtc: false
moq: false
srt: true
srtAddress: 127.0.0.1:18890
api: false
metrics: false
pprof: false
authMethod: internal
authInternalUsers:
  - user: pub
    pass: {password}
    ips: [127.0.0.1]
    permissions:
      - action: publish
        path: match
  - user: any
    ips: [127.0.0.1]
    permissions:
      - action: read
        path: match
paths:
  match:
    srtPublishPassphrase: {phrase}
'''
query = urlencode({'streamid': f'publish:match:pub:{password}', 'passphrase':phrase, 'pbkeylen':'16', 'pkt_size':'1316'})
source = 'srt://127.0.0.1:18890?' + query
creation = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
def launch(command):
    return subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=creation)

with tempfile.TemporaryDirectory() as directory:
    path = Path(directory) / 'mediamtx.yml'
    path.write_text(config, encoding='utf-8')
    server = launch([args.mediamtx, str(path)])
    publisher = None
    try:
        time.sleep(1)
        if server.poll() is not None: raise RuntimeError('MediaMTX did not start')
        input_args = ['-stream_loop','-1','-re','-i',args.video] if args.video else ['-re','-f','lavfi','-i','testsrc=size=320x180:rate=10']
        publisher = launch([args.ffmpeg,'-loglevel','quiet',*input_args,'-an','-t','40','-vf','scale=1280:-2','-c:v','libx264','-pix_fmt','yuv420p','-g','10','-preset','ultrafast','-f','mpegts',source])
        time.sleep(3)
        if publisher.poll() is not None: raise RuntimeError('Publisher stopped before analysis')
        with TestClient(app) as client:
            deadline=time.monotonic()+30
            analysis={}; status={}
            last_attempt = 0.0
            while time.monotonic() < deadline:
                status=client.get('/api/v1/status').json()
                analysis=client.get('/api/v1/analysis').json()
                if analysis['timestamp']: break
                if status['status'] in ('idle', 'error') and time.monotonic()-last_attempt > 2:
                    response=client.post('/api/v1/start', json={'source':'rtsp://127.0.0.1:18554/match'})
                    if response.status_code not in (200, 409): raise RuntimeError(f'API start failed: {response.status_code}')
                    last_attempt = time.monotonic()
                time.sleep(.2)
            print('status', status['status'])
            print('message', status.get('message'))
            print('analysis_timestamp_present', bool(analysis.get('timestamp')))
            print('players', len(analysis.get('players', [])))
            print('teams', sorted({player['team'] for player in analysis.get('players', [])}))
            print('metrics', analysis.get('metrics'))
            print('fps', status.get('fps'))
            print('post_decode_latency_ms', status.get('latency_ms'))
            client.post('/api/v1/stop')
            deadline = time.monotonic() + 8
            while client.get('/api/v1/status').json()['status'] == 'running' and time.monotonic() < deadline:
                time.sleep(.1)
            if not analysis.get('timestamp'): raise RuntimeError('No frame analyzed')
    finally:
        if publisher and publisher.poll() is None: publisher.kill(); publisher.wait()
        server.terminate(); server.wait(timeout=10)
