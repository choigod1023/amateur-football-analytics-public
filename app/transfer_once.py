"""One-shot archive receiver. This plaintext test service has no authentication.

Run only for an explicitly authorized transfer, behind firewall/router source
restrictions. The sender's IP restriction is not identity authentication and
does not encrypt data. The receiving directory and filename are set by the
operator, never by a remote request.
"""
import asyncio
import hashlib
import hmac
import ipaddress
import os
import re
import secrets
import threading
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from starlette.background import BackgroundTask

MAX_BYTES = 8 * 1024**3
SAFE_NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,119}\Z')
RESERVED = {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}


def validate_target(directory, filename):
    root = Path(directory).absolute()
    if not root.is_dir() or root.is_symlink() or root.resolve() != root:
        raise ValueError('Destination must be an existing directory without symlinks')
    if not SAFE_NAME.fullmatch(filename) or filename.endswith(('.', ' ')) or filename.split('.')[0].upper() in RESERVED:
        raise ValueError('Filename is invalid')
    return root / filename


def create_app(directory, filename, source, *, max_bytes=MAX_BYTES, on_complete=None):
    target = validate_target(directory, filename)
    source_ip = ipaddress.ip_address(source)
    if source_ip.version != 4 or source_ip.is_unspecified or source_ip.is_multicast:
        raise ValueError('One specific source IPv4 is required')
    if not isinstance(max_bytes, int) or not 0 < max_bytes <= MAX_BYTES:
        raise ValueError('Invalid size limit')
    lock = asyncio.Lock()
    complete = False
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware('http')
    async def gate(request, call_next):
        try:
            allowed = ipaddress.ip_address(request.client.host) == source_ip
        except (ValueError, AttributeError):
            allowed = False
        if not allowed:
            return Response(status_code=403, headers={'Cache-Control': 'no-store'})
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        return response

    @app.post('/upload')
    async def upload(request: Request):
        nonlocal complete
        if request.headers.get('content-type','').split(';')[0].strip().lower() != 'application/octet-stream':
            return Response(status_code=415)
        digest_header = request.headers.get('x-content-sha256', '')
        if not re.fullmatch(r'[a-fA-F0-9]{64}', digest_header):
            return Response(status_code=400)
        try:
            length = int(request.headers.get('content-length', ''))
        except ValueError:
            return Response(status_code=411)
        if length < 1 or length > max_bytes:
            return Response(status_code=413)
        async with lock:
            if complete:
                return Response(status_code=409)
            if target.exists() or target.is_symlink():
                return Response(status_code=409)
            temp = target.parent / ('.transfer-' + secrets.token_hex(16) + '.part')
            digest = hashlib.sha256()
            count = 0
            try:
                descriptor = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(descriptor, 'wb') as out:
                    async for chunk in request.stream():
                        count += len(chunk)
                        if count > length or count > max_bytes:
                            return Response(status_code=413)
                        digest.update(chunk)
                        out.write(chunk)
                if count != length or not hmac.compare_digest(digest.hexdigest(), digest_header.lower()):
                    return Response(status_code=422)
                try:
                    # Hard-link creation is atomic and fails if the destination exists.
                    os.link(temp, target)
                except FileExistsError:
                    return Response(status_code=409)
                complete = True
                return JSONResponse({'stored': True, 'bytes': count, 'sha256': digest.hexdigest()},
                                    background=BackgroundTask(on_complete) if on_complete else None)
            finally:
                temp.unlink(missing_ok=True)

    return app


def main():
    directory = os.environ.get('TRANSFER_DIR', '')
    filename = os.environ.get('TRANSFER_FILENAME', '')
    source = os.environ.get('TRANSFER_SOURCE_IP', '')
    bind = os.environ.get('TRANSFER_BIND_IP', '127.0.0.1')
    address = ipaddress.ip_address(bind)
    if address.version != 4 or address.is_unspecified or address.is_multicast or address.is_link_local:
        raise SystemExit('A specific IPv4 bind is required')
    app = create_app(directory, filename, source, on_complete=lambda: setattr(server, 'should_exit', True))
    server = uvicorn.Server(uvicorn.Config(app, host=bind, port=8443, access_log=False, proxy_headers=False))
    timer = threading.Timer(1800, lambda: setattr(server, 'should_exit', True))
    timer.daemon = True
    timer.start()
    try:
        server.run()
    finally:
        timer.cancel()


if __name__ == '__main__':
    main()
