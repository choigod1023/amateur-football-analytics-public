"""Real MP4 -> analysis -> authenticated loopback HTTPS preview smoke test.

Run: .venv/Scripts/python.exe -m tests.https_preview_smoke --video <local MP4>
Uses ephemeral secrets/cert and private loopback ports 8000, 18443. It neither
modifies trust stores nor tests the Mac browser, SRT or public connectivity.
"""
import argparse, datetime, ipaddress, os, secrets, socket, ssl, subprocess, sys, tempfile, time
from pathlib import Path
import cv2, httpx, numpy as np
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

parser=argparse.ArgumentParser()
parser.add_argument('--video', required=True, help='Path to an existing local MP4')
args=parser.parse_args()
video=Path(args.video).resolve(strict=True)
if not video.is_file() or video.suffix.lower() != '.mp4': raise SystemExit('Provide a local MP4 file')
root=Path(__file__).resolve().parents[1]
procs=[]
with tempfile.TemporaryDirectory(dir=root) as td:
    temp=Path(td); key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'127.0.0.1')]); now=datetime.datetime.now(datetime.timezone.utc)
    cert=(x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(now-datetime.timedelta(minutes=1)).not_valid_after(now+datetime.timedelta(hours=1)).add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address('127.0.0.1'))]),False).sign(key,hashes.SHA256()))
    (temp/'key').write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
    (temp/'cert').write_bytes(cert.public_bytes(serialization.Encoding.PEM)); token=secrets.token_urlsafe(48); (temp/'token').write_text(token)
    python=str(root/'.venv'/'Scripts'/'python.exe'); flags=subprocess.CREATE_NO_WINDOW
    def start(cmd,env=None):
        p=subprocess.Popen(cmd,cwd=root,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=flags); procs.append(p)
    try:
        for port in (8000,18443):
            with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as s:
                s.bind(('127.0.0.1',port))
        start([python,'-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8000'])
        env={**os.environ,'FOOTBALL_PROXY_TOKEN_FILE':str(temp/'token'),'FOOTBALL_PROXY_TLS_CERT':str(temp/'cert'),'FOOTBALL_PROXY_TLS_KEY':str(temp/'key'),'FOOTBALL_PROXY_PORT':'18443','FOOTBALL_PROXY_HOST':'127.0.0.1','FOOTBALL_PROXY_ALLOWED_CIDRS':'127.0.0.1/32','FOOTBALL_PROXY_ALLOWED_ORIGIN':''}
        start([python,'-m','app.read_proxy'],env)
        for _ in range(100):
            try:
                r=httpx.post('http://127.0.0.1:8000/api/v1/start',json={'source':str(video)},timeout=2,trust_env=False)
                if r.status_code==200: break
            except httpx.ConnectError: pass
            time.sleep(.1)
        else: raise RuntimeError('API start failed')
        with httpx.Client(verify=ssl.create_default_context(cafile=str(temp/'cert')),trust_env=False,timeout=5) as c:
            url='https://127.0.0.1:18443/api/v1/frame.jpg'; deadline=time.monotonic()+50
            while time.monotonic()<deadline:
                try:
                    unauthorized=c.get(url); break
                except httpx.ConnectError: time.sleep(.1)
            assert unauthorized.status_code==401
            while time.monotonic()<deadline:
                result=c.get(url,headers={'Authorization':'Bearer '+token})
                if result.status_code==200:break
                assert result.status_code==204
                time.sleep(.1)
            assert result.status_code==200
            image=cv2.imdecode(np.frombuffer(result.content,np.uint8),cv2.IMREAD_COLOR)
            assert image is not None and image.shape[1]<=960 and image.shape[0]<=540 and len(result.content)<=2*1024*1024
            assert result.headers.get('x-frame-timestamp') and result.headers.get('cache-control')=='no-store'
            print('https_pipeline=ok unauthorized=401 jpeg_bytes=',len(result.content),'dimensions=',image.shape[1],image.shape[0])
    finally:
        for p in reversed(procs):
            if p.poll() is None:p.terminate()
        for p in reversed(procs):
            try:p.wait(timeout=5)
            except subprocess.TimeoutExpired:p.kill();p.wait()
