"""Local-only review of a looping MP4. Does not start an external listener."""
import argparse
import os
from pathlib import Path
import sys
import threading
import time

import uvicorn
from fastapi.staticfiles import StaticFiles
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['FOOTBALL_LABEL_REVIEW'] = '1'
from app import main


def main_entry():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--config', required=True, type=Path)
    parser.add_argument('--port', default=18961, type=int)
    args = parser.parse_args()
    if not args.source.is_file() or not args.config.is_file() or not 1024 <= args.port <= 65535:
        parser.error('An existing local video, configuration and unprivileged port are required')
    source, config = str(args.source.resolve()), str(args.config.resolve())
    def run_loop():
        while True:
            if main.worker is None or not main.worker.is_alive():
                if main.status['status'] == 'error':
                    return
                try:
                    main.start(main.Start(source=source, config=config))
                except Exception:
                    return
            time.sleep(2)
    main.app.mount('/', StaticFiles(directory=Path(__file__).resolve().parents[1] / 'web', html=True), name='dashboard')
    threading.Thread(target=run_loop, daemon=True).start()
    uvicorn.run(main.app, host='127.0.0.1', port=args.port, access_log=False)


if __name__ == '__main__':
    main_entry()
