"""Loopback-only SRT security test. Pass --ffmpeg and --mediamtx executable paths.

Random test secrets appear only in process arguments and a temporary config;
other local processes can inspect arguments during this test. No secrets are logged.
"""
import argparse
import os
import secrets
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.parse import urlencode

parser = argparse.ArgumentParser()
parser.add_argument('--ffmpeg', required=True)
parser.add_argument('--mediamtx', required=True)
args = parser.parse_args()
server = args.mediamtx
ffmpeg = args.ffmpeg
pw = secrets.token_hex(12)
pub_pass = secrets.token_hex(12)
read_pass = secrets.token_hex(12)
config = f'''logLevel: error
rtsp: false
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
  - user: testpub
    pass: {pw}
    ips: [127.0.0.1]
    permissions:
      - action: publish
        path: match
  - user: testread
    pass: {pw}
    ips: [127.0.0.1]
    permissions:
      - action: read
        path: match
paths:
  match:
    srtPublishPassphrase: {pub_pass}
    srtReadPassphrase: {read_pass}
'''
def url(action, auth, phrase):
    return 'srt://127.0.0.1:18890?' + urlencode({'streamid':f'{action}:match:{action == "publish" and "testpub" or "testread"}:{auth}', 'passphrase':phrase, 'pbkeylen':'16', 'pkt_size':'1316'})

def ff(args):
    return subprocess.Popen([ffmpeg, '-hide_banner', '-loglevel', 'quiet', *args], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

with tempfile.TemporaryDirectory() as temp:
    path = Path(temp) / 'mediamtx.yml'
    path.write_text(config, encoding='utf-8')
    creation = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    server_proc = subprocess.Popen([str(server), str(path)], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=creation)
    publisher = None
    try:
        time.sleep(1)
        if server_proc.poll() is not None: raise RuntimeError('server failed to start')
        # The server must reject bad auth and bad encryption keys independently.
        def try_publish(auth, phrase):
            p = ff(['-f','lavfi','-i','testsrc=size=320x180:rate=10','-t','1','-c:v','libx264','-pix_fmt','yuv420p','-f','mpegts',url('publish',auth,phrase)])
            try: return p.wait(timeout=10)
            except subprocess.TimeoutExpired: p.kill(); p.wait(); return None
        bad_pub_auth = try_publish('invalid-password',pub_pass) not in (0,None)
        bad_pub_pass = try_publish(pw,'wrong-passphrase123456') not in (0,None)
        print('bad_publish_auth_rejected', bad_pub_auth, flush=True)
        print('bad_publish_passphrase_rejected', bad_pub_pass, flush=True)
        publisher = ff(['-re','-f','lavfi','-i','testsrc=size=320x180:rate=10','-t','35','-c:v','libx264','-pix_fmt','yuv420p','-g','10','-preset','ultrafast','-f','mpegts',url('publish',pw,pub_pass)])
        time.sleep(3)
        def try_read(auth, phrase):
            p = ff(['-i',url('read',auth,phrase),'-frames:v','10','-f','null','-'])
            try: return p.wait(timeout=12)
            except subprocess.TimeoutExpired: p.kill(); p.wait(); return None
        bad_read_auth = try_read('invalid-password',read_pass) not in (0,None)
        bad_read_pass = try_read(pw,'wrong-passphrase123456') not in (0,None)
        print('bad_read_auth_rejected', bad_read_auth, flush=True)
        print('bad_read_passphrase_rejected', bad_read_pass, flush=True)
        result = try_read(pw,read_pass)
        print('ten_frames_read_exit_code', result, flush=True)
        print('publisher_running', publisher.poll() is None, flush=True)
        if not all((bad_pub_auth, bad_pub_pass, bad_read_auth, bad_read_pass, result == 0, publisher.poll() is None)):
            raise RuntimeError('SRT security smoke test failed')
    finally:
        if publisher and publisher.poll() is None: publisher.kill(); publisher.wait()
        server_proc.terminate(); server_proc.wait(timeout=10)
