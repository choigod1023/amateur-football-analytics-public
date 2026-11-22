"""Send a local concat playlist to a loopback MediaMTX SRT listener.

Re-encode with short closed GOPs and no B-frames to make decoder recovery
after joins or loss possible. This does not change incoming iPhone streams.
"""
import argparse
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.demo_job import ChildJob


def sender_command(ffmpeg: str, playlist: Path, output: str) -> list[str]:
    target = urlsplit(output)
    if (target.scheme != 'srt' or target.hostname not in {'127.0.0.1', 'localhost', '::1'}
            or target.username or target.password or not target.port):
        raise ValueError('Only an explicit loopback SRT target is permitted')
    if parse_qs(target.query).get('mode', ['caller'])[0] != 'caller':
        raise ValueError('Sender must use caller mode')
    if not playlist.is_file():
        raise ValueError('Playlist does not exist')
    return [ffmpeg, '-hide_banner', '-loglevel', 'error', '-nostdin',
            '-re', '-stream_loop', '-1', '-f', 'concat', '-safe', '0',
            '-i', str(playlist), '-an', '-c:v', 'libx264', '-preset', 'ultrafast',
            '-tune', 'zerolatency', '-g', '25', '-bf', '0', '-pix_fmt', 'yuv420p',
            '-f', 'mpegts', output]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ffmpeg', required=True)
    parser.add_argument('--playlist', type=Path, required=True)
    parser.add_argument('--output', required=True, help='Loopback SRT URL including path streamid')
    args = parser.parse_args()
    try:
        command = sender_command(args.ffmpeg, args.playlist, args.output)
    except ValueError as exc:
        parser.error(str(exc))
    job = ChildJob()
    process = None
    try:
        process = subprocess.Popen(command)
        job.add(process)
        return process.wait()
    finally:
        job.close()
        if process is not None and process.poll() is None:
            process.terminate()
            process.wait()


if __name__ == '__main__':
    raise SystemExit(main())
