"""Compare what a phone app recorded itself with what the server received from the same moment of the stream (for Moblin: its own MP4 recording and the MediaMTX recording).

python scripts/srt_phone_compare.py <phone recording.mp4> <server recording.mp4> --ffmpeg <ffmpeg.exe> --ffprobe <ffprobe.exe> --detector yolo11n.pt --pitch-top 0.5 [--window-start 30 --seconds 30]

What it reports for one test setting (one pair of files):
  * transport facts of both files: codec, picture size, frame rate (nominal and average), bitrate, key frame interval, gaps in the time line
    (the numbers that are really sent, which can differ from the settings shown in the app);
  * the same moment is found in both files by comparing pictures (the recordings start at different times), then persons are detected in both
    with the tile detector of the live analysis and the received picture is compared with the phone's own picture
    (recall and precision against the phone recording, not against a human label).
Nothing is sent anywhere; both files stay on this computer.
"""
import argparse, json, subprocess, sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import srt_degradation_test as base  # noqa: E402
import track_review_clip as tile_detector  # noqa: E402


def probe(ffprobe, path, seconds=120):
    """Codec, size, frame rates, bitrate, key frame interval and time gaps of the first `seconds` of a file."""
    stream = json.loads(subprocess.run([str(ffprobe), '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=codec_name,profile,width,height,avg_frame_rate,r_frame_rate,bit_rate,pix_fmt',
                                        '-show_entries', 'format=duration,bit_rate,size', '-of', 'json', str(path)], capture_output=True, text=True).stdout or '{}')
    packets = subprocess.run([str(ffprobe), '-v', 'error', '-select_streams', 'v:0', '-read_intervals', f'%+{seconds}', '-show_entries', 'packet=pts_time,flags', '-of', 'csv=p=0', str(path)],
                             capture_output=True, text=True).stdout.splitlines()
    times, keys = [], []
    for line in packets:
        parts = line.split(',')
        try:
            t = float(parts[0])
        except (ValueError, IndexError):
            continue
        times.append(t)
        if len(parts) > 1 and 'K' in parts[1]:
            keys.append(t)
    times.sort()
    gaps = [b - a for a, b in zip(times, times[1:])]
    interval = [b - a for a, b in zip(keys, keys[1:])]
    s = (stream.get('streams') or [{}])[0]
    f = stream.get('format') or {}
    fps = lambda text: (lambda a, b: round(float(a) / float(b), 2) if float(b) else None)(*text.split('/')) if text and '/' in text else None
    return {'codec': s.get('codec_name'), 'profile': s.get('profile'), 'size': f"{s.get('width')}x{s.get('height')}", 'nominal_fps': fps(s.get('r_frame_rate')), 'average_fps': fps(s.get('avg_frame_rate')),
            'file_bitrate_kbps': round(float(f['bit_rate']) / 1000) if f.get('bit_rate') else None, 'duration_s': round(float(f['duration']), 1) if f.get('duration') else None,
            'packets_checked': len(times), 'frames_per_second_in_sample': round(len(times) / max(1e-6, times[-1] - times[0]), 2) if len(times) > 1 else None,
            'key_frame_interval_median_s': round(sorted(interval)[len(interval) // 2], 2) if interval else None, 'key_frame_interval_max_s': round(max(interval), 2) if interval else None,
            'time_gaps_over_150ms': sum(1 for g in gaps if g > 0.15), 'longest_gap_s': round(max(gaps), 2) if gaps else None}


def gray(frame):
    return cv2.resize(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (160, 90)).astype(np.float32)


def frame_at(capture, seconds):
    capture.set(cv2.CAP_PROP_POS_MSEC, max(0.0, seconds) * 1000.0)
    ok, frame = capture.read()
    return frame if ok else None


def find_offset(phone, server, window_start, search=40.0, step=0.25):
    """Seconds to add to a phone time to get the same picture in the server recording (the lowest picture difference), and that difference (about 0 to 5 is the same picture)."""
    target = gray(frame_at(phone, window_start))
    best = None
    t = max(0.0, window_start - search)
    while t <= window_start + search:
        frame = frame_at(server, t)
        if frame is not None:
            error = float(np.mean((gray(frame) - target) ** 2))
            if best is None or error < best[0]:
                best = (error, t)
        t += step
    if best is None:
        return None, None
    fine = best
    t = best[1] - step
    while t <= best[1] + step:
        frame = frame_at(server, t)
        if frame is not None:
            error = float(np.mean((gray(frame) - target) ** 2))
            if error < fine[0]:
                fine = (error, t)
        t += 1 / 30
    return fine[1] - window_start, fine[0]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('phone', type=Path); p.add_argument('server', type=Path)
    p.add_argument('--ffmpeg', type=Path, required=True); p.add_argument('--ffprobe', type=Path, required=True); p.add_argument('--detector', type=Path, required=True)
    p.add_argument('--pitch-top', type=float, default=0.5); p.add_argument('--window-start', type=float, default=30.0); p.add_argument('--seconds', type=float, default=30.0)
    p.add_argument('--sample-fps', type=float, default=2.0); p.add_argument('--confidence', type=float, default=0.25); p.add_argument('--device', default='0')
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    result = {'phone_file': args.phone.name, 'server_file': args.server.name, 'phone': probe(args.ffprobe, args.phone), 'server': probe(args.ffprobe, args.server)}
    phone, server = cv2.VideoCapture(str(args.phone)), cv2.VideoCapture(str(args.server))
    offset, error = find_offset(phone, server, args.window_start)
    result['alignment'] = {'server_minus_phone_seconds': None if offset is None else round(offset, 2), 'picture_difference': None if error is None else round(error, 1)}
    if offset is None or error > 400:
        result['detection'] = None
        result['note'] = 'The same moment was not found in both files (picture difference too large); check that both recordings cover the same stream.'
    else:
        from ultralytics import YOLO
        tile_detector.PITCH_TOP['yt'] = args.pitch_top
        model = YOLO(str(args.detector))
        phone_height = int(phone.get(cv2.CAP_PROP_FRAME_HEIGHT)); server_height = int(server.get(cv2.CAP_PROP_FRAME_HEIGHT))
        used = ref_total = got_total = matched = 0
        for k in range(int(args.seconds * args.sample_fps)):
            t = args.window_start + k / args.sample_fps
            a, b = frame_at(phone, t), frame_at(server, t + offset)
            if a is None or b is None:
                continue
            ref = base.detect(model, a, 'yt', args.device, args.confidence, 1.0)
            got = base.detect(model, b, 'yt', args.device, args.confidence, phone_height / server_height)
            ref_total += len(ref); got_total += len(got); matched += base.match_count(ref, got); used += 1
        result['detection'] = {'sample_moments': used, 'phone_boxes': ref_total, 'server_boxes': got_total, 'matched': matched,
                               'recall_vs_phone_recording': round(matched / ref_total, 3) if ref_total else None,
                               'precision_vs_phone_recording': round(matched / got_total, 3) if got_total else None}
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
