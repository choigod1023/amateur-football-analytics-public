"""Follow the ball in the clips of the detailed report (scenes.json of scripts/make_scene_clips.py).

python scripts/track_ball_scenes.py --scenes clips/scenes.json --video-h1 h1.mp4 --video-h2 h2.mp4 --calibrations calibrations.json --camera cam4 \
    --candidates ball-candidate.pt --reranker rerank.pt --person yolo11n.pt --out clips/ball.json [--only 1,2]

For each scene the frames from 6 s before to 8 s after (5 per second) go through scripts/ball_finder.py. The answer is the ball path in pixels, in metres (the ball is on the ground in
the calibration, so a ball in the air is off by its height) and a picture of the path on the scene still. A frame without an answer means not found, never no ball (see ball_finder.py).
"""
import argparse
import json
import sys
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from app.pitch_map import apply, fit  # noqa: E402
from ball_finder import BallFinder  # noqa: E402


def frames(video, start, seconds, rate=5):
    cap = cv2.VideoCapture(video)
    out = []
    for k in range(int(seconds * rate)):
        t = start + k / rate
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, image = cap.read()
        if ok:
            out.append((t, image))
    cap.release()
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--scenes', required=True)
    p.add_argument('--video-h1', required=True)
    p.add_argument('--video-h2', required=True)
    p.add_argument('--calibrations', required=True)
    p.add_argument('--camera', default='cam4')
    p.add_argument('--candidates', required=True)
    p.add_argument('--reranker', required=True)
    p.add_argument('--person', default='yolo11n.pt')
    p.add_argument('--out', required=True)
    p.add_argument('--only', help='comma separated scene numbers')
    p.add_argument('--threshold', type=float, help='use the single-threshold linker of ball_path instead of the balanced one')
    args = p.parse_args()
    scenes = json.loads(Path(args.scenes).read_text(encoding='utf-8'))
    fitted = fit(json.loads(Path(args.calibrations).read_text(encoding='utf-8'))[args.camera])
    finder = BallFinder(args.candidates, args.reranker, args.person, args.camera)
    only = {int(x) for x in args.only.split(',')} if args.only else None
    result = {}
    folder = Path(args.scenes).parent
    for number, s in enumerate(scenes, 1):
        if only and number not in only:
            continue
        video = args.video_h1 if s['half'] == '전반' else args.video_h2
        seq = frames(video, s['start'], 14)
        images = [im for _, im in seq]
        path = finder.path(images, threshold=args.threshold)
        h, w = images[0].shape[:2]
        points = []
        for idx, (x, y, prob) in sorted(path.items()):
            m = apply(fitted['H'], x / w, y / h)
            points.append({'t': round(seq[idx][0], 2), 'px': [round(x), round(y)], 'p': round(prob, 2), 'm': [round(m[0], 1), round(m[1], 1)] if m else None})
        result[s['name']] = {'frames': len(images), 'found': len(points), 'points': points}
        # picture: the path on the frame at the scene time
        k = min(range(len(seq)), key=lambda i: abs(seq[i][0] - s['at']))
        still = images[k].copy()
        for a, b in zip(points, points[1:]):
            cv2.line(still, tuple(a['px']), tuple(b['px']), (0, 255, 255), 2)
        for pt in points:
            cv2.circle(still, tuple(pt['px']), 6, (0, 200, 255), 2)
        x0, x1 = 0, w
        crop = still[int(h * 0.36):int(h * 0.72), x0:x1]
        cv2.imwrite(str(folder / (s['name'] + '_ball.jpg')), crop, [cv2.IMWRITE_JPEG_QUALITY, 90])
        print(number, s['name'], f'found in {len(points)} of {len(images)} frames', flush=True)
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding='utf-8')


if __name__ == '__main__':
    main()
