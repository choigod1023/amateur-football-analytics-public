"""Temporary public-demo-only gateway. No encryption or identity authentication.

Never expose user footage. Source IP filtering is not authentication, can fail
behind proxies/NAT, and does not prevent interception. No router/firewall changes.
"""
import ipaddress
import os
import re
from pathlib import Path
import subprocess
import tempfile
import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, Response, StreamingResponse
from app.srt_path_ingest import config_for
from app.cors import configure_cors

ROOT = Path(__file__).resolve().parent.parent
PATHS = {'/api/v1/status', '/api/v1/analysis', '/api/v1/frame.jpg', '/api/v1/sequences'}
POST_PATHS = {'/api/v1/upload', '/api/v1/live'}
SEQUENCE_VIDEO = re.compile(r'^/api/v1/sequences/([0-9a-f]{32})/video$')
SEQUENCE_IMAGE = re.compile(r'^/api/v1/sequences/([0-9a-f]{32})/snapshot\.jpg$')
MAX_UPLOAD_BYTES = 256 * 1024 * 1024


def one_ipv4(value):
    result = ipaddress.ip_address(value)
    if result.version != 4 or result.is_unspecified or result.is_multicast:
        raise ValueError('Expected a single IPv4 address')
    return result


def demo_srt_config(bind, source, allow_cellular=False):
    config = config_for(bind, str(one_ipv4(source)), 8890, 18554)
    token = '    srtPublishPassphrase: invalid_config_not_for_direct_use\n'
    if config.count(token) != 1: raise ValueError('Unexpected template')
    if allow_cellular:
        restricted = f'    ips: [{one_ipv4(source)}/32]'
        if config.count(restricted) < 1: raise ValueError('Unexpected publisher restriction')
        config = config.replace(restricted, '    ips: []', 1)
    return config.replace(token, '')


def create_app(source, upstream_transport=None, allow_any_viewer=False, static_dir=None):
    allowed = one_ipv4(source)
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    configure_cors(app)
    static_root = Path(static_dir).resolve() if static_dir else None
    static_types = {'.html', '.js', '.mjs', '.css', '.json', '.png', '.jpg', '.jpeg', '.webp', '.gif', '.svg', '.ico', '.woff', '.woff2', '.ttf', '.wasm'}

    def static_candidate(path):
        if static_root is None or path == '/api' or path.startswith('/api/') or path in ('/docs', '/redoc', '/openapi.json'):
            return None
        parts = ('index.html' if path == '/' else path.lstrip('/')).split('/')
        if any(not part or part.startswith('.') or '\\' in part or ':' in part for part in parts):
            return None
        candidate = static_root.joinpath(*parts).resolve()
        try:
            candidate.relative_to(static_root)
        except ValueError:
            return None
        return candidate if candidate.suffix.lower() in static_types and candidate.is_file() else None

    @app.middleware('http')
    async def gate(request: Request, call_next):
        try: peer = ipaddress.ip_address(request.client.host)
        except (ValueError, AttributeError): return Response(status_code=403)
        if not allow_any_viewer and peer != allowed: return Response(status_code=403)
        path = request.url.path
        if path == '/api/v1/sequences': methods = ('GET', 'POST')
        elif SEQUENCE_VIDEO.fullmatch(path) or SEQUENCE_IMAGE.fullmatch(path): methods = ('GET',)
        elif path in POST_PATHS: methods = ('POST',)
        elif path in PATHS or static_candidate(path) is not None: methods = ('GET',)
        else: return Response(status_code=404)
        if request.method not in methods and request.method != 'OPTIONS': return Response(status_code=405)
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response

    @app.get('/api/v1/{name}')
    async def read(name: str):
        try:
            async with httpx.AsyncClient(timeout=3, trust_env=False, follow_redirects=False, transport=upstream_transport) as client:
                response = await client.get('http://127.0.0.1:8000/api/v1/' + name)
            if response.status_code == 204 and name == 'frame.jpg': return Response(status_code=204)
            expected = 'image/jpeg' if name == 'frame.jpg' else 'application/json'
            if response.status_code != 200 or response.headers.get('content-type','').split(';')[0] != expected or len(response.content) > 2_000_000:
                return Response(status_code=502)
            headers = {k:response.headers[k] for k in ('x-frame-timestamp','x-frame-age-ms') if k in response.headers}
            return Response(response.content, media_type=expected, headers=headers)
        except httpx.HTTPError:
            return Response(status_code=502)

    @app.post('/api/v1/upload')
    async def upload(request: Request):
        content_type = request.headers.get('content-type', '').split(';')[0].lower()
        if content_type != 'video/mp4': return Response(status_code=415)
        declared = request.headers.get('content-length')
        if declared:
            try:
                if int(declared) < 1 or int(declared) > MAX_UPLOAD_BYTES: return Response(status_code=413)
            except ValueError: return Response(status_code=400)
        headers = {'Content-Type': 'video/mp4'}
        if declared: headers['Content-Length'] = declared
        async def body():
            total=0
            async for chunk in request.stream():
                total+=len(chunk)
                if total > MAX_UPLOAD_BYTES: raise ValueError('Upload too large')
                yield chunk
        try:
            async with httpx.AsyncClient(timeout=300, trust_env=False, follow_redirects=False, transport=upstream_transport) as client:
                result = await client.post('http://127.0.0.1:8000/api/v1/upload',headers=headers,content=body())
            if result.status_code >= 500: return Response(status_code=502)
            return Response(result.content,status_code=result.status_code,media_type='application/json')
        except ValueError:
            return Response(status_code=413)
        except httpx.HTTPError:
            return Response(status_code=502)

    @app.post('/api/v1/sequences')
    async def create_sequence(request: Request):
        if request.headers.get('content-type', '').split(';')[0].lower() != 'application/json':
            return Response(status_code=415)
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 1024: return Response(status_code=413)
        try:
            async with httpx.AsyncClient(timeout=130, trust_env=False, follow_redirects=False, transport=upstream_transport) as client:
                result = await client.post('http://127.0.0.1:8000/api/v1/sequences', content=bytes(body), headers={'Content-Type': 'application/json'})
            if len(result.content) > 10000: return Response(status_code=502)
            return Response(result.content, status_code=result.status_code, media_type='application/json')
        except httpx.HTTPError:
            return Response(status_code=502)

    @app.get('/api/v1/sequences/{identifier}/video')
    async def sequence_video(identifier: str, request: Request):
        if not re.fullmatch(r'[0-9a-f]{32}', identifier): return Response(status_code=404)
        client = httpx.AsyncClient(timeout=30, trust_env=False, follow_redirects=False, transport=upstream_transport)
        headers = {'Range': request.headers['range']} if 'range' in request.headers else {}
        try:
            upstream = await client.send(client.build_request('GET', 'http://127.0.0.1:8000/api/v1/sequences/' + identifier + '/video', headers=headers), stream=True)
            forwarded = {key: upstream.headers[key] for key in ('content-range', 'accept-ranges', 'content-length') if key in upstream.headers}
            if upstream.status_code == 416:
                await upstream.aclose(); await client.aclose()
                return Response(status_code=416, headers={k:v for k,v in forwarded.items() if k != 'content-length'})
            length = upstream.headers.get('content-length')
            if (upstream.status_code not in (200, 206) or upstream.headers.get('content-type', '').split(';')[0] != 'video/mp4'
                    or length is None or not length.isdigit() or int(length) > 50 * 1024 * 1024):
                code = 404 if upstream.status_code == 404 else 502
                await upstream.aclose(); await client.aclose()
                return Response(status_code=code)
            async def chunks():
                try:
                    async for chunk in upstream.aiter_bytes(): yield chunk
                finally:
                    await upstream.aclose(); await client.aclose()
            return StreamingResponse(chunks(), status_code=upstream.status_code, media_type='video/mp4', headers=forwarded)
        except httpx.HTTPError:
            await client.aclose()
            return Response(status_code=502)

    @app.get('/api/v1/sequences/{identifier}/snapshot.jpg')
    async def sequence_snapshot(identifier: str):
        if not re.fullmatch(r'[0-9a-f]{32}', identifier): return Response(status_code=404)
        try:
            async with httpx.AsyncClient(timeout=10, trust_env=False, follow_redirects=False, transport=upstream_transport) as client:
                result = await client.get('http://127.0.0.1:8000/api/v1/sequences/' + identifier + '/snapshot.jpg')
            if result.status_code == 404: return Response(status_code=404)
            if result.status_code != 200 or result.headers.get('content-type', '').split(';')[0] != 'image/jpeg' or len(result.content) > 2_000_000:
                return Response(status_code=502)
            return Response(result.content, media_type='image/jpeg')
        except httpx.HTTPError:
            return Response(status_code=502)

    @app.post('/api/v1/live')
    async def live():
        try:
            async with httpx.AsyncClient(timeout=20, trust_env=False, follow_redirects=False, transport=upstream_transport) as client:
                result = await client.post('http://127.0.0.1:8000/api/v1/live')
            if result.status_code >= 500: return Response(status_code=502)
            return Response(result.content,status_code=result.status_code,media_type='application/json')
        except httpx.HTTPError:
            return Response(status_code=502)

    @app.get('/{path:path}')
    async def static(path: str, request: Request):
        candidate = static_candidate(request.url.path)
        return FileResponse(candidate) if candidate is not None else Response(status_code=404)

    return app


def main():
    import sys
    if len(sys.argv) != 2 or sys.argv[1] not in ('gateway','srt'):
        raise SystemExit('Usage: python -m app.plaintext_demo gateway|srt; set DEMO_BIND_IP and DEMO_SOURCE_IP in process environment')
    mode = sys.argv[1]
    bind, source = os.environ.get('DEMO_BIND_IP',''), os.environ.get('DEMO_SOURCE_IP','')
    one_ipv4(bind); one_ipv4(source)
    if mode == 'gateway':
        uvicorn.run(create_app(source, allow_any_viewer=os.environ.get('DEMO_HTTP_ALLOW_ANY') == '1', static_dir=os.environ.get('DEMO_STATIC_DIR') or ROOT / 'web'), host=bind, port=8443, access_log=False, proxy_headers=False)
    else:
        config = demo_srt_config(bind, source, allow_cellular=os.environ.get('DEMO_SRT_ALLOW_ANY') == '1')
        env={k:v for k,v in os.environ.items() if not k.upper().startswith('MTX_')}
        with tempfile.TemporaryDirectory(prefix='football-demo-') as temp:
            path=Path(temp)/'mediamtx.yml'; path.write_text(config,encoding='utf-8')
            subprocess.run([str(ROOT/'mediamtx'/'mediamtx.exe'), str(path)],env=env,check=True)


if __name__ == '__main__': main()
