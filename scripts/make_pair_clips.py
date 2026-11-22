"""A short enlarged clip for every pair of tracks that may be one person, so that a person can see the hand-over and answer 'same person?'.

Usage: python scripts/make_pair_clips.py <store> <half key, e.g. h1> <video> <ffmpeg> <calibrations.json> "<half spec>"
   half spec: the same as scripts/prepare_player_review.py

For every candidate in <store>/players/<half key>/index.json a clip `pair_<a>_<b>.mp4` is cut from the recording (from 1.5 s before the first track ends to 1.5 s after the second begins, 5 pictures
per second), cropped around the place of the hand-over and enlarged. The first track is boxed in orange while it is followed, the second in sky blue from where it begins, all other tracked players of the
frame in thin grey so that a person sees who else stands there. The candidate gets `clip` (the file name) and `near_others` (how many other players of the same team stood within 5 m of the place where the
second track begins: with 0 the hand-over is hard to confuse, with 2 or more it is not). The index file is changed in place.
"""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_match_report import load_half  # noqa: E402

ORANGE, SKY, GREY = (60, 160, 255), (255, 200, 90), (170, 170, 170)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('store')
    parser.add_argument('half_key')
    parser.add_argument('video')
    parser.add_argument('ffmpeg')
    parser.add_argument('calibrations')
    parser.add_argument('spec')
    args = parser.parse_args()
    folder = Path(args.store) / 'players' / args.half_key
    index = json.loads((folder / 'index.json').read_text(encoding='utf-8'))
    half = load_half(args.spec, json.loads(Path(args.calibrations).read_text(encoding='utf-8')), 'B')
    fps, offset = half['fps'], half['offset']
    tracks = half['result']['tracks']
    team_of = {t['id']: t['team'] for t in index['tracks']}
    metres = {}
    for frame, teams in half['by_frame'].items():
        for team, rows in teams.items():
            for tid, x, y in rows:
                metres.setdefault(tid, {})[frame] = (x, y)
    boxes = {}                                                                    # frame -> {track: box}
    work = folder / '_pair'
    done = 0
    for c in index['candidates']:
        by_id = {t['id']: t for t in index['tracks']}
        a_last, b_first = int(round((by_id[c['a']]['last'] - offset) * fps)), int(round((by_id[c['b']]['first'] - offset) * fps))      # the times of the index are those of the pitch positions
        first, last = max(0, min(a_last, b_first) - int(1.5 * fps)), max(a_last, b_first) + int(1.5 * fps)
        by_a = {r['frame']: r['box'] for r in tracks[c['a']]}
        by_b = {r['frame']: r['box'] for r in tracks[c['b']]}
        # the others of the same team around the place of the hand-over
        spot = metres.get(c['b'], {}).get(b_first)
        near = 0
        if spot:
            for tid, positions in metres.items():
                if tid in (c['a'], c['b']) or team_of.get(tid) != team_of.get(c['a']):
                    continue
                p = positions.get(b_first)
                if p and ((p[0] - spot[0]) ** 2 + (p[1] - spot[1]) ** 2) ** 0.5 <= 5.0:
                    near += 1
        c['near_others'] = near
        # the window of the picture: the boxes of both tracks over the clip and a margin
        xs, ys = [], []
        for f in range(first, last + 1):
            for box in (by_a.get(f), by_b.get(f)):
                if box:
                    if (box is by_a.get(f) and f <= a_last + 2) or (box is by_b.get(f) and f >= b_first - 2):
                        xs += [box[0], box[2]]
                        ys += [box[1], box[3]]
        if not xs or last <= first:
            continue
        pad_x, pad_y = 140, 90
        x0, x1, y0, y1 = min(xs) - pad_x, max(xs) + pad_x, min(ys) - pad_y, max(ys) + pad_y
        width = max(x1 - x0, (y1 - y0) * 16 / 9, 360)
        height = width * 9 / 16
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        shutil.rmtree(work, ignore_errors=True)
        work.mkdir(parents=True)
        start = offset + first / fps
        seconds = (last - first) / fps + 0.2
        subprocess.run([args.ffmpeg, '-hide_banner', '-loglevel', 'error', '-y', '-ss', f'{start:.3f}', '-t', f'{seconds:.3f}', '-i', args.video, '-vf', 'fps=5', '-q:v', '2', str(work / 'f_%03d.jpg')], check=True)
        pictures = sorted(work.glob('f_*.jpg'))
        if not pictures:
            print('no pictures for', c['a'], c['b'], 'start', round(start, 1), 'seconds', round(seconds, 1), flush=True)
            continue
        for number, path in enumerate(pictures):
            frame = first + number
            image = cv2.imread(str(path))
            left, top = int(min(max(0, cx - width / 2), image.shape[1] - width)), int(min(max(0, cy - height / 2), image.shape[0] - height))
            scale = 960 / width
            crop = cv2.resize(image[top:top + int(height), left:left + int(width)], (960, int(round(height * scale / 2)) * 2), interpolation=cv2.INTER_CUBIC)      # an even size, which H.264 needs
            for tid, rows in tracks.items():
                if tid in (c['a'], c['b']) or team_of.get(tid) is None:
                    continue
                row = next((r for r in rows if r['frame'] == frame), None)
                if row:
                    b = row['box']
                    cv2.rectangle(crop, (int((b[0] - left) * scale), int((b[1] - top) * scale)), (int((b[2] - left) * scale), int((b[3] - top) * scale)), GREY, 1, cv2.LINE_AA)
            for box, colour, active in ((by_a.get(frame), ORANGE, frame <= a_last), (by_b.get(frame), SKY, frame >= b_first)):
                if box and active:
                    cv2.rectangle(crop, (int((box[0] - left) * scale) - 3, int((box[1] - top) * scale) - 3), (int((box[2] - left) * scale) + 3, int((box[3] - top) * scale) + 3), colour, 3, cv2.LINE_AA)
            cv2.imwrite(str(work / f'o_{number:03d}.jpg'), crop, [cv2.IMWRITE_JPEG_QUALITY, 90])
        name = f'pair_{c["a"]}_{c["b"]}.mp4'
        if not list(work.glob('o_*.jpg')):
            print('no output pictures for', c['a'], c['b'], flush=True)
            continue
        subprocess.run([args.ffmpeg, '-hide_banner', '-loglevel', 'error', '-y', '-framerate', '3', '-i', str(work / 'o_%03d.jpg'), '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '22', str(folder / name)], check=True)
        c['clip'] = name
        done += 1
    shutil.rmtree(work, ignore_errors=True)
    (folder / 'index.json').write_text(json.dumps(index, ensure_ascii=False), encoding='utf-8')
    print(f'{done} clips for {len(index["candidates"])} candidate pairs in {folder}')


if __name__ == '__main__':
    main()
