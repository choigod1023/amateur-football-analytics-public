"""Start the local analyser only when the local SRT relay has a video stream."""
import argparse
import json
from pathlib import Path
import subprocess
import time
import urllib.error
import urllib.request

SOURCE = 'rtsp://127.0.0.1:18554/match'
API = 'http://127.0.0.1:18081/api/v1/'


def should_start(status, ready):
    return (ready and isinstance(status, dict) and status.get('status') in ('idle', 'error')
            and status.get('input_mode') == 'live')


def video_ready(ffprobe):
    try:
        result = subprocess.run([str(ffprobe), '-v', 'error', '-rtsp_transport', 'tcp',
                                 '-i', SOURCE, '-select_streams', 'v:0',
                                 '-show_entries', 'stream=codec_type', '-of', 'csv=p=0'],
                                capture_output=True, text=True, timeout=5,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        return result.returncode == 0 and 'video' in result.stdout.splitlines()
    except (OSError, subprocess.TimeoutExpired):
        return False


def tick(ffprobe, config):
    with urllib.request.urlopen(API + 'status', timeout=2) as response:
        status = json.load(response)
    if status.get('status') not in ('idle', 'error') or status.get('input_mode') != 'live':
        return False
    if not should_start(status, video_ready(ffprobe)):
        return False
    data = json.dumps({'source': SOURCE, 'config': str(config)}).encode('utf-8')
    request = urllib.request.Request(API + 'start', data=data,
                                     headers={'Content-Type': 'application/json'}, method='POST')
    with urllib.request.urlopen(request, timeout=4) as response:
        return response.status == 200


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ffprobe', type=Path, required=True)
    parser.add_argument('--config', type=Path, required=True)
    args = parser.parse_args()
    if not args.ffprobe.is_file() or not args.config.is_file():
        parser.error('Existing ffprobe and analysis config files are required')
    print('Waiting for video on the local SRT relay; Ctrl+C stops this watcher.', flush=True)
    while True:
        try:
            if tick(args.ffprobe.resolve(), args.config.resolve()):
                print('Started local analysis for the incoming video.', flush=True)
        except (OSError, ValueError, urllib.error.URLError):
            pass
        time.sleep(5)


if __name__ == '__main__':
    main()
