"""End-to-end loopback test with synthetic video, no private data."""
import os, signal, subprocess, sys, time
from pathlib import Path
import httpx

root=Path(__file__).resolve().parents[1]
ffmpeg=root.parent.parent/'work'/'ffmpeg-local'/'ffmpeg-9.0.2-essentials_build'/'bin'/'ffmpeg.exe'
env={**os.environ,'DEMO_BIND_IP':'127.0.0.1','DEMO_SOURCE_IP':'127.0.0.1'}
env={k:v for k,v in env.items() if not k.upper().startswith('MTX_')}
stack=subprocess.Popen([sys.executable,'-m','app.demo_supervisor'],cwd=root,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=getattr(subprocess,'CREATE_NEW_PROCESS_GROUP',0))
sender=None
try:
    time.sleep(4)
    if stack.poll() is not None: raise RuntimeError('Supervisor exited')
    sender=subprocess.Popen([str(ffmpeg),'-nostdin','-re','-f','lavfi','-i','testsrc=size=320x180:rate=10','-t','30','-c:v','libx264','-g','10','-pix_fmt','yuv420p','-preset','ultrafast','-f','mpegts','srt://127.0.0.1:8890?streamid=publish:match&pkt_size=1316'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    found=False; deadline=time.monotonic()+35
    with httpx.Client(timeout=2,trust_env=False) as client:
        while time.monotonic()<deadline:
            if stack.poll() is not None: raise RuntimeError('Supervisor exited')
            try:
                status=client.get('http://127.0.0.1:8443/api/v1/status')
                frame=client.get('http://127.0.0.1:8443/api/v1/frame.jpg')
                if status.status_code==200 and frame.status_code==200 and frame.headers.get('content-type','').startswith('image/jpeg'):
                    assert len(frame.content)<=2_000_000 and frame.headers['cache-control']=='no-store'
                    assert client.post('http://127.0.0.1:8443/api/v1/start').status_code==404
                    found=True; break
            except httpx.HTTPError: pass
            time.sleep(.5)
    print('srt_to_http_frame_success=',found,flush=True)
    if not found: raise RuntimeError('No JPEG frame')
finally:
    if sender and sender.poll() is None: sender.kill(); sender.wait()
    if stack.poll() is None:
        stack.send_signal(signal.CTRL_BREAK_EVENT if os.name=='nt' else signal.SIGINT)
        try: stack.wait(timeout=12)
        except subprocess.TimeoutExpired: stack.kill(); stack.wait()
