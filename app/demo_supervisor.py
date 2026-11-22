"""Temporary public-demo stack; defaults to local-only, no network modifications."""
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from app.plaintext_demo import one_ipv4, demo_srt_config
from app.demo_job import ChildJob

ROOT = Path(__file__).resolve().parent.parent


def main():
    env = os.environ.copy()
    env.setdefault('DEMO_BIND_IP', '127.0.0.1')
    env.setdefault('DEMO_SOURCE_IP', '127.0.0.1')
    one_ipv4(env['DEMO_BIND_IP']); one_ipv4(env['DEMO_SOURCE_IP'])
    children=[]
    job=ChildJob()
    temp=tempfile.TemporaryDirectory(prefix='football-demo-stack-')
    config=Path(temp.name)/'mediamtx.yml'
    config.write_text(demo_srt_config(env['DEMO_BIND_IP'],env['DEMO_SOURCE_IP'], allow_cellular=env.get('DEMO_SRT_ALLOW_ANY') == '1'),encoding='utf-8')
    env={k:v for k,v in env.items() if not k.upper().startswith('MTX_')}
    commands = [
        [sys.executable, '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8000', '--no-access-log'],
        [str(ROOT/'mediamtx'/'mediamtx.exe'), str(config)],
        [sys.executable, '-m', 'app.plaintext_demo', 'gateway'],
    ]
    try:
        for command in commands:
            process=subprocess.Popen(command, cwd=ROOT, env=env, stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            children.append(process)
            job.add(process)
        print('Public-demo supervisor started; services are unencrypted.', flush=True)
        while True:
            if any(process.poll() is not None for process in children): raise RuntimeError('A child process exited')
            try:
                with urllib.request.urlopen('http://127.0.0.1:8000/api/v1/status',timeout=2) as response:
                    import json
                    state=json.load(response)
                    status=state.get('status')
                if status in ('idle','error') and state.get('input_mode') != 'file':
                    request=urllib.request.Request('http://127.0.0.1:8000/api/v1/start',
                        data=b'{"source":"rtsp://127.0.0.1:18554/match"}',
                        headers={'Content-Type':'application/json'},method='POST')
                    try: urllib.request.urlopen(request,timeout=2).close()
                    except urllib.error.HTTPError: pass
            except (OSError, urllib.error.URLError): pass
            time.sleep(2)
    except KeyboardInterrupt:
        pass
    finally:
        job.close()
        for process in children:
            if process.poll() is None: process.terminate()
        for process in children:
            try: process.wait(timeout=8)
            except subprocess.TimeoutExpired: process.kill(); process.wait()
        temp.cleanup()


if __name__ == '__main__': main()
