"""Degraded local SRT test for videos WITHOUT labels (compared with the clean decode of the same video).

One video segment is sent over loopback SRT (ffmpeg caller -> UDP proxy -> ffmpeg listener) with a bitrate, a picture height, an SRT latency and,
in the proxy, packet loss, delay and jitter. The received stream is measured twice:
  * transport: delay of the arrival against the media time, received frames against sent frames, decoder error lines, received bitrate;
  * detection: persons found on the received frames (same tile detector as the live analysis) against persons found on the ORIGINAL frames
    of the same moments. This is agreement with the undamaged video, not accuracy against a human label.
Everything stays on this computer (127.0.0.1). It is not a test of a phone, a mobile network or a router.
"""
import argparse, heapq, json, random, select, socket, statistics, subprocess, sys, tempfile, threading, time
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import track_review_clip as tile_detector  # noqa: E402

FPS = 30
# name: picture height, video kbit/s, SRT latency ms, loss share of data packets, one-way delay ms, jitter ms (plus or minus)
PROFILES = {
    'clean': dict(height=720, kbps=4000, latency=200, loss=0.0, delay=0, jitter=0),
    'br2000': dict(height=720, kbps=2000, latency=200, loss=0.0, delay=0, jitter=0),
    'br1000': dict(height=720, kbps=1000, latency=200, loss=0.0, delay=0, jitter=0),
    'br500': dict(height=720, kbps=500, latency=200, loss=0.0, delay=0, jitter=0),
    'h540_br1000': dict(height=540, kbps=1000, latency=200, loss=0.0, delay=0, jitter=0),
    'h360_br600': dict(height=360, kbps=600, latency=200, loss=0.0, delay=0, jitter=0),
    'loss1_lat200': dict(height=720, kbps=4000, latency=200, loss=0.01, delay=20, jitter=0),
    'loss5_lat200': dict(height=720, kbps=4000, latency=200, loss=0.05, delay=20, jitter=0),
    'loss5_lat1500': dict(height=720, kbps=4000, latency=1500, loss=0.05, delay=20, jitter=0),
    'loss10_lat200': dict(height=720, kbps=4000, latency=200, loss=0.10, delay=20, jitter=0),
    'cell_like': dict(height=720, kbps=2000, latency=500, loss=0.02, delay=60, jitter=40),
    # for 1080p sources
    'p1080_8000': dict(height=1080, kbps=8000, latency=200, loss=0.0, delay=0, jitter=0),
    'p1080_4000': dict(height=1080, kbps=4000, latency=200, loss=0.0, delay=0, jitter=0),
    'p1080_2000': dict(height=1080, kbps=2000, latency=200, loss=0.0, delay=0, jitter=0),
    'p1080_loss10': dict(height=1080, kbps=4000, latency=200, loss=0.10, delay=20, jitter=0),
}


class Proxy(threading.Thread):
    """UDP relay between the SRT sender and receiver. Only big packets (SRT data) are dropped, only after the handshake, and only toward the receiver."""

    def __init__(self, listen_port, target_port, loss, delay_ms, jitter_ms, seed=1, grace_s=3.0):
        super().__init__(daemon=True)
        self.front = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); self.front.bind(('127.0.0.1', listen_port))
        self.back = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); self.back.bind(('127.0.0.1', 0))
        self.target = ('127.0.0.1', target_port)
        self.loss, self.delay, self.jitter, self.grace = loss, delay_ms / 1000, jitter_ms / 1000, grace_s
        self.rng = random.Random(seed)
        self.stop = threading.Event()
        self.sender = None
        self.heap, self.order = [], 0
        self.seen = self.dropped = 0
        self.started = time.time()

    def _schedule(self, due, sock, data, addr):
        self.order += 1
        heapq.heappush(self.heap, (due, self.order, sock, data, addr))

    def run(self):
        while not self.stop.is_set():
            wait = 0.005
            if self.heap:
                wait = max(0.0, min(wait, self.heap[0][0] - time.time()))
            ready, _, _ = select.select([self.front, self.back], [], [], wait)
            now = time.time()
            for sock in ready:
                try:
                    data, addr = sock.recvfrom(65535)
                except OSError:
                    continue
                if sock is self.front:
                    self.sender = addr
                    if len(data) > 200:
                        self.seen += 1
                        if now - self.started > self.grace and self.rng.random() < self.loss:
                            self.dropped += 1
                            continue
                    jitter = self.rng.uniform(-self.jitter, self.jitter)
                    self._schedule(now + max(0.0, self.delay + jitter), self.back, data, self.target)
                elif self.sender is not None:
                    self._schedule(now + self.delay, self.front, data, self.sender)
            now = time.time()
            while self.heap and self.heap[0][0] <= now:
                _, _, sock, data, addr = heapq.heappop(self.heap)
                try:
                    sock.sendto(data, addr)
                except OSError:
                    pass
        self.front.close(); self.back.close()


def free_udp_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.bind(('127.0.0.1', 0)); port = s.getsockname()[1]; s.close()
    return port


def run_transport(ffmpeg, video, start, seconds, profile, out_ts, seed):
    """Send the segment and write what arrives to out_ts. Returns the transport numbers."""
    listen_port, target_port = free_udp_port(), free_udp_port()
    latency_us = int(profile['latency'] * 1000)
    proxy = Proxy(listen_port, target_port, profile['loss'], profile['delay'], profile['jitter'], seed=seed)
    proxy.start()
    receiver = subprocess.Popen([str(ffmpeg), '-hide_banner', '-loglevel', 'error', '-nostdin', '-progress', 'pipe:1', '-nostats',
                                 '-i', f'srt://127.0.0.1:{target_port}?mode=listener&latency={latency_us}', '-c', 'copy', '-f', 'mpegts', '-y', str(out_ts)],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
    lags, errors = [], []
    t0 = [None]

    def read_progress():
        for line in receiver.stdout:
            if line.startswith('out_time_us=') and t0[0] is not None:
                try:
                    media = int(line.split('=')[1]) / 1e6
                except ValueError:
                    continue
                if media > 0:
                    lags.append((time.time() - t0[0], media))
    thread = threading.Thread(target=read_progress, daemon=True); thread.start()
    time.sleep(1.0)
    kbps = profile['kbps']
    sender = subprocess.Popen([str(ffmpeg), '-hide_banner', '-loglevel', 'error', '-nostdin', '-re', '-ss', str(start), '-t', str(seconds), '-i', str(video), '-an',
                               '-vf', f"scale=-2:{profile['height']}", '-r', str(FPS), '-c:v', 'libx264', '-preset', 'veryfast', '-tune', 'zerolatency',
                               '-b:v', f'{kbps}k', '-maxrate', f'{kbps}k', '-bufsize', f'{2 * kbps}k', '-g', str(FPS), '-bf', '0', '-pix_fmt', 'yuv420p',
                               '-f', 'mpegts', f'srt://127.0.0.1:{listen_port}?mode=caller&latency={latency_us}&pkt_size=1316'],
                              stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    t0[0] = time.time()
    try:
        sender.wait(timeout=seconds + 40)
    except subprocess.TimeoutExpired:
        sender.kill()
    sender_error = (sender.stderr.read() or '').strip()
    try:
        receiver.wait(timeout=latency_us / 1e6 + 15)
    except subprocess.TimeoutExpired:
        receiver.kill()
    thread.join(timeout=3)
    receiver_error = (receiver.stderr.read() or '').strip()
    proxy.stop.set(); proxy.join(timeout=2)
    # delay of the arrival against the media time once the stream is running (progress lines come about every half second)
    steady = [wall - media for wall, media in lags if media >= 5.0]
    delay = {}
    if steady:
        steady.sort()
        delay = {'median_s': round(statistics.median(steady), 2), 'p95_s': round(steady[min(len(steady) - 1, int(len(steady) * 0.95))], 2), 'max_s': round(steady[-1], 2)}
    return {'proxy_data_packets': proxy.seen, 'proxy_dropped': proxy.dropped, 'arrival_delay': delay,
            'sender_error': sender_error[-300:], 'receiver_error': receiver_error[-300:]}


def decode_errors(ffmpeg, path):
    result = subprocess.run([str(ffmpeg), '-hide_banner', '-v', 'error', '-i', str(path), '-f', 'null', '-'], capture_output=True, text=True)
    lines = [ln for ln in (result.stderr or '').splitlines() if ln.strip()]
    return len(lines)


def read_all(path):
    """Every decoded frame of the file with its time in ms (relative to the first decoded frame)."""
    cap = cv2.VideoCapture(str(path))
    frames, first = [], None
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        ms = cap.get(cv2.CAP_PROP_POS_MSEC)
        if first is None:
            first = ms
        frames.append((ms - first, frame))
    cap.release()
    return frames


def iou(a, b):
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0])); iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def match_count(reference, found, threshold=0.5):
    """Greedy one-to-one matches (highest IoU first)."""
    pairs = sorted(((iou(r, f), i, j) for i, r in enumerate(reference) for j, f in enumerate(found)), reverse=True)
    used_r, used_f, count = set(), set(), 0
    for value, i, j in pairs:
        if value < threshold:
            break
        if i in used_r or j in used_f:
            continue
        used_r.add(i); used_f.add(j); count += 1
    return count


def detect(model, frame, camera, device, confidence, scale):
    return [[d[0] * scale, d[1] * scale, d[2] * scale, d[3] * scale] for d in tile_detector.detect(model, frame, camera, device, confidence)]


def align_offset_ms(received, first_reference_frame):
    """Time in the received file that shows the same picture as the first original frame (the stream starts a little later than the media time and the
    first frames can be lost). Looks at the first 3 seconds only."""
    small = lambda f: cv2.resize(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY), (160, 90)).astype(np.float32)
    target = small(first_reference_frame)
    best = None
    for ms, frame in received[:90]:
        error = float(np.mean((small(frame) - target) ** 2))
        if best is None or error < best[0]:
            best = (error, ms)
    return best[1] if best else 0.0


def detection_agreement(model, device, confidence, reference_boxes, received, sample_times_ms, height, source_height, truth=None):
    """reference_boxes: {k: boxes on the original frame k}. Received frames are tested at their own size and the boxes are scaled back."""
    scale = source_height / height
    ref_total = got_total = matched = used = truth_total = truth_matched = 0
    for k, t in enumerate(sample_times_ms):
        if not received:
            break
        index = min(range(len(received)), key=lambda i: abs(received[i][0] - t))
        if abs(received[index][0] - t) > 120:
            continue                                    # nothing arrived near this moment: counted as lost below
        found = detect(model, received[index][1], 'yt', device, confidence, scale)
        ref = reference_boxes[k]
        ref_total += len(ref); got_total += len(found); matched += match_count(ref, found); used += 1
        if truth is not None:
            truth_total += len(truth[k]); truth_matched += match_count(truth[k], found)
    extra = {'human_label_boxes': truth_total, 'matched_human_labels': truth_matched,
             'recall_vs_human_labels': round(truth_matched / truth_total, 3) if truth_total else None} if truth is not None else {}
    return {**extra, 'sample_moments_used': used, 'reference_boxes': ref_total, 'received_boxes': got_total, 'matched': matched,
            'recall_vs_clean_original': round(matched / ref_total, 3) if ref_total else None,
            'precision_vs_clean_original': round(matched / got_total, 3) if got_total else None}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('video', type=Path); p.add_argument('--ffmpeg', type=Path, required=True); p.add_argument('--detector', type=Path, required=True)
    p.add_argument('--labels', type=Path, help='JSON {frame: [[x, y, w, h], ...]} of human boxes in the pixels of the source video; the samples are then the labelled frames')
    p.add_argument('--start', type=float, default=1200.0); p.add_argument('--seconds', type=float, default=60.0)
    p.add_argument('--pitch-top', type=float, required=True, help='fraction of the picture height above which there is no pitch (stands, sky)')
    p.add_argument('--profiles', nargs='+', default=list(PROFILES), choices=list(PROFILES))
    p.add_argument('--confidence', type=float, default=0.25); p.add_argument('--device', default='0')
    p.add_argument('--sample-fps', type=float, default=5.0); p.add_argument('--work-dir', type=Path, required=True); p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    from ultralytics import YOLO
    tile_detector.PITCH_TOP['yt'] = args.pitch_top
    model = YOLO(str(args.detector))
    args.work_dir.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(str(args.video)); source_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    truth = None
    ref_frames = None
    if args.labels:
        video_fps = cap.get(cv2.CAP_PROP_FPS) or FPS
        by_frame = {int(k): v for k, v in json.loads(args.labels.read_text(encoding='utf-8')).items() if v}
        step = max(1, round(video_fps / args.sample_fps))
        first, last = int(args.start * video_fps), int((args.start + args.seconds) * video_fps)
        ref_frames = []
        for f in sorted(by_frame):
            if first <= f < last and (not ref_frames or f - ref_frames[-1] >= step):
                ref_frames.append(f)
        if len(ref_frames) < 10:
            raise SystemExit('too few labelled frames in the chosen window')
        args.start = ref_frames[0] / video_fps
        times = [(f - ref_frames[0]) / video_fps for f in ref_frames]
        truth = [[[x, y, x + w, y + h] for x, y, w, h in by_frame[f]] for f in ref_frames]
    else:
        times = [k / args.sample_fps for k in range(int(args.seconds * args.sample_fps))]
    reference, first_frame = [], None
    for k, t in enumerate(times):
        if ref_frames is not None:
            cap.set(cv2.CAP_PROP_POS_FRAMES, ref_frames[k])
        else:
            cap.set(cv2.CAP_PROP_POS_MSEC, (args.start + t) * 1000.0)
        ok, frame = cap.read()
        if ok and first_frame is None:
            first_frame = frame.copy()
        reference.append(detect(model, frame, 'yt', args.device, args.confidence, 1.0) if ok else [])
    cap.release()
    print(f'reference: {sum(len(r) for r in reference) / max(1, len(reference)):.1f} persons per sampled frame on the original', flush=True)
    original_vs_truth = None
    if truth is not None:
        total = sum(len(t) for t in truth); got = sum(match_count(t, r) for t, r in zip(truth, reference))
        original_vs_truth = {'human_label_boxes': total, 'matched': got, 'recall_vs_human_labels': round(got / total, 3) if total else None}
        print(f'original frames against the human labels: {original_vs_truth}', flush=True)
    results = {'video': args.video.name, 'start_s': args.start, 'seconds': args.seconds, 'confidence': args.confidence, 'source_height': source_height,
               'reference_persons_per_frame': round(sum(len(r) for r in reference) / max(1, len(reference)), 2), 'sample_moments': len(times),
               'original_vs_human_labels': original_vs_truth, 'profiles': {}}
    clean_offset = None
    for name in args.profiles:
        profile = PROFILES[name]
        out_ts = args.work_dir / f'{name}.ts'
        info = run_transport(args.ffmpeg, args.video, args.start, args.seconds, profile, out_ts, seed=7)
        size = out_ts.stat().st_size if out_ts.exists() else 0
        received = read_all(out_ts) if size else []
        errors = decode_errors(args.ffmpeg, out_ts) if size else None
        gaps = sum(1 for a, b in zip(received, received[1:]) if b[0] - a[0] > 100)
        row = {**profile, **info, 'received_bytes': size, 'received_kbps': round(size * 8 / args.seconds / 1000) if size else 0,
               'frames_expected': int(args.seconds * FPS), 'frames_decoded': len(received),
               'frames_decoded_share': round(len(received) / (args.seconds * FPS), 3), 'timeline_gaps_over_100ms': gaps, 'decoder_error_lines': errors}
        offset = align_offset_ms(received, first_frame) if received else 0.0
        row['alignment_offset_ms'] = round(offset)
        row['detection'] = detection_agreement(model, args.device, args.confidence, reference, received, [t * 1000.0 + offset for t in times], profile['height'], source_height, truth) if received else None
        results['profiles'][name] = row
        args.output.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding='utf-8')
        d = row['detection'] or {}
        print(f"{name:14s} delay_med={row['arrival_delay'].get('median_s')} frames={row['frames_decoded_share']} gaps={gaps} errors={errors} "
              f"recall={d.get('recall_vs_clean_original')} precision={d.get('precision_vs_clean_original')} vs_human={d.get('recall_vs_human_labels')} dropped={info['proxy_dropped']}/{info['proxy_data_packets']}", flush=True)
        out_ts.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
