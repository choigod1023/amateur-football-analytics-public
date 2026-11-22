"""Synthetic check of the stream health screen: loopback SRT sends (as in srt_degradation_test.py) while the screen's own monitor reads the file that is being written.

python scripts/stream_health_synthetic.py <video> --ffmpeg <ffmpeg.exe> --ffprobe <ffprobe.exe> --start 2400 --seconds 30 --output <result.json> [--profiles ...]
For each profile the transport runs in a thread; the monitor measures the growing receive file every few seconds, and the last verdict before the send ends is kept
(plus the HTTP answer of the stand-alone screen for the first profile, to check the web path).
"""
import argparse
import json
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import srt_degradation_test as base  # noqa: E402
from app import stream_health  # noqa: E402

EXTRA = {
    'p1080_500': dict(height=1080, kbps=500, latency=200, loss=0.0, delay=0, jitter=0),
    'p1080_loss5': dict(height=1080, kbps=4000, latency=200, loss=0.05, delay=20, jitter=0),
    'p720_2000': dict(height=720, kbps=2000, latency=200, loss=0.0, delay=0, jitter=0),
    'p720_1000': dict(height=720, kbps=1000, latency=200, loss=0.0, delay=0, jitter=0),
}
DEFAULT = ['p1080_8000', 'p1080_4000', 'p1080_2000', 'p1080_500', 'p720_2000', 'p720_1000', 'p1080_loss5', 'p1080_loss10']


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('video', type=Path); p.add_argument('--ffmpeg', type=Path, required=True); p.add_argument('--ffprobe', type=Path, required=True)
    p.add_argument('--start', type=float, default=2400.0); p.add_argument('--seconds', type=float, default=30.0)
    p.add_argument('--profiles', nargs='+', default=DEFAULT); p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    profiles = {**base.PROFILES, **EXTRA}
    results = {}
    for name in args.profiles:
        profile = profiles[name]
        work = Path(tempfile.mkdtemp(prefix='shealth_'))
        out_ts = work / 'recv.ts'
        box = {}
        thread = threading.Thread(target=lambda: box.update(base.run_transport(args.ffmpeg, args.video, args.start, args.seconds, profile, out_ts, seed=7)), daemon=True)
        thread.start()
        monitor = stream_health.StreamHealthMonitor(work, args.ffprobe, window_s=10.0, decode_every_s=10.0)
        verdicts = []
        time.sleep(14)
        while thread.is_alive():
            verdicts.append(monitor.once())
            time.sleep(2)
        thread.join()
        measured = [v for v in verdicts if v.get('numbers')]
        last = measured[-1] if measured else None
        results[name] = {'profile': profile, 'samples': len(measured), 'levels_over_time': [v['level'] for v in measured], 'last': last,
                         'transport': {k: box.get(k) for k in ('proxy_data_packets', 'proxy_dropped', 'arrival_delay')}}
        print(name, last and (last['level'], last['size'], last['numbers']['bitrate_kbps'], last['numbers']['fps'], last['numbers']['key_interval_s'], last['numbers']['gap_count']), flush=True)
    args.output.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding='utf-8')


if __name__ == '__main__':
    main()
