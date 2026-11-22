"""Loopback-only socket and automatic shutdown smoke test (uses port 8443)."""
import hashlib
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
import httpx

with tempfile.TemporaryDirectory() as destination:
    env={**os.environ,'TRANSFER_DIR':destination,'TRANSFER_FILENAME':'sample.zip',
         'TRANSFER_SOURCE_IP':'127.0.0.1','TRANSFER_BIND_IP':'127.0.0.1'}
    process=subprocess.Popen([sys.executable,'-m','app.transfer_once'],env=env,
        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    try:
        deadline=time.monotonic()+15
        with httpx.Client(trust_env=False, timeout=2) as client:
            while True:
                if process.poll() is not None: raise RuntimeError('Receiver exited before readiness')
                try:
                    r=client.get('http://127.0.0.1:8443/no-route')
                    if r.status_code==404: break
                except httpx.HTTPError: pass
                if time.monotonic()>deadline: raise RuntimeError('Receiver did not start')
                time.sleep(.1)
            data=b'local sample bytes'
            response=client.post('http://127.0.0.1:8443/upload',content=data,headers={
                'content-type':'application/octet-stream','x-content-sha256':hashlib.sha256(data).hexdigest()})
            assert response.status_code==200 and response.json()['bytes']==len(data)
        assert (Path(destination)/'sample.zip').read_bytes()==data
        assert process.wait(timeout=10)==0
        print('local_upload_and_automatic_exit=True')
    finally:
        if process.poll() is None: process.kill(); process.wait(timeout=5)
