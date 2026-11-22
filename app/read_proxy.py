"""TLS gateway with opt-in manual confirmation; start with `python -m app.read_proxy`."""
import hmac
import ipaddress
import os
from pathlib import Path

import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response


def parse_allowed_cidrs(value: str | None):
    if value is None:
        return ()
    items = [item.strip() for item in value.split(',')]
    if not items or any(not item for item in items):
        raise ValueError('Allowed CIDRs must be a comma-separated list')
    networks = tuple(ipaddress.ip_network(item, strict=False) for item in items)
    if any(network.prefixlen == 0 for network in networks):
        raise ValueError('An unrestricted /0 source network is not allowed')
    return networks


def validate_bind(host: str, networks):
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        raise ValueError('Bind host must be a literal IP address') from None
    if not address.is_loopback and not networks:
        raise ValueError('Non-loopback binding requires FOOTBALL_PROXY_ALLOWED_CIDRS')


def create_app(token: str, allowed_origin: str | None = None, allowed_cidrs=(), *, allow_manual=False, serve_dashboard=False) -> FastAPI:
    if len(token) < 32 or not token.isascii() or any(c.isspace() for c in token):
        raise ValueError('Bearer token must be at least 32 ASCII characters without whitespace')
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    allowed_paths = {'/api/v1/status', '/api/v1/analysis', '/api/v1/frame.jpg', '/api/v1/proxy-capabilities'}
    if allow_manual:
        allowed_paths |= {'/api/v1/manual-snapshot', '/api/v1/manual-track'}
    static_files = {'/': 'index.html', '/index.html': 'index.html', '/style.css': 'style.css',
                    '/app.js': 'app.js', '/freshness.js': 'freshness.js', '/teams.js': 'teams.js',
                    '/pitch.js': 'pitch.js', '/sequences.js': 'sequences.js',
                    '/manual-confirmation.js': 'manual-confirmation.js', '/api-auth.js': 'api-auth.js',
                    '/live-bookmarks.js': 'live-bookmarks.js', '/live-video.js': 'live-video.js'}
    web_root = (Path(__file__).resolve().parent.parent / 'web').resolve()

    @app.middleware('http')
    async def gate(request: Request, call_next):
        if allowed_cidrs:
            try:
                peer = ipaddress.ip_address(request.client.host)
            except (ValueError, AttributeError):
                return Response(status_code=403)
            if not any(peer in network for network in allowed_cidrs):
                return Response(status_code=403)
        # The optional dashboard contains only static code. All API data and
        # state changes remain behind the separate bearer-token gate below.
        if serve_dashboard and request.url.path in static_files:
            if request.method != 'GET':
                return Response(status_code=405)
            candidate = (web_root / static_files[request.url.path]).resolve()
            if candidate.parent != web_root or not candidate.is_file() or candidate.stat().st_size > 2_000_000:
                return Response(status_code=404)
            return FileResponse(candidate, headers={'Cache-Control': 'no-store',
                'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer',
                'Content-Security-Policy': "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"})
        origin = request.headers.get('origin')
        cors = {'Access-Control-Allow-Origin': allowed_origin, 'Vary': 'Origin', 'Access-Control-Expose-Headers': 'X-Frame-Timestamp, X-Frame-Age-Ms'} if allowed_origin and origin == allowed_origin else {}
        if request.url.path not in allowed_paths:
            return JSONResponse({'detail': 'Not found'}, status_code=404)
        if origin and origin != allowed_origin:
            return JSONResponse({'detail': 'Origin not allowed'}, status_code=403)
        expected = 'POST' if request.url.path == '/api/v1/manual-track' else 'GET'
        if request.method == 'OPTIONS':
            if not cors or request.headers.get('access-control-request-method') != expected:
                return Response(status_code=403)
            requested = {x.strip().lower() for x in request.headers.get('access-control-request-headers', '').split(',') if x.strip()}
            allowed_headers = {'authorization', 'content-type'} if expected == 'POST' else {'authorization'}
            if requested - allowed_headers:
                return Response(status_code=403)
            headers = 'Authorization, Content-Type' if expected == 'POST' else 'Authorization'
            return Response(status_code=204, headers={**cors, 'Access-Control-Allow-Methods': expected, 'Access-Control-Allow-Headers': headers, 'Access-Control-Max-Age': '600'})
        if request.method != expected:
            return JSONResponse({'detail': 'Method not allowed'}, status_code=405, headers=cors)
        credential = request.headers.get('authorization', '')
        if not hmac.compare_digest(credential.encode('utf-8'), ('Bearer ' + token).encode('ascii')):
            return JSONResponse({'detail': 'Unauthorized'}, status_code=401, headers={**cors, 'WWW-Authenticate': 'Bearer', 'Cache-Control': 'no-store'})
        response = await call_next(request)
        response.headers.update(cors)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response

    @app.get('/api/v1/proxy-capabilities')
    async def capabilities():
        return {'manual_enabled': allow_manual, 'controls_enabled': False}

    @app.get('/api/v1/{name}')
    async def read(name: str):
        # Fixed loopback destination: neither client headers nor URL determine upstream.
        try:
            async with httpx.AsyncClient(timeout=3, trust_env=False, follow_redirects=False) as client:
                upstream = await client.get('http://127.0.0.1:8000/api/v1/' + name)
            if name == 'frame.jpg':
                if upstream.status_code == 204:
                    return Response(status_code=204)
                if upstream.status_code != 200 or upstream.headers.get('content-type', '').split(';')[0] != 'image/jpeg' or len(upstream.content) > 2_000_000:
                    raise ValueError('Invalid upstream frame')
                headers = {k: upstream.headers[k] for k in ('x-frame-timestamp', 'x-frame-age-ms') if k in upstream.headers}
                return Response(content=upstream.content, media_type='image/jpeg', headers=headers)
            if name == 'manual-snapshot' and upstream.status_code == 409 and len(upstream.content) <= 4096:
                return JSONResponse(upstream.json(), status_code=409)
            if upstream.status_code != 200 or len(upstream.content) > 3_000_000:
                raise ValueError('upstream unavailable')
            return JSONResponse(upstream.json())
        except (httpx.HTTPError, ValueError):
            return JSONResponse({'detail': 'Upstream unavailable'}, status_code=502)

    @app.post('/api/v1/manual-track')
    async def manual_track(request: Request):
        if request.headers.get('content-type', '').split(';')[0].strip().lower() != 'application/json':
            return JSONResponse({'detail': 'JSON required'}, status_code=415)
        # Refuse oversized inputs even for a valid token, without trusting the
        # optional Content-Length header or forwarding browser credentials.
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 4096:
                return JSONResponse({'detail': 'Request too large'}, status_code=413)
        try:
            async with httpx.AsyncClient(timeout=3, trust_env=False, follow_redirects=False) as client:
                upstream = await client.post('http://127.0.0.1:8000/api/v1/manual-track',
                                             content=bytes(body), headers={'Content-Type': 'application/json'})
            if len(upstream.content) > 4096 or upstream.status_code not in (200, 400, 409, 422):
                raise ValueError('Invalid upstream response')
            return JSONResponse(upstream.json(), status_code=upstream.status_code)
        except (httpx.HTTPError, ValueError):
            return JSONResponse({'detail': 'Upstream unavailable'}, status_code=502)

    return app


def main():
    token_file = os.environ.get('FOOTBALL_PROXY_TOKEN_FILE')
    cert = os.environ.get('FOOTBALL_PROXY_TLS_CERT')
    key = os.environ.get('FOOTBALL_PROXY_TLS_KEY')
    if not all((token_file, cert, key)):
        raise SystemExit('Set FOOTBALL_PROXY_TOKEN_FILE, FOOTBALL_PROXY_TLS_CERT and FOOTBALL_PROXY_TLS_KEY')
    token = Path(token_file).read_text(encoding='utf-8').strip()
    host = os.environ.get('FOOTBALL_PROXY_HOST', '127.0.0.1')
    try:
        allowed_cidrs = parse_allowed_cidrs(os.environ.get('FOOTBALL_PROXY_ALLOWED_CIDRS'))
        validate_bind(host, allowed_cidrs)
    except ValueError as error:
        raise SystemExit(str(error)) from None
    manual = os.environ.get('FOOTBALL_PROXY_ALLOW_MANUAL', '')
    if manual not in ('', '0', '1'):
        raise SystemExit('FOOTBALL_PROXY_ALLOW_MANUAL must be 0 or 1')
    dashboard = os.environ.get('FOOTBALL_PROXY_SERVE_DASHBOARD', '')
    if dashboard not in ('', '0', '1'):
        raise SystemExit('FOOTBALL_PROXY_SERVE_DASHBOARD must be 0 or 1')
    app = create_app(token, os.environ.get('FOOTBALL_PROXY_ALLOWED_ORIGIN') or None, allowed_cidrs,
                     allow_manual=manual == '1', serve_dashboard=dashboard == '1')
    # Trust only the socket peer; X-Forwarded-For must not bypass source filtering.
    uvicorn.run(app, host=host, port=int(os.environ.get('FOOTBALL_PROXY_PORT', '8443')), ssl_certfile=cert, ssl_keyfile=key, access_log=False, proxy_headers=False)


if __name__ == '__main__':
    main()
