"""Local-only, plaintext test; no private information in frames or metadata."""
import os
import subprocess
import tempfile
import time
from pathlib import Path
from app.plaintext_demo import demo_srt_config

ROOT=Path(__file__).resolve().parents[1]
ffmpeg=ROOT.parent.parent/'work'/'ffmpeg-local'/'ffmpeg-9.0.2-essentials_build'/'bin'/'ffmpeg.exe'
server=ROOT/'mediamtx'/'mediamtx.exe'
flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
def run(args,env=None): return subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=flags,env=env)
def stop(process):
    if process and process.poll() is None: process.kill(); process.wait(timeout=10)

with tempfile.TemporaryDirectory() as directory:
    config=Path(directory)/'mediamtx.yml'; config.write_text(demo_srt_config('127.0.0.1','127.0.0.1', allow_cellular=os.environ.get('DEMO_TEST_CELLULAR') == '1'),encoding='utf-8')
    service=publisher=reader=None
    try:
        service=run([str(server),str(config)],env={k:v for k,v in os.environ.items() if not k.upper().startswith('MTX_')}); time.sleep(1)
        if service.poll() is not None: raise RuntimeError('MediaMTX did not start')
        publisher=run([str(ffmpeg),'-nostdin','-re','-f','lavfi','-i','testsrc=size=320x180:rate=10','-t','25','-c:v','libx264','-g','10','-pix_fmt','yuv420p','-preset','ultrafast','-f','mpegts','srt://127.0.0.1:8890?streamid=publish:match&pkt_size=1316'])
        time.sleep(3)
        reader=run([str(ffmpeg),'-nostdin','-rtsp_transport','tcp','-i','rtsp://127.0.0.1:18554/match','-frames:v','10','-f','null','-'])
        ok=reader.wait(timeout=15)==0
        print('plaintext_local_srt_ten_frames=',ok)
        if not ok: raise RuntimeError('Local decode failed')
    finally:
        stop(reader); stop(publisher); stop(service)
