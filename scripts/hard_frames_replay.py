"""Replay a stretch of the match video through the hard-frame collector with two detectors (research, offline; wiki/hard-frames.md).

python scripts/hard_frames_replay.py <video> <out folder> <start> <seconds> <camera> <weights A> <weights B> [--settings '{"drop": 4}'] [--max-frames N]

Each analysed frame (5 fps, the tile detector at confidence 0.10, like the live analysis) is detected by both detectors. Per detector a collector (app/hard_frames.py) saves its
suspicious frames into <out folder>/<detector name>/ with the other detector's boxes as `other_boxes` for the disagreement rule. Every frame is also logged to
<out folder>/frames_<detector>.jsonl (time, counts, the rules that fired before the budget, how many boxes of the other detector with score >= 0.35 this detector lacks),
so that rule rates can be computed. Only the images the collector keeps are written. The run can be repeated: a finished folder is not run again.
Nothing is written into the review store.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
import cv2  # noqa: E402
import track_review_clip as tracker  # noqa: E402
from app.hard_frames import HardFrameCollector, colour_counts, judge, _iou  # noqa: E402

CONF = 0.10
FPS = 5.0


def frames_of(cap, start, end):
    """(second, frame) at 5 fps between start and end; the frame time is read back because the video has variable frame times."""
    cap.set(cv2.CAP_PROP_POS_MSEC, start * 1000)
    want = start
    while want <= end:
        if not cap.grab():
            return
        ts = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000
        if ts + 1e-3 >= want:
            ok, frame = cap.retrieve()
            if not ok:
                return
            yield ts, frame
            want = ts + 1 / FPS


def main():
    args = sys.argv[1:]
    settings, max_frames = {}, None
    if '--settings' in args:
        i = args.index('--settings')
        settings = json.loads(args[i + 1])
        del args[i:i + 2]
    if '--max-frames' in args:
        i = args.index('--max-frames')
        settings['max_frames'] = int(args[i + 1])
        del args[i:i + 2]
    if len(args) != 7:
        raise SystemExit(__doc__)
    video, out, start, seconds, camera = args[0], Path(args[1]), float(args[2]), float(args[3]), args[4]
    names = [Path(w).parent.name for w in args[5:7]]
    if (out / 'done.flag').exists():
        print('already done')
        return
    from ultralytics import YOLO
    models = [YOLO(w) for w in args[5:7]]
    collectors = [HardFrameCollector(out / n, camera, n, settings) for n in names]
    logs = [open(out / f'frames_{n}.jsonl', 'w', encoding='utf-8') for n in names]
    cap = cv2.VideoCapture(video)
    count = 0
    for t, frame in frames_of(cap, start, start + seconds):
        found = [[[round(float(v), 1) for v in d[:5]] for d in tracker.detect(m, frame, camera, 0, CONF)] for m in models]
        for k in (0, 1):
            mine, other = found[k], found[1 - k]
            counts = colour_counts(frame, mine)
            lacking = sum(1 for o in other if o[4] >= 0.35 and all(_iou(o, b) < 0.3 for b in mine))
            c = collectors[k]
            history = [(h[1], h[2]) for h in c.history]
            reasons = judge(history, counts['n'], counts['dark'], mine, other, c.settings)
            saved = c.observe(t, frame, mine, counts['dark'], camera, other)
            logs[k].write(json.dumps({'t': round(t, 2), 'n': counts['n'], 'dark': counts['dark'], 'neon': counts['neon'], 'reasons': reasons, 'lacking_vs_other': lacking, 'saved': bool(saved), 'other_boxes': other if saved else None}) + '\n')
        count += 1
        if count % 100 == 0:
            print(count, 'frames', [c.saved for c in collectors], flush=True)
    for f in logs:
        f.close()
    (out / 'done.flag').write_text(json.dumps({'frames': count, 'settings': c.settings, 'summaries': [c.summary() for c in collectors]}), encoding='utf-8')
    print('done', count, [c.summary() for c in collectors])


if __name__ == '__main__':
    main()
