"""End-to-end latency of the live coaching chain: from a picture leaving the sender to the alert showing on the coach's bench screen API.

What is measured (all on this computer, loopback SRT, nothing leaves it):
  * the sender (this script) reads a 30 fps constant-rate segment of the match, burns a clock marker into every frame (a row of black and white blocks that codes the frame
    number, plus the number as text) and hands the frame to an ffmpeg encoder at real time; the wall time of the hand-over is the "event time" of that picture;
  * ffmpeg encodes (x264, zerolatency) and sends over SRT through the UDP proxy of scripts/srt_degradation_test.py (packet loss, delay, jitter);
  * the SRT stream goes into a private MediaMTX relay (the same program the server uses, own ports, no auth, started here) and is read from it over RTSP/TCP, the way the
    live analysis reads a stream (OpenCV's FFmpeg has no SRT support);
  * the receiving side is the real scripts/run_live_feedback.py (a stream source, so the newest-frame queue is on) run in a worker process. The worker is NOT edited: this file wraps
    four calls of it from outside to take wall times and to read the marker of the frame that goes through (the reader, the tile detector, LiveAnalyzer.update);
  * every PROBE_EVERY seconds of video one probe alert is added by the wrapper at the first analysed frame at or after the probe frame, so that there are many events to time (natural
    alerts need 3 to 11 s of a condition and come rarely). The probe goes through the real write path (alerts.jsonl in a store folder) like any alert. Natural alerts are timed
    the same way from the frame that raised them;
  * this script polls the alerts file (every 10 ms) and a temporary copy of the review server (a real HTTP server of app.review_public on a free port, never port 8443) at /api/v1/bench
    (every 100 ms) and writes down when a row first shows up. The page web/bench.js asks the same URL once a second, which is added as its own line.
Stages per analysed frame: send -> read (encode, SRT, proxy, MediaMTX relay, RTSP, decode), read -> detector start (waiting for the analysis to take the newest frame), detector, tracking and team labels
and projection, LiveAnalyzer; per alert: analyser end -> row in the file, file -> API, API -> page (at most 1 s). The rule time of an alert (3 to 11 s of a condition) is not in these numbers.
Not measured: the phone camera and its encoder, the real network, the tablet, the browser's drawing time.
"""
import argparse
import json
import os
import statistics
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

FPS = 30
BITS = 16
BLOCK = 24                  # pixels of one marker block
PROBE_FIRST, PROBE_EVERY = 15.0, 8.0
# name: video kbit/s, SRT latency ms, loss share, one-way delay ms, jitter ms, extra OpenCV capture options of the worker
PROFILES = {
    'lat120': dict(kbps=4000, latency=120, loss=0.0, delay=0, jitter=0, cv=''),
    'lat200': dict(kbps=4000, latency=200, loss=0.0, delay=0, jitter=0, cv=''),
    'lat500': dict(kbps=4000, latency=500, loss=0.0, delay=0, jitter=0, cv=''),
    'lat1500_loss5': dict(kbps=4000, latency=1500, loss=0.05, delay=20, jitter=0, cv=''),
    'loss10_lat200': dict(kbps=4000, latency=200, loss=0.10, delay=20, jitter=0, cv=''),
    'cell_like': dict(kbps=2000, latency=500, loss=0.02, delay=60, jitter=40, cv=''),
    'lat200_lowdelay': dict(kbps=4000, latency=200, loss=0.0, delay=0, jitter=0, cv='fflags;nobuffer|flags;low_delay'),
}


# ---------------------------------------------------------------- the marker
def draw_marker(frame, number):
    """Burn the frame number into the top-left corner: sync (white, black), 16 data bits, 1 parity bit, as blocks of BLOCK pixels, plus the number as text for the eye."""
    import cv2
    bits = [1, 0] + [(number >> (BITS - 1 - i)) & 1 for i in range(BITS)]
    bits.append(sum(bits[2:]) % 2)
    for i, bit in enumerate(bits):
        frame[0:BLOCK, i * BLOCK:(i + 1) * BLOCK] = 255 if bit else 0
    cv2.putText(frame, f'{number / FPS:8.2f}s #{number}', (4, BLOCK + 28), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2, cv2.LINE_AA)
    return frame


def read_marker(frame):
    """The frame number coded in the corner, or None when the sync or the parity does not fit (a damaged frame)."""
    h, w = frame.shape[:2]
    scale = w / 1920.0
    size = BLOCK * scale
    values = []
    for i in range(BITS + 3):
        x0, x1 = int((i + 0.25) * size), max(int((i + 0.75) * size), int((i + 0.25) * size) + 1)
        y0, y1 = int(0.25 * size), max(int(0.75 * size), int(0.25 * size) + 1)
        values.append(1 if float(frame[y0:y1, x0:x1].mean()) > 127 else 0)
    if values[0] != 1 or values[1] != 0 or sum(values[2:2 + BITS]) % 2 != values[2 + BITS]:
        return None
    number = 0
    for bit in values[2:2 + BITS]:
        number = number * 2 + bit
    return number


# ---------------------------------------------------------------- worker: the real live run with four wrapped calls
def worker(args):
    import threading as th
    ready_file, log_file = Path(args.ready_file), Path(args.log_file)
    import cv2
    import numpy as np  # noqa: F401
    real_capture = cv2.VideoCapture

    def capture(*a, **k):
        ready_file.write_text(str(time.time()))                                      # the model is loaded; the sender starts now and the stream shows up on the relay a moment later
        c = real_capture(*a, **k)
        for _ in range(200):
            if c.isOpened():
                break
            time.sleep(0.3)
            c = real_capture(*a, **k)
        return c
    cv2.VideoCapture = capture

    import run_live_feedback as rlf
    from app import live_input, live_feedback
    local = th.local()
    log = {'read': {}, 'det0': {}, 'det1': {}, 'upd0': {}, 'upd1': {}, 'undecoded': 0, 'reads': 0}

    real_read = live_input.ReconnectingReader.read

    def read(self):
        ok, frame = real_read(self)
        now = time.time()
        if ok:
            log['reads'] += 1
            m = read_marker(frame)
            if m is None:
                log['undecoded'] += 1
            else:
                log['read'].setdefault(m, now)
        return ok, frame
    live_input.ReconnectingReader.read = read

    real_detect = rlf.tile_detector.detect

    def detect(*a, **k):
        m = read_marker(a[1])
        local.m = m
        t0 = time.time()
        out = real_detect(*a, **k)
        if m is not None:
            log['det0'][m], log['det1'][m] = t0, time.time()
        return out
    rlf.tile_detector.detect = detect

    real_update = live_feedback.LiveAnalyzer.update
    probes = {'next': int(PROBE_FIRST * FPS)}

    def update(self, t, team, other):
        m = getattr(local, 'm', None)
        u0 = time.time()
        new = list(real_update(self, t, team, other))
        u1 = time.time()
        if m is not None:
            log['upd0'][m], log['upd1'][m] = u0, u1
            for alert in new:
                alert['e2e_marker'], alert['e2e_probe'] = m, False
            if m >= probes['next']:
                step = int(PROBE_EVERY * FPS)
                probes['next'] += step * (1 + (m - probes['next']) // step)
                new.append({'time': round(t, 1), 'kind': 'e2e_probe', 'polarity': 'info', 'title': '지연 시험 신호', 'text': f'프레임 {m}', 'rules': [], 'drill': None,
                            'detail': None, 'e2e_marker': m, 'e2e_probe': True})
        return new
    live_feedback.LiveAnalyzer.update = update

    def dump():
        out = {k: ({str(m): v for m, v in val.items()} if isinstance(val, dict) else val) for k, val in log.items()}
        log_file.write_text(json.dumps(out), encoding='utf-8')
    def dump_often():                                                                # the orchestrator stops this process after the sender has finished, so the log is written all the time
        while True:
            time.sleep(2.0)
            try:
                dump()
            except Exception:
                pass
    th.Thread(target=dump_often, daemon=True).start()
    sys.argv = ['run_live_feedback.py'] + args.live_args
    try:
        rlf.main()
    finally:
        dump()


# ---------------------------------------------------------------- orchestrator
def percentile(values, q):
    values = sorted(values)
    if not values:
        return None
    pos = (len(values) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(values) - 1)
    return values[lo] + (values[hi] - values[lo]) * (pos - lo)


def summarise(values):
    values = [v for v in values if v is not None]
    if not values:
        return {'n': 0}
    return {'n': len(values), 'p50': round(percentile(values, 0.5), 3), 'p95': round(percentile(values, 0.95), 3), 'max': round(max(values), 3), 'mean': round(statistics.mean(values), 3)}


def free_port():
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()
    return port


def free_tcp_port():
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()
    return port


def start_bench_server(directory, port):
    import uvicorn
    from app.review_public import create_app
    app = create_app(str(directory), f'http://127.0.0.1:{port}')
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=port, log_level='warning', access_log=False))
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(100):
        try:
            urllib.request.urlopen(f'http://127.0.0.1:{port}/api/v1/bench', timeout=1).read()
            return server
        except Exception:
            time.sleep(0.1)
    raise SystemExit('The temporary bench server did not start.')


def run_condition(name, profile, args, out_dir):
    import cv2
    import srt_degradation_test as transport
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    store = out_dir / 'store'
    session = 'e2e_' + name.replace('-', '_')
    alerts_file = store / 'alerts' / session / 'alerts.jsonl'
    for old in (alerts_file, out_dir / 'worker_log.json', out_dir / 'ready.txt'):
        if old.exists():
            old.unlink()
    (store / 'alerts').mkdir(parents=True, exist_ok=True)
    seconds = args.seconds
    listen_port, target_port, http_port, rtsp_port = free_port(), free_port(), free_port(), free_tcp_port()
    latency_us = int(profile['latency'] * 1000)
    source_url = f'rtsp://127.0.0.1:{rtsp_port}/match'
    config = out_dir / 'mediamtx.yml'                                                  # a private relay on its own ports (the production server and its relay are not touched)
    yml = ['logLevel: error', 'rtsp: true', f'rtspAddress: 127.0.0.1:{rtsp_port}', 'rtspTransports: [tcp]', 'rtmp: false', 'hls: false', 'webrtc: false', 'srt: true',
           f'srtAddress: 127.0.0.1:{target_port}', 'api: false', 'metrics: false', 'pprof: false', 'playback: false', 'paths:', '  match: {}']
    config.write_text(chr(10).join(yml) + chr(10), encoding='utf-8')
    relay = subprocess.Popen([str(args.mediamtx), str(config)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.5)
    server = start_bench_server(store, http_port)
    live_args = [source_url, str(args.calibrations), args.camera, '--direction', str(args.direction), '--team', args.team, '--detector', str(args.detector),
                 '--classifier', str(args.classifier), '--reference-bg', *map(str, args.reference_bg), '--shift', *map(str, args.shift),
                 '--seconds', str(seconds + 600), '--store', str(store), '--session', session, '--heartbeat-seconds', '2']
    env = dict(os.environ)
    env['PYTHONIOENCODING'] = 'utf-8'
    env['PYTHONUNBUFFERED'] = '1'
    env['OPENCV_FFMPEG_CAPTURE_OPTIONS'] = 'rtsp_transport;tcp' + ('|' + profile['cv'] if profile['cv'] else '')
    cmd = [sys.executable, '-X', 'utf8', str(Path(__file__).resolve()), '--worker', '--ready-file', str(out_dir / 'ready.txt'), '--log-file', str(out_dir / 'worker_log.json'), '--live-args', *live_args]
    run_log = (out_dir / 'run.log').open('w', encoding='utf-8')
    worker_proc = subprocess.Popen(cmd, stdout=run_log, stderr=subprocess.STDOUT, env=env)
    for _ in range(600):                                                              # the model loads first (tens of seconds), then the listener opens
        if (out_dir / 'ready.txt').exists() or worker_proc.poll() is not None:
            break
        time.sleep(0.2)
    if not (out_dir / 'ready.txt').exists():
        raise SystemExit('The worker did not get to the listening step; see ' + str(out_dir / 'run.log'))
    time.sleep(0.5)
    proxy = transport.Proxy(listen_port, target_port, profile['loss'], profile['delay'], profile['jitter'], seed=7)
    proxy.start()
    kbps = profile['kbps']
    sender = subprocess.Popen([str(args.ffmpeg), '-hide_banner', '-loglevel', 'error', '-nostdin', '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-s', '1920x1080', '-r', str(FPS), '-i', '-',
                               '-c:v', 'libx264', '-preset', 'veryfast', '-tune', 'zerolatency', '-b:v', f'{kbps}k', '-maxrate', f'{kbps}k', '-bufsize', f'{2 * kbps}k',
                               '-g', str(FPS), '-bf', '0', '-pix_fmt', 'yuv420p', '-f', 'mpegts', f'srt://127.0.0.1:{listen_port}?mode=caller&streamid=publish:match&latency={latency_us}&pkt_size=1316&connect_timeout=15000'],
                              stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    sent = {}
    stop = threading.Event()

    # observers: the alerts file (10 ms) and the bench API (100 ms)
    file_seen, api_seen, rows = {}, {}, {}

    def watch_file():
        done = 0
        while not stop.is_set():
            try:
                if alerts_file.exists():
                    lines = alerts_file.read_text(encoding='utf-8').splitlines()
                    now = time.time()
                    for i in range(done, len(lines)):
                        if not lines[i].strip():
                            continue
                        try:
                            rows[i] = json.loads(lines[i])
                        except ValueError:
                            break
                        file_seen[i] = now
                        done = i + 1
            except OSError:
                pass
            time.sleep(0.01)

    def watch_api():
        url = f'http://127.0.0.1:{http_port}/api/v1/bench?session={session}'
        while not stop.is_set():
            try:
                body = json.loads(urllib.request.urlopen(url, timeout=2).read())
                now = time.time()
                for a in ([body['current']] if body.get('current') else []) + list(body.get('recent') or []):
                    api_seen.setdefault(a['number'], now)
            except Exception:
                pass
            time.sleep(0.1)
    threads = [threading.Thread(target=watch_file, daemon=True), threading.Thread(target=watch_api, daemon=True)]
    for t in threads:
        t.start()

    # the sender: real time, one frame every 1/30 s
    cap = cv2.VideoCapture(str(args.segment))
    total = int(seconds * FPS)
    t0 = time.time()
    for i in range(total):
        ok, frame = cap.read()
        if not ok:
            break
        wait = t0 + i / FPS - time.time()
        if wait > 0:
            time.sleep(wait)
        draw_marker(frame, i)
        sent[i] = time.time()
        try:
            sender.stdin.write(frame.tobytes())
        except (BrokenPipeError, OSError):
            break
    cap.release()
    try:
        sender.stdin.close()
    except OSError:
        pass
    time.sleep(4.0)                                                                  # the last frames still in flight are analysed and their alerts written
    worker_proc.kill()
    time.sleep(0.5)
    stop.set()
    for t in threads:
        t.join(timeout=3)
    try:
        sender.wait(timeout=10)
    except subprocess.TimeoutExpired:
        sender.kill()
    sender_error = (sender.stderr.read() or b'').decode('utf-8', 'replace').strip()[-300:]
    proxy.stop.set()
    proxy.join(timeout=2)
    server.should_exit = True
    relay.kill()
    run_log.close()

    log = json.loads((out_dir / 'worker_log.json').read_text(encoding='utf-8'))
    key = lambda name: {int(k): v for k, v in log[name].items()}
    read, det0, det1, upd0, upd1 = key('read'), key('det0'), key('det1'), key('upd0'), key('upd1')
    frames = []
    for m in sorted(upd1):
        if m not in sent or m not in read:
            continue
        frames.append({'marker': m, 'send_to_read': read[m] - sent[m], 'wait': det0[m] - read[m], 'detect': det1[m] - det0[m], 'track': upd0[m] - det1[m], 'analyzer': upd1[m] - upd0[m],
                       'total_to_analyzer_end': upd1[m] - sent[m]})
    events = []
    for i, row in sorted(rows.items()):
        m = row.get('e2e_marker')
        if m is None or m not in sent or m not in upd1:
            continue
        api = api_seen.get(i)
        events.append({'row': i, 'kind': row.get('kind'), 'probe': bool(row.get('e2e_probe')), 'marker': m, 'send_to_analyzer_end': upd1[m] - sent[m],
                       'analyzer_end_to_file': file_seen[i] - upd1[m], 'file_to_api': None if api is None else api - file_seen[i],
                       'send_to_api': None if api is None else api - sent[m], 'row_latency_ms_in_file': row.get('latency_ms')})
    # the page asks once a second: the first poll at or after the API time, over 10 phases of the poll clock
    page = []
    for e in events:
        if e['send_to_api'] is None:
            continue
        for phase in range(10):
            offset = phase / 10.0
            page.append(e['send_to_api'] + ((offset - (e['send_to_api'] % 1.0)) % 1.0))
    probe = [e for e in events if e['probe']]
    natural = [e for e in events if not e['probe']]
    summary = {
        'condition': name, 'profile': profile, 'video_seconds_sent': round(total / FPS, 1), 'frames_sent': len(sent), 'frames_decoded_by_worker': log['reads'], 'frames_with_unreadable_marker': log['undecoded'],
        'frames_analysed_and_matched': len(frames), 'proxy_data_packets': proxy.seen, 'proxy_dropped': proxy.dropped, 'sender_error': sender_error,
        'stage_send_to_read_s': summarise([f['send_to_read'] for f in frames]), 'stage_wait_for_analysis_s': summarise([f['wait'] for f in frames]),
        'stage_detector_s': summarise([f['detect'] for f in frames]), 'stage_tracking_s': summarise([f['track'] for f in frames]), 'stage_analyzer_s': summarise([f['analyzer'] for f in frames]),
        'frame_total_to_analyzer_end_s': summarise([f['total_to_analyzer_end'] for f in frames]),
        'probe_events': len(probe), 'natural_alerts': len(natural),
        'event_analyzer_end_to_file_s': summarise([e['analyzer_end_to_file'] for e in events]), 'event_file_to_api_s': summarise([e['file_to_api'] for e in events]),
        'event_total_to_api_s': summarise([e['send_to_api'] for e in events]), 'event_total_to_page_s': summarise(page),
        'probe_total_to_api_s': summarise([e['send_to_api'] for e in probe]), 'natural_total_to_api_s': summarise([e['send_to_api'] for e in natural]),
        'natural_alert_kinds': [e['kind'] for e in natural]}
    (out_dir / 'frames.json').write_text(json.dumps(frames), encoding='utf-8')
    (out_dir / 'events.json').write_text(json.dumps(events, ensure_ascii=False), encoding='utf-8')
    return summary


def orchestrate(args):
    results = {'segment': str(args.segment), 'seconds': args.seconds, 'camera': args.camera, 'conditions': {}}
    if args.output.exists():                                                          # continue after an interruption: finished conditions stay, only the missing ones run
        try:
            results['conditions'] = json.loads(args.output.read_text(encoding='utf-8')).get('conditions', {})
        except ValueError:
            pass
    args.work_dir.mkdir(parents=True, exist_ok=True)
    args.segment, args.calibrations, args.detector, args.classifier, args.ffmpeg, args.mediamtx = (x.resolve() for x in (args.segment, args.calibrations, args.detector, args.classifier, args.ffmpeg, args.mediamtx))
    for name in args.profiles:
        if name in results['conditions']:
            print('already done, kept:', name, flush=True)
            continue
        print('running', name, flush=True)
        summary = run_condition(name, PROFILES[name], args, args.work_dir / name)
        results['conditions'][name] = summary
        args.output.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding='utf-8')
        print(name, 'frames', summary['frames_analysed_and_matched'], 'events', summary['probe_events'], 'send->read p50', summary['stage_send_to_read_s'].get('p50'),
              'event->api p50/p95', summary['event_total_to_api_s'].get('p50'), summary['event_total_to_api_s'].get('p95'), flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--worker', action='store_true', help='internal: the receiving side')
    p.add_argument('--ready-file'); p.add_argument('--log-file'); p.add_argument('--live-args', nargs=argparse.REMAINDER, default=[])
    p.add_argument('--segment', type=Path); p.add_argument('--calibrations', type=Path); p.add_argument('--camera', default='cam3')
    p.add_argument('--direction', type=int, choices=(1, -1), default=1); p.add_argument('--team', choices=('A', 'B'), default='B')
    p.add_argument('--detector', type=Path); p.add_argument('--classifier', type=Path)
    p.add_argument('--reference-bg', type=float, nargs=4); p.add_argument('--shift', type=float, nargs=2, default=(0.0, 0.0))
    p.add_argument('--ffmpeg', type=Path); p.add_argument('--mediamtx', type=Path); p.add_argument('--seconds', type=float, default=240.0)
    p.add_argument('--profiles', nargs='+', choices=list(PROFILES)); p.add_argument('--work-dir', type=Path); p.add_argument('--output', type=Path)
    args = p.parse_args()
    if args.worker:
        worker(args)
    else:
        orchestrate(args)


if __name__ == '__main__':
    main()
