"""Detect people in a long stretch of the match video once and keep the result, so later steps can be repeated quickly.

Usage: python scripts/cache_detections.py <video> <start second> <end second> <cam1|cam3> <output folder>
       [--model yolo11n.pt] [--confidence 0.05] [--pass <weights>:<confidence>:<tile px> ...] [--fps 5] [--chunk 60] [--ffmpeg <path>]

--pass (repeatable) runs several detectors one after the other, for example a large one on 384 px tiles and then a small one
on 512 px tiles; a box of a later pass is kept only where no earlier box overlaps it by more than 60 %. Without --pass one pass
with --model and --confidence is made.

The stretch is cut into chunks of `chunk` seconds; each chunk is decoded to temporary frames, every detection gets its
colour features (see app/team_role_features.py) and one file chunk_<start>.npz is written (frames are numbered from the
start of the whole stretch). Chunks that already exist are skipped, so an interrupted run can be resumed. The video, the
frames and the cache stay on this computer; the temporary frames are deleted after each chunk.
"""
import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))


def chunk_plan(start, end, chunk):
    """[(chunk start, length)] covering [start, end); the last chunk may be shorter."""
    plan, at = [], start
    while at < end:
        plan.append((at, min(chunk, end - at)))
        at += chunk
    return plan


def parse_passes(items):
    """['w.pt:0.05:384', ...] -> [('w.pt', 0.05, 384), ...] (the weights path may contain a drive letter colon)."""
    passes = []
    for item in items:
        path, confidence, tile = item.rsplit(':', 2)
        passes.append((path, float(confidence), int(tile)))
    return passes


def overlap_share(a, b):
    width = min(a[2], b[2]) - max(a[0], b[0])
    height = min(a[3], b[3]) - max(a[1], b[1])
    if width <= 0 or height <= 0:
        return 0.0
    return width * height / max(1e-6, min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1])))


def detect_passes(tracker, models, passes, image, camera):
    """[(box, score, pass index)] of all passes; a later pass only adds boxes that no earlier box overlaps by more than 60 %."""
    kept = []
    for index, (path, confidence, tile) in enumerate(passes):
        tracker.TILE = tile
        for d in tracker.detect(models[path], image, camera, 0, confidence):
            box = [float(v) for v in d[:4]]
            if all(overlap_share(box, k[0]) <= 0.6 for k in kept):
                kept.append((box, float(d[4]), index))
    tracker.TILE = 384
    return kept


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('video')
    parser.add_argument('start', type=float)
    parser.add_argument('end', type=float)
    parser.add_argument('camera', choices=['cam1', 'cam3'])
    parser.add_argument('output')
    parser.add_argument('--model', default='yolo11n.pt')
    parser.add_argument('--confidence', type=float, default=0.05)
    parser.add_argument('--pass', dest='passes', action='append', default=[], help='weights:confidence:tile, repeatable')
    parser.add_argument('--fps', type=float, default=5.0)
    parser.add_argument('--chunk', type=int, default=60)
    parser.add_argument('--ffmpeg', default='ffmpeg')
    args = parser.parse_args()
    import cv2
    import numpy as np
    from ultralytics import YOLO
    import track_review_clip as tracker
    from app.team_role_features import box_features

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    passes = parse_passes(args.passes) if args.passes else [(args.model, args.confidence, 384)]
    models = {path: YOLO(path) for path, _, _ in passes}
    for at, length in chunk_plan(args.start, args.end, args.chunk):
        target = out / f'chunk_{int(at):05d}.npz'
        if target.exists():
            continue
        work = Path(tempfile.mkdtemp(prefix='frames_'))
        try:
            subprocess.run([args.ffmpeg, '-hide_banner', '-loglevel', 'error', '-y', '-ss', str(at), '-t', str(length), '-i', args.video,
                            '-vf', f'fps={args.fps}', '-q:v', '3', str(work / 'f_%04d.jpg')], check=True)
            frames, boxes, scores, feats, sources = [], [], [], [], []
            files = sorted(work.glob('f_*.jpg'))
            for index, path in enumerate(files):
                image = cv2.imread(str(path))
                height, width = image.shape[:2]
                for box, score, source in detect_passes(tracker, models, passes, image, args.camera):
                    frames.append(index)
                    boxes.append(box)
                    scores.append(score)
                    sources.append(source)
                    feats.append(box_features(image, [box[0] / width, box[1] / height, box[2] / width, box[3] / height]))
            np.savez_compressed(target, frames=np.array(frames, np.int32), boxes=np.array(boxes, np.float32).reshape(-1, 4),
                                scores=np.array(scores, np.float32), source=np.array(sources, np.int8), feats=np.array(feats, np.float32).reshape(len(frames), -1),
                                start=at, fps=args.fps, frame_count=len(files), camera=args.camera)
            print(f'chunk {at:.0f} s: {len(files)} frames, {len(frames)} detections', flush=True)
        finally:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == '__main__':
    main()
