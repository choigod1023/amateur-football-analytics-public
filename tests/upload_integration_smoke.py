"""Exercise real MP4 decoding, GPU inference, upload gateway and JPEG locally."""
import argparse
import tempfile
import time
from pathlib import Path
import httpx
from fastapi.testclient import TestClient
import app.main as backend
from app.plaintext_demo import create_app

parser=argparse.ArgumentParser()
parser.add_argument('--video',required=True)
args=parser.parse_args()
video=Path(args.video)
with tempfile.TemporaryDirectory(prefix='football-upload-test-') as temp:
    backend.UPLOAD_DIR=Path(temp)/'uploads'
    app=create_app('127.0.0.1',upstream_transport=httpx.ASGITransport(app=backend.app))
    try:
        with TestClient(app,client=('127.0.0.1',1234)) as client:
            response=client.post('/api/v1/upload',content=video.read_bytes(),headers={'content-type':'video/mp4'})
            print('upload_http',response.status_code,flush=True)
            if response.status_code!=200: raise RuntimeError('Upload failed')
            deadline=time.monotonic()+40
            while time.monotonic()<deadline:
                status=client.get('/api/v1/status').json()
                analysis=client.get('/api/v1/analysis').json()
                frame=client.get('/api/v1/frame.jpg')
                if frame.status_code==200 and analysis['timestamp']: break
                if status['status']=='error': raise RuntimeError('Analysis failed')
                time.sleep(.2)
            print('mode',status['input_mode'],'source',status['source'],'state',status['status'],flush=True)
            print('analysis_timestamp_present',bool(analysis['timestamp']),'frame_http',frame.status_code,'jpeg_bytes',len(frame.content),'no_store',frame.headers.get('cache-control')=='no-store',flush=True)
            if frame.status_code!=200 or not analysis['timestamp']: raise RuntimeError('No analyzed frame')
    finally:
        backend.stop_event.set()
        if backend.worker: backend.worker.join(timeout=15)
        if backend.worker and backend.worker.is_alive(): raise RuntimeError('Analysis did not stop')
