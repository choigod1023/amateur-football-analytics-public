"""Better pictures of the tracks for the page /players: the sharpest moments instead of fixed times, and one picture that fuses several moments.

Usage: python scripts/enhance_player_pictures.py <store> <half key> <video> <ffmpeg> <tracks.json> [--team B] [--sample 16]

What it does, and what it cannot do:
  * The recording shows a player about 30 pixels tall. No processing adds detail that the recording does not hold; this script only chooses better moments and removes noise.
  * For every track of the team it looks at up to --sample moments spread over its life (only moments that fall on a whole second of the video, so that the frame and the box agree), measures
    the sharpness of the player in each (variance of the Laplacian of the box scaled to a common height, times the height of the box) and keeps the three best that are at least 5 s apart:
    they become `<track>_0.jpg` to `<track>_2.jpg`. (A fusion of several moments by the median was tried and dropped: a running person is not at the same place in two moments, so the
    result is a ghost.)
  * Every picture is denoised a little at the original size, enlarged with Lanczos to 260 pixels and sharpened mildly (unsharp mask). No machine-learning enlargement is used: such models invent
    plausible detail (also digits), which must not decide who a person is.
The index file gets the new `pictures` and `sharpness` (the Laplacian variance of the three pictures before and after) of every track it changed; the old pictures are overwritten.
"""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np


def sharpness(patch):
    gray = cv2.cvtColor(cv2.resize(patch, (48, 96), interpolation=cv2.INTER_CUBIC), cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def finish(patch, height=260):
    """Denoise a little at the original size, enlarge to `height` with Lanczos and sharpen mildly."""
    small = cv2.fastNlMeansDenoisingColored(patch, None, 4, 4, 5, 15)
    scale = height / small.shape[0]
    big = cv2.resize(small, None, fx=scale, fy=scale, interpolation=cv2.INTER_LANCZOS4)
    blur = cv2.GaussianBlur(big, (0, 0), 1.6)
    return np.clip(cv2.addWeighted(big, 1.6, blur, -0.6, 0), 0, 255).astype(np.uint8)


def cut(image, box, pad_x=0.18, pad_y=0.08):
    x1, y1, x2, y2 = box
    w, h = x2 - x1, y2 - y1
    left, right = int(max(0, x1 - pad_x * w)), int(min(image.shape[1], x2 + pad_x * w))
    top, bottom = int(max(0, y1 - pad_y * h)), int(min(image.shape[0], y2 + pad_y * h))
    patch = image[top:bottom, left:right].copy()
    dim = np.full(patch.shape[:2], 0.45, np.float32)                       # everything outside the box of the person is dimmed: the picture is of him alone
    dim[int(y1 - top):int(y2 - top) + 1, int(x1 - left):int(x2 - left) + 1] = 1.0
    return np.clip(patch * dim[..., None], 0, 255).astype(np.uint8)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('store')
    parser.add_argument('half_key')
    parser.add_argument('video')
    parser.add_argument('ffmpeg')
    parser.add_argument('tracks')
    parser.add_argument('--team', default='B')
    parser.add_argument('--sample', type=int, default=16)
    args = parser.parse_args()
    folder = Path(args.store) / 'players' / args.half_key
    index = json.loads((folder / 'index.json').read_text(encoding='utf-8'))
    result = json.loads(Path(args.tracks).read_text(encoding='utf-8'))
    fps, offset = float(result['fps']), float(result['first_second'])
    step = int(round(fps))                                                    # rows on a whole second of the video
    wanted = [t for t in index['tracks'] if t['team'] == args.team]
    last_second = max(int((result['frames'] / fps)) + 1, 1)
    frames = folder / '_frames'
    shutil.rmtree(frames, ignore_errors=True)
    frames.mkdir()
    print('cutting one picture per second of the half ...', flush=True)
    subprocess.run([args.ffmpeg, '-hide_banner', '-loglevel', 'error', '-y', '-ss', f'{offset:.3f}', '-t', f'{last_second:.3f}', '-i', args.video, '-vf', 'fps=1', '-q:v', '2', str(frames / 'f_%05d.jpg')], check=True)
    cache = {}

    def frame_at(k):
        if k not in cache:
            if len(cache) > 60:
                cache.clear()
            cache[k] = cv2.imread(str(frames / f'f_{k + 1:05d}.jpg'))
        return cache[k]
    others = {}                                                                     # frame -> [(track id, box)] of everybody tracked, for the moments on a whole second
    for tid, rows in result['tracks'].items():
        for r in rows:
            if r['frame'] % step == 0:
                others.setdefault(r['frame'], []).append((tid, r['box']))

    def crowded(track_id, frame, box):
        """The largest share of the box of this track that another person's box covers at this moment."""
        worst = 0.0
        area = max(1.0, (box[2] - box[0]) * (box[3] - box[1]))
        for tid, other in others.get(frame, []):
            if tid == track_id:
                continue
            w = min(box[2], other[2]) - max(box[0], other[0])
            h = min(box[3], other[3]) - max(box[1], other[1])
            if w > 0 and h > 0:
                worst = max(worst, w * h / area)
        return worst
    changed = 0
    for number, track in enumerate(wanted, 1):
        rows = [r for r in result['tracks'].get(track['id'], []) if r['frame'] % step == 0 and r['team'] == args.team and not r.get('interpolated')]       # an interpolated box is a guess, the person may stand elsewhere
        if len(rows) < 3:
            continue
        picks = [rows[int(i * (len(rows) - 1) / max(1, args.sample - 1))] for i in range(min(args.sample, len(rows)))]
        scored = []
        for row in picks:
            image = frame_at(row['frame'] // step)
            if image is None:
                continue
            x1, y1, x2, y2 = row['box']
            if x1 < 4 or y1 < 4 or x2 > image.shape[1] - 4 or y2 > image.shape[0] - 4 or y2 - y1 < 12:
                continue
            tight = image[int(y1):int(y2), int(x1):int(x2)]
            if tight.size == 0:
                continue
            overlap = crowded(track['id'], row['frame'], row['box'])
            scored.append((sharpness(tight) * (y2 - y1) * (1.0 if overlap < 0.1 else 0.3 if overlap < 0.3 else 0.05), sharpness(tight), row['frame'], row['box']))
        if len(scored) < 3:
            continue
        scored.sort(key=lambda s: -s[0])
        chosen = []
        for item in scored:
            if all(abs(item[2] - c[2]) >= 5 * fps for c in chosen):
                chosen.append(item)
            if len(chosen) == 3:
                break
        if len(chosen) < 3:
            chosen = scored[:3]
        out = []
        for k, item in enumerate(chosen[:3]):
            patch = cut(frame_at(item[2] // step), item[3])
            cv2.imwrite(str(folder / f'{track["id"]}_{k}.jpg'), finish(patch), [cv2.IMWRITE_JPEG_QUALITY, 90])
            out.append(f'{track["id"]}_{k}.jpg')
        track['pictures'] = out
        track['sharpness'] = [round(c[1], 1) for c in chosen[:3]]
        changed += 1
        if number % 25 == 0:
            print(f'{number} of {len(wanted)} tracks', flush=True)
    (folder / 'index.json').write_text(json.dumps(index, ensure_ascii=False), encoding='utf-8')
    shutil.rmtree(frames, ignore_errors=True)
    print(f'{changed} of {len(wanted)} tracks of team {args.team} got new pictures in {folder}')


if __name__ == '__main__':
    main()
