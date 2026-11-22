"""Isolated loopback integration test; generated secrets in process args temporarily.

Run: python -m tests.srt_path_smoke --ffmpeg PATH --mediamtx PATH
Does not open router/firewall. Other local processes can inspect test arguments.
"""
import argparse
import os
import secrets
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.parse import urlencode
from app.srt_path_ingest import config_for, secure_environment

parser=argparse.ArgumentParser()
parser.add_argument('--ffmpeg',required=True)
parser.add_argument('--mediamtx',required=True)
args=parser.parse_args()
phrase=secrets.token_hex(24)
env=secure_environment({**os.environ, 'FOOTBALL_SRT_PASSPHRASE':phrase})
flags=getattr(subprocess,'CREATE_NO_WINDOW',0)

def execute(command, *, env=None):
    return subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,env=env,creationflags=flags)

def url(passphrase):
    params={'streamid':'publish:match','pkt_size':'1316'}
    if passphrase is not None: params.update(passphrase=passphrase,pbkeylen='16')
    return 'srt://127.0.0.1:18990?' + urlencode(params)

def sender(passphrase):
    return execute([args.ffmpeg,'-hide_banner','-loglevel','quiet','-re','-f','lavfi','-i','testsrc=size=320x180:rate=10','-t','35','-c:v','libx264','-g','10','-pix_fmt','yuv420p','-preset','ultrafast','-f','mpegts',url(passphrase)])

def stop(proc):
    if proc and proc.poll() is None:
        proc.kill(); proc.wait(timeout=10)

with tempfile.TemporaryDirectory(prefix='srt-path-smoke-') as temp:
    path=Path(temp)/'local.yml'
    server=None; publisher=None
    try:
        path.write_text(config_for('127.0.0.1','127.0.0.2',18990,18555),encoding='utf-8')
        server=execute([args.mediamtx,str(path)],env=env); time.sleep(1)
        if server.poll() is not None: raise RuntimeError('server start failed')
        rejected=sender(phrase)
        try: bad_source=rejected.wait(timeout=8)!=0
        except subprocess.TimeoutExpired: bad_source=False; stop(rejected)
        stop(server)
        path.write_text(config_for('127.0.0.1','127.0.0.1',18990,18555),encoding='utf-8')
        server=execute([args.mediamtx,str(path)],env=env); time.sleep(1)
        if server.poll() is not None: raise RuntimeError('server restart failed')
        rejected=sender('wrong-passphrase1234567890123456')
        try: bad_phrase=rejected.wait(timeout=8)!=0
        except subprocess.TimeoutExpired: bad_phrase=False; stop(rejected)
        rejected=sender(None)
        try: no_phrase=rejected.wait(timeout=8)!=0
        except subprocess.TimeoutExpired: no_phrase=False; stop(rejected)
        publisher=sender(phrase); time.sleep(3)
        reader=execute([args.ffmpeg,'-hide_banner','-loglevel','quiet','-rtsp_transport','tcp','-i','rtsp://127.0.0.1:18555/match','-frames:v','10','-f','null','-'])
        try: frames=reader.wait(timeout=15)==0
        except subprocess.TimeoutExpired: frames=False; stop(reader)
        print('wrong_source_rejected',bad_source,'wrong_passphrase_rejected',bad_phrase,'no_passphrase_rejected',no_phrase,'ten_frames_decoded',frames,flush=True)
        if not all((bad_source,bad_phrase,no_phrase,frames)): raise RuntimeError('SRT path test failed')
    finally:
        stop(publisher); stop(server)
