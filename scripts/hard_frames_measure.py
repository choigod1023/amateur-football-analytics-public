"""Measure which cheap rules flag the frames where a detector misses a person the user confirmed (research, read only; wiki/hard-frames.md).

python scripts/hard_frames_measure.py <review store> <video> <out.json> <weights> [<weights> ...] [--history 6] [--controls 100] [--seed 7]

For every frame that holds a human-confirmed box (the 116 boxes of scripts/bench_human_boxes.py) and for random control frames away from them, the detector is run
on the frames of the `history` seconds before it at 5 fps, the way the live analysis sees them (tile detector, confidence 0.10). Per frame the person count and the colour
rule counts (neon = team A, dark = team B) are stored; for the last frame the boxes of every detector are stored too. app/hard_frames.py rules are then scored on this file
by scripts/hard_frames_score.py. Nothing is written into the review store.
"""
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
import cv2  # noqa: E402
import track_review_clip as tracker  # noqa: E402
from app.camera_segments import camera_of  # noqa: E402
from app.hard_frames import colour_counts  # noqa: E402
from bench_human_boxes import build_cases  # noqa: E402

CONF = 0.10
FPS = 5.0


def read_window(cap, end, history):
    """-> list of (second, frame) at 5 fps from end-history to end (the video has variable frame times, so the frame time is read back)."""
    start = max(0.0, end - history)
    cap.set(cv2.CAP_PROP_POS_MSEC, start * 1000)
    out, want = [], start
    while want <= end + 1e-6:
        ok = cap.grab()
        if not ok:
            break
        ts = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000
        if ts + 1e-3 >= want:
            ok, frame = cap.retrieve()
            if not ok:
                break
            out.append((round(ts, 2), frame))
            want = ts + 1 / FPS
    return out


def main():
    args = sys.argv[1:]
    opts = {'--history': 6.0, '--controls': 100, '--seed': 7}
    for key in list(opts):
        if key in args:
            i = args.index(key)
            opts[key] = type(opts[key])(args[i + 1])
            del args[i:i + 2]
    if len(args) < 4:
        raise SystemExit(__doc__)
    store, video, out_path, weights = args[0], args[1], args[2], args[3:]
    from ultralytics import YOLO
    models = [(Path(w).parent.name + '/' + Path(w).name, YOLO(w)) for w in weights]
    cases = build_cases(store, video)
    targets = []
    for c in cases:
        cam = camera_of(c['time'])
        if cam is None:
            continue
        targets.append({'time': c['time'], 'camera': cam, 'group': c['group'], 'boxes': c['boxes'], 'tags': c['tags'], 'image': c['image']})
    human_times = [t['time'] for t in targets]
    rng = random.Random(opts['--seed'])
    controls = []
    while len(controls) < opts['--controls']:
        t = round(rng.uniform(75, 2900), 1)
        cam = camera_of(t)
        if cam is None or camera_of(t - opts['--history']) != cam or any(abs(t - h) < 15 for h in human_times):
            continue
        controls.append({'time': t, 'camera': cam, 'group': 'control', 'boxes': [], 'tags': [], 'image': None})
    cap = cv2.VideoCapture(str(video))
    result = {'history': opts['--history'], 'confidence': CONF, 'weights': [m[0] for m in models], 'rows': []}
    if Path(out_path).exists():                                                         # resume after an interruption: finished frames are kept and not measured again
        old = json.loads(Path(out_path).read_text(encoding='utf-8'))
        if old.get('weights') == result['weights'] and old.get('history') == result['history']:
            result['rows'] = old['rows']
    done = {(r['group'], r['time']) for r in result['rows']}
    print('already done:', len(done), flush=True)
    for number, item in enumerate(targets + controls):
        if (item['group'], item['time']) in done:
            continue
        frames = read_window(cap, item['time'], opts['--history'])
        if len(frames) < 10:
            continue
        row = {'time': item['time'], 'camera': item['camera'], 'group': item['group'], 'human_boxes': [[float(v) for v in b] for b in item['boxes']], 'tags': item['tags'], 'models': {}}
        for name, model in models:
            history = []
            for ts, frame in frames[:-1]:
                dets = tracker.detect(model, frame, item['camera'], 0, CONF)
                history.append({'t': ts, **colour_counts(frame, dets)})
            last_image = item['image'] if item['image'] is not None else frames[-1][1]
            dets = tracker.detect(model, last_image, item['camera'], 0, CONF)
            row['models'][name] = {'history': history, 'last': {**colour_counts(last_image, dets), 'boxes': [[round(float(v), 1) for v in d[:5]] for d in dets]}}
        result['rows'].append(row)
        tmp = Path(out_path).with_suffix('.tmp')                                        # written after every frame (a power cut must not lose finished work)
        tmp.write_text(json.dumps(result), encoding='utf-8')
        tmp.replace(out_path)
        print(number, len(targets) + len(controls), flush=True)
    Path(out_path).write_text(json.dumps(result), encoding='utf-8')
    print('done', len(result['rows']), 'frames')


if __name__ == '__main__':
    main()
