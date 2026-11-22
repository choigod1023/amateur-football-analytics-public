"""Photos of moments in which our team attacked narrowly, with the five lanes and the tracked players drawn on the photo (to check the position numbers with the eye).

python scripts/width_photos.py --h1 positions_h1.jsonl --h2 positions_h2.jsonl --h2-end 1405 --video-h1 h1.mp4 --video-h2 h2.mp4 --calibrations calibrations.json --out-dir photos [--per-half 2]

A moment: the team centre is in the opponent's half, at least eight outfield players are seen and the team width (10th to 90th percentile of the sideways positions) is among the narrowest 20 % of such
moments; moments of one half are at least 60 s apart. The lanes (dashed) are the five lanes of the report, the wide lanes are shaded. Our tracked players are blue, the opponent's orange. The team's view and the picture's view
differ by the attack direction of the half, which is turned back here.
"""
import argparse
import json
import statistics
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_detailed_report as R  # noqa: E402
from app.pitch_map import fit  # noqa: E402


def moments(data):
    rows = []
    for t in sorted(data):
        pts = R.outfield(data[t]['ours'])
        if len(pts) < 8 or statistics.mean(p[1] for p in pts) <= 8:
            continue
        ys = sorted(p[2] for p in pts)
        k = len(ys)
        rows.append((ys[int(0.9 * (k - 1))] - ys[int(0.1 * (k - 1))], t, statistics.mean(p[1] for p in pts)))
    return rows


def pick(rows, count, gap=60):
    if not rows:
        return []
    limit = np.percentile([r[0] for r in rows], 20)
    chosen = []
    for w, t, c in sorted(rows):
        if w > limit:
            break
        if all(abs(t - x[1]) >= gap for x in chosen):
            chosen.append((w, t, c))
        if len(chosen) == count:
            break
    return sorted(chosen, key=lambda x: x[1])


def project(inv, u, v, direction, size):
    x, y = u * direction, v * direction
    p = inv @ np.array([x, y, 1.0])
    return int(p[0] / p[2] * size[0]), int(p[1] / p[2] * size[1])


def render(video, t, row, fitted, direction):
    cap = cv2.VideoCapture(video)
    cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
    ok, im = cap.read()
    cap.release()
    if not ok:
        return None
    h, w = im.shape[:2]
    inv = np.linalg.inv(fitted['H'])
    over = im.copy()
    half_l, half_w = R.L / 2, R.W / 2
    # shade the two wide lanes in the opponent's half
    for lo, hi in ((-half_w, R.LANE_EDGES[0]), (R.LANE_EDGES[3], half_w)):
        quad = np.array([project(inv, a, b, direction, (w, h)) for a, b in ((0, lo), (half_l, lo), (half_l, hi), (0, hi))], np.int32)
        cv2.fillConvexPoly(over, quad, (0, 225, 255))
    im = cv2.addWeighted(over, 0.22, im, 0.78, 0)
    for e in R.LANE_EDGES:
        a, b = project(inv, 0, e, direction, (w, h)), project(inv, half_l, e, direction, (w, h))
        cv2.line(im, a, b, (255, 255, 255), 1, cv2.LINE_AA)
    for key, colour in (('theirs', (107, 138, 255)), ('ours', (255, 184, 109))):
        for _, u, v in row[key]:
            x, y = project(inv, u, v, direction, (w, h))
            cv2.circle(im, (x, y), 9, colour, 2, cv2.LINE_AA)
    return im


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--h1', required=True)
    p.add_argument('--h2', required=True)
    p.add_argument('--h2-end', type=float)
    p.add_argument('--video-h1', required=True)
    p.add_argument('--video-h2', required=True)
    p.add_argument('--calibrations', required=True)
    p.add_argument('--camera', default='cam4')
    p.add_argument('--out-dir', required=True)
    p.add_argument('--per-half', type=int, default=2)
    args = p.parse_args()
    fitted = fit(json.loads(Path(args.calibrations).read_text(encoding='utf-8'))[args.camera])
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    info = []
    for half, positions, video, end in (('전반', args.h1, args.video_h1, None), ('후반', args.h2, args.video_h2, args.h2_end)):
        direction = int(json.loads(Path(positions).read_text(encoding='utf-8').splitlines()[0])['direction'])
        data = R.read(positions, end=end)
        for width, t, centre in pick(moments(data), args.per_half):
            im = render(video, t, data[t], fitted, direction)
            if im is None:
                continue
            name = f'width_{"h1" if half == "전반" else "h2"}_{t:04d}.jpg'
            cv2.imwrite(str(out / name), im[int(im.shape[0] * 0.33):int(im.shape[0] * 0.75)], [cv2.IMWRITE_JPEG_QUALITY, 90])
            info.append({'half': half, 't': t, 'width': round(width, 1), 'file': name, 'minute': (t - min(data)) / 60.0})
            print(half, t, f'width {width:.1f} m', name, flush=True)
    (out / 'width_photos.json').write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding='utf-8')


if __name__ == '__main__':
    main()
