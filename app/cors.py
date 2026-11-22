"""Opt-in exact browser origins; CORS does not provide authentication."""
import os
from urllib.parse import urlsplit

from fastapi.middleware.cors import CORSMiddleware


def configure_cors(app):
    raw = os.environ.get('FOOTBALL_CORS_ORIGINS', '')
    if not raw.strip():
        return
    origins = []
    for part in raw.split(','):
        origin = part.strip()
        try:
            url = urlsplit(origin)
            port = url.port  # Forces validation of the port.
            if (not origin or any(c in origin for c in '*?#') or any(c.isspace() for c in origin)
                    or url.scheme not in ('http', 'https') or not url.hostname
                    or url.username is not None or url.password is not None
                    or url.path or url.query or url.fragment
                    or url.netloc.endswith(':') or port == 0):
                raise ValueError
        except ValueError as exc:
            raise ValueError('FOOTBALL_CORS_ORIGINS must contain exact http(s) origins') from exc
        if origin not in origins:
            origins.append(origin)
    app.add_middleware(CORSMiddleware, allow_origins=origins,
                       allow_credentials=False, allow_methods=['GET', 'POST'],
                       allow_headers=['Content-Type'])
