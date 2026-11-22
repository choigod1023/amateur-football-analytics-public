"""Build review candidates for kickoffs and goals from a 1 fps person scan, plus short silent clips.

Image-space heuristics only: a very dark person (the referee in a long coat) standing inside the centre
circle for several seconds, and both colour groups on opposite sides of the halfway line. The centre
circle is read for camera setting cam1 and moved to other settings with the per-frame background
transform. Candidates are suggestions for a person to confirm; nothing here is a detection result.
"""
import argparse
import json
import math
import subprocess
import time
from pathlib import Path

import numpy as np

CX, CY, RX, RY = 1008.0, 828.0, 149.0, 23.0   # centre circle in cam1 pixels, read by eye from one frame (approximate)


def line_x(y):
    return 994.0 + (y - 780.0) * 0.288


def load_motion(path):
    """Rows [index, clip_s, scale, tx, ty, inliers] mapping frame pixels to frame 1 pixels, about every 30 s."""
    rows = [r for r in json.loads(Path(path).read_text(encoding='utf-8')) if r[2] is not None and r[5] >= 40]
    return sorted(rows, key=lambda r: r[1])


def transform_at(rows, t):
    if not rows:
        return None
    row = min(rows, key=lambda r: abs(r[1] - t))
    return (row[2], row[3], row[4]) if abs(row[1] - t) <= 45 else None


def build(scan_path, motion_path, min_run, merge_window):
    scan = [json.loads(line) for line in Path(scan_path).read_text(encoding='utf-8').splitlines() if line.strip()]
    motion = load_motion(motion_path)
    total = len(scan)
    near = np.zeros(total, bool)
    formation = np.zeros(total)
    for t in range(total):
        tr = transform_at(motion, t)
        if tr is None:
            continue
        s, tx, ty = tr
        cx, cy, rx, ry = (CX - tx) / s, (CY - ty) / s, RX / s, RY / s
        dark_dist, players = None, []
        for x1, y1, x2, y2, _, neon, dark, _p in scan[t]['people']:
            h = y2 - y1
            # the background shift moves the pitch band as well; spectators stand in front of the fence
            if h >= 100 or h < 24 or y2 < 0.715 * 1080 - ty or y2 >= 0.84 * 1080:
                continue
            players.append(((x1 + x2) / 2, y2, neon))
            if dark >= 0.45 and neon < 0.05:
                d = math.hypot(((x1 + x2) / 2 - cx) / rx, (y2 - cy) / ry)
                dark_dist = d if dark_dist is None else min(dark_dist, d)
        near[t] = dark_dist is not None and dark_dist < 1.3
        if len(players) >= 8:
            a = [x - (line_x((y + ty) / 1) + (-tx)) for x, y, n in players if n >= 0.14]
            b = [x - (line_x((y + ty) / 1) + (-tx)) for x, y, n in players if n < 0.14]
            if len(a) >= 3 and len(b) >= 3:
                fa = max(np.mean(np.array(a) > 0), np.mean(np.array(a) < 0))
                fb = max(np.mean(np.array(b) > 0), np.mean(np.array(b) < 0))
                opposite = np.sign(np.median(a)) != np.sign(np.median(b))
                centre = np.mean([abs((x - cx) / rx) < 2.6 for x, y, n in players])
                formation[t] = (1.0 if opposite else 0.0) * min(fa, fb) * float(centre)
    runs, t = [], 0
    while t < total:
        if near[t]:
            s0 = t
            while t < total and near[t]:
                t += 1
            if t - s0 >= min_run:
                runs.append((s0, t - 1))
        else:
            t += 1
    items = []
    for s0, e0 in runs:
        peak = float(formation[s0:e0 + 1].max())
        items.append({'t': float(s0 + 2), 'run': [s0, e0], 'formation': round(peak, 2),
                      'reasons': [f'심판 후보(아주 어두운 옷)가 센터서클 안에 {e0 - s0 + 1}초 머묾'] +
                                 ([f'두 팀이 센터 양쪽에 나뉜 배치(점수 {peak:.2f})'] if peak >= 0.35 else [])})
    # merge candidates closer than the window, keep the strongest
    items.sort(key=lambda i: i['t'])
    merged = []
    for item in items:
        if merged and item['t'] - merged[-1]['t'] < merge_window:
            prev = merged[-1]
            if (item['run'][1] - item['run'][0], item['formation']) > (prev['run'][1] - prev['run'][0], prev['formation']):
                merged[-1] = item
        else:
            merged.append(item)
    for i, item in enumerate(merged, 1):
        item['id'] = f'c{i:03d}'
        item['score'] = round(min(1.0, (item['run'][1] - item['run'][0] + 1) / 15) * 0.6 + item['formation'] * 0.4, 3)
    return merged, total


def make_media(clip, ffmpeg, item, media_dir, before, after, motion):
    t0 = max(0.0, item['t'] - before)
    tr = transform_at(motion, item['t']) or (1.0, 0.0, 0.0)
    y0 = int(min(max(0, (CY - tr[2]) / tr[0] - 280), 1080 - 460))
    item['start'], item['end'] = round(t0, 1), round(item['t'] + after, 1)
    base = [str(ffmpeg), '-hide_banner', '-loglevel', 'error', '-y']
    out = media_dir / (item['id'] + '.mp4')
    subprocess.run(base + ['-ss', f'{t0}', '-t', f'{item["t"] - t0 + after}', '-i', str(clip), '-an',
                           '-vf', f'crop=1920:460:0:{y0},scale=1280:-2,fps=15', '-c:v', 'libx264', '-preset', 'veryfast',
                           '-crf', '30', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(out)], check=True)
    subprocess.run(base + ['-ss', f'{item["t"]}', '-i', str(clip), '-frames:v', '1',
                           '-vf', f'crop=1920:460:0:{y0},scale=640:-2', '-q:v', '4', str(media_dir / (item['id'] + '.jpg'))], check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--scan', required=True)
    ap.add_argument('--motion', required=True)
    ap.add_argument('--clip', required=True)
    ap.add_argument('--ffmpeg', required=True)
    ap.add_argument('--store', required=True, help='dedicated review store directory')
    ap.add_argument('--min-run', type=int, default=4)
    ap.add_argument('--merge-window', type=int, default=20)
    ap.add_argument('--before', type=int, default=30)
    ap.add_argument('--after', type=int, default=8)
    ap.add_argument('--limit', type=int, default=0)
    a = ap.parse_args()
    events = Path(a.store) / 'events'
    media = events / 'media'
    if (events / 'candidates.json').exists():
        raise SystemExit('candidates.json already exists; refusing to overwrite')
    media.mkdir(parents=True, exist_ok=True)
    items, total = build(a.scan, a.motion, a.min_run, a.merge_window)
    if a.limit:
        items = items[:a.limit]
    motion = load_motion(a.motion)
    started = time.time()
    for item in items:
        make_media(a.clip, a.ffmpeg, item, media, a.before, a.after, motion)
    (events / 'candidates.json').write_text(json.dumps(
        {'generated': time.strftime('%Y-%m-%d %H:%M:%S'), 'clip': Path(a.clip).name,
         'time_basis': 'seconds from the start of the match clip (17 minutes into the merged recording)',
         'method': 'referee-like person inside the centre circle for several seconds; opposite-side formation score (heuristic, unverified)',
         'seconds_scanned': total, 'items': items}, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f'{len(items)} candidates, media written in {time.time() - started:.0f}s -> {events}')


if __name__ == '__main__':
    main()
