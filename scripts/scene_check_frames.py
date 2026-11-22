"""Frame sheets for checking report scenes with the eye before writing about them.

python scripts/scene_check_frames.py --video h2.mp4 --times 81 187 241 --out-dir checks [--before 3 --after 3 --band 0.40 0.73]

For every time one JPEG: the frames at t-before, t and t+after stacked, cut to the band of the picture where the pitch is (fractions of the height), with the time written on each frame.
No tracking is drawn on purpose: the sheet shows what the camera saw, so a story made by the tracker (for example a long run that was really two players joined by an id switch) can be caught.
Rule of the project since 2026-11-19: no scene text in a report without looking at its sheet.
"""
import argparse
from pathlib import Path

import cv2
import numpy as np


def sheet(cap, t, before, after, band, width):
    rows = []
    for dt in (-before, 0, after):
        cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, (t + dt) * 1000))
        ok, im = cap.read()
        if not ok:
            continue
        h, w = im.shape[:2]
        crop = im[int(h * band[0]):int(h * band[1])]
        crop = cv2.resize(crop, (width, int(crop.shape[0] * width / w)))
        label = f'{t + dt:.0f} s ({"+" if dt >= 0 else ""}{dt:g})'
        cv2.putText(crop, label, (12, 36), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (0, 0, 0), 5, cv2.LINE_AA)
        cv2.putText(crop, label, (12, 36), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (0, 255, 255), 2, cv2.LINE_AA)
        rows.append(crop)
    return np.vstack(rows) if rows else None


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--video', required=True)
    p.add_argument('--times', type=float, nargs='+', required=True)
    p.add_argument('--out-dir', required=True)
    p.add_argument('--before', type=float, default=3.0)
    p.add_argument('--after', type=float, default=3.0)
    p.add_argument('--band', type=float, nargs=2, default=(0.40, 0.73))
    p.add_argument('--width', type=int, default=1600)
    args = p.parse_args()
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        raise SystemExit('cannot open ' + args.video)
    for t in args.times:
        im = sheet(cap, t, args.before, args.after, args.band, args.width)
        if im is None:
            print('no frames at', t)
            continue
        path = out / f'check_{Path(args.video).stem}_{t:06.1f}.jpg'
        cv2.imwrite(str(path), im, [cv2.IMWRITE_JPEG_QUALITY, 88])
        print(path)
    cap.release()


if __name__ == '__main__':
    main()
