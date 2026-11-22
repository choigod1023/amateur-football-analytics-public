"""Stand-alone read-only server of the stream health screen (does not touch the production server on 8443).

python scripts/run_stream_health.py [--port 8791] [--host 127.0.0.1] [--directory <recordings/match>] [--file <one file>]
Open http://127.0.0.1:8791/stream . The page has no login and shows only numbers about the stream; keep the host on 127.0.0.1 unless the network is trusted.
"""
import argparse
from contextlib import asynccontextmanager
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import uvicorn  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.responses import RedirectResponse  # noqa: E402

from app import stream_health  # noqa: E402


def build_app(directory=None, ffprobe=None, file=None, interval_s=3.0, start=True):
    monitor = stream_health.StreamHealthMonitor(directory, ffprobe, file, interval_s=interval_s)

    @asynccontextmanager
    async def lifespan(_app):
        if start:
            monitor.start()
        yield
        monitor.stop()

    app = FastAPI(title='stream health', docs_url=None, redoc_url=None, lifespan=lifespan)
    stream_health.install(app, monitor)

    @app.get('/')
    def root():
        return RedirectResponse('/stream')

    app.state.monitor = monitor
    return app


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port', type=int, default=8791); p.add_argument('--host', default='127.0.0.1')
    p.add_argument('--directory', type=Path); p.add_argument('--file', type=Path); p.add_argument('--ffprobe', type=Path)
    p.add_argument('--interval', type=float, default=3.0)
    args = p.parse_args()
    if args.port == 8443:
        p.error('8443 is the production port')
    uvicorn.run(build_app(args.directory, args.ffprobe, args.file, args.interval), host=args.host, port=args.port, log_level='warning')


if __name__ == '__main__':
    main()
