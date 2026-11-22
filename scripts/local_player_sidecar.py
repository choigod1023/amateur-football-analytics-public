"""Optional local-only WHEP video preview; never bind a public interface."""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile
import time
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.demo_job import ChildJob

CONFIG = '''logLevel: error
rtsp: true
rtspAddress: 127.0.0.1:18557
rtspTransports: [tcp]
rtmp: false
hls: false
webrtc: true
webrtcAddress: 127.0.0.1:18889
webrtcLocalUDPAddress: 127.0.0.1:18189
webrtcIPsFromInterfaces: false
webrtcAdditionalHosts: [127.0.0.1]
webrtcAllowOrigins: ['http://127.0.0.1:18081']
moq: false
srt: false
api: false
metrics: false
pprof: false
playback: false
authMethod: internal
authInternalUsers:
  - user: any
    ips: [127.0.0.1/32]
    permissions:
      - action: publish
        path: player
      - action: read
        path: player
paths:
  player:
    overridePublisher: false
'''

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mediamtx', type=Path, required=True)
    parser.add_argument('--ffmpeg', type=Path, required=True)
    args = parser.parse_args()
    if not args.mediamtx.is_file() or not args.ffmpeg.is_file():
        parser.error('MediaMTX and FFmpeg binaries must exist')
    # Fixed upstream and fixed listeners mean user input cannot open a network service.
    ffmpeg = [str(args.ffmpeg.resolve()), '-hide_banner', '-loglevel', 'error', '-nostdin',
              '-rtsp_transport', 'tcp', '-i', 'rtsp://127.0.0.1:18555/match', '-an',
              '-vf', 'scale=1920:-2', '-c:v', 'libx264', '-profile:v', 'baseline',
              '-pix_fmt', 'yuv420p', '-preset', 'ultrafast', '-tune', 'zerolatency',
              '-g', '25', '-bf', '0', '-b:v', '3M', '-rtsp_transport', 'tcp',
              '-f', 'rtsp', 'rtsp://127.0.0.1:18557/player']
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith('MTX_')}
    flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    job = ChildJob()
    with tempfile.TemporaryDirectory(prefix='football-local-player-') as tmp:
        path = Path(tmp) / 'mediamtx.yml'
        path.write_text(CONFIG, encoding='utf-8')
        try:
            server = subprocess.Popen([str(args.mediamtx.resolve()), str(path)], env=env,
                                      stdin=subprocess.DEVNULL, creationflags=flags)
            job.add(server)
            encoder = None
            while server.poll() is None:
                if encoder is None or encoder.poll() is not None:
                    encoder = subprocess.Popen(ffmpeg, env=env, stdin=subprocess.DEVNULL, creationflags=flags)
                    job.add(encoder)
                time.sleep(3)
            raise RuntimeError('Local MediaMTX stopped')
        except KeyboardInterrupt:
            pass
        finally:
            job.close()

if __name__ == '__main__': main()
