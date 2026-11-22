"""Actual loopback TLS test with ephemeral certificate, token and upstream."""
import datetime
import ipaddress
import os
from pathlib import Path
import secrets
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from fastapi.testclient import TestClient
from app.read_proxy import create_app, parse_allowed_cidrs, validate_bind


def test_bind_restrictions():
    validate_bind('127.0.0.1', ())
    with pytest.raises(ValueError):
        validate_bind('0.0.0.0', ())
    with pytest.raises(ValueError):
        parse_allowed_cidrs('0.0.0.0/0')
    with pytest.raises(ValueError):
        parse_allowed_cidrs('127.0.0.1,')
    validate_bind('0.0.0.0', parse_allowed_cidrs('127.0.0.1/32'))
    app = create_app('a' * 32, allowed_cidrs=parse_allowed_cidrs('192.0.2.1/32'))
    with TestClient(app, client=('198.51.100.10', 1234)) as client:
        response = client.get('/api/v1/status', headers={'Authorization': 'Bearer ' + 'a' * 32, 'X-Forwarded-For': '192.0.2.1'})
        assert response.status_code == 403


def test_tls_proxy():
    received = []
    class Backend(BaseHTTPRequestHandler):
        def do_GET(self):
            received.append((self.path, self.headers.get('Authorization')))
            if self.path == '/api/v1/frame.jpg':
                self.send_response(200)
                self.send_header('Content-Type','image/jpeg')
                self.send_header('X-Frame-Timestamp','2026-11-10T00:00:00+00:00')
                self.send_header('X-Frame-Age-Ms','5')
                self.end_headers()
                self.wfile.write(b'\xff\xd8\xff\xd9')
                return
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"ok":true}')

        def log_message(self, *args):
            pass

    backend = ThreadingHTTPServer(('127.0.0.1', 8000), Backend)
    thread = threading.Thread(target=backend.serve_forever, daemon=True)
    thread.start()
    process = None
    try:
        with tempfile.TemporaryDirectory(dir='.') as temporary:
            root = Path(temporary).resolve()
            token = secrets.token_urlsafe(48)
            (root / 'token').write_text(token, encoding='utf-8')
            private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, '127.0.0.1')])
            now = datetime.datetime.now(datetime.timezone.utc)
            cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(private_key.public_key())
                    .serial_number(x509.random_serial_number()).not_valid_before(now - datetime.timedelta(minutes=1))
                    .not_valid_after(now + datetime.timedelta(hours=1))
                    .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address('127.0.0.1'))]), False)
                    .sign(private_key, hashes.SHA256()))
            (root / 'key.pem').write_bytes(private_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
            (root / 'cert.pem').write_bytes(cert.public_bytes(serialization.Encoding.PEM))
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 0))
                port = sock.getsockname()[1]
            env = os.environ.copy()
            env.update(FOOTBALL_PROXY_TOKEN_FILE=str(root / 'token'), FOOTBALL_PROXY_TLS_CERT=str(root / 'cert.pem'),
                       FOOTBALL_PROXY_TLS_KEY=str(root / 'key.pem'), FOOTBALL_PROXY_PORT=str(port),
                       FOOTBALL_PROXY_ALLOWED_ORIGIN='https://dashboard.example',
                       FOOTBALL_PROXY_ALLOWED_CIDRS='127.0.0.1/32')
            process = subprocess.Popen([sys.executable, '-m', 'app.read_proxy'], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            url = f'https://127.0.0.1:{port}'
            with httpx.Client(verify=ssl.create_default_context(cafile=str(root / 'cert.pem')), trust_env=False) as client:
                for _ in range(100):
                    try:
                        response = client.get(url + '/api/v1/status')
                        break
                    except httpx.ConnectError:
                        time.sleep(.1)
                else:
                    raise AssertionError('TLS proxy did not start')
                assert response.status_code == 401
                assert client.get(url + '/api/v1/status', headers={'Authorization':'Bearer wrong'}).status_code == 401
                auth = {'Authorization': 'Bearer ' + token}
                assert client.get(url + '/api/v1/status', headers=auth).json() == {'ok': True}
                assert client.get(url + '/api/v1/status', headers={**auth, 'X-Forwarded-For':'203.0.113.1'}).status_code == 200
                assert client.get(url + '/api/v1/analysis', headers=auth).status_code == 200
                assert client.get(url + '/api/v1/frame.jpg').status_code == 401
                image=client.get(url + '/api/v1/frame.jpg', headers={**auth,'Origin':'https://dashboard.example'})
                assert image.status_code==200 and image.headers['content-type']=='image/jpeg' and image.content==b'\xff\xd8\xff\xd9'
                assert image.headers['x-frame-timestamp']=='2026-11-10T00:00:00+00:00' and 'x-frame-timestamp' in image.headers['access-control-expose-headers'].lower()
                assert received == [('/api/v1/status', None), ('/api/v1/status', None), ('/api/v1/analysis', None), ('/api/v1/frame.jpg',None)]
                for method, path in [('POST','/api/v1/start'), ('POST','/api/v1/stop'), ('GET','/docs'), ('PUT','/api/v1/status')]:
                    assert client.request(method, url + path, headers=auth).status_code in (404,405)
                assert client.get(url + '/api/v1/status', headers={**auth,'Origin':'https://attacker.example'}).status_code == 403
                preflight = client.options(url + '/api/v1/analysis', headers={'Origin':'https://dashboard.example', 'Access-Control-Request-Method':'GET', 'Access-Control-Request-Headers':'authorization'})
                assert preflight.status_code == 204 and preflight.headers['access-control-allow-origin'] == 'https://dashboard.example'
    finally:
        if process is not None:
            process.terminate()
            process.wait(timeout=10)
        backend.shutdown()
        backend.server_close()
