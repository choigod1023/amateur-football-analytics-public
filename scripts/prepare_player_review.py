"""Prepare the tracks of a recorded half for the page /players: three pictures of every long track, its place and time, a guess of its position slot and the pairs of tracks that may be one person.

Usage: python scripts/prepare_player_review.py <store> <half key, e.g. h1> <video> <ffmpeg> <calibrations.json> "<half spec>" [--min-rows 40]
   half spec: "<name>|<tracks.json>|<camera>|<direction>|<offset>|<bg a,b,tx,ty>|<schedule>|<goals>"   (the same as scripts/build_match_report.py; the goals are not used)

Writes <store>/players/<half key>/index.json and crops/pictures `<track>_<n>.jpg`. Only tracks with at least --min-rows sightings are listed (5 per second: 40 rows are 8 seconds); shorter ones
are mostly flickers. The position slot is guessed at the middle of the track from the players of its team that were found at that moment (app/position_slots.py), so it follows the shape of
the team then and not an average over the half.

A pair of tracks of the same team is a candidate when the second begins 0 to 4 s after the first ends and no further from its last place than 3 m plus 3 m per second of gap. This is only a
suggestion for a person to answer 'same person?'; nothing is joined without an answer.
"""
import argparse
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from app.position_slots import assign_slots  # noqa: E402
from build_match_report import load_half  # noqa: E402


def cut(ffmpeg, video, second, target):
    subprocess.run([ffmpeg, '-hide_banner', '-loglevel', 'error', '-y', '-ss', f'{second:.3f}', '-i', video, '-frames:v', '1', '-q:v', '2', str(target)], check=True)
    return cv2.imread(str(target))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('store')
    parser.add_argument('half_key')
    parser.add_argument('video')
    parser.add_argument('ffmpeg')
    parser.add_argument('calibrations')
    parser.add_argument('spec')
    parser.add_argument('--min-rows', type=int, default=40)
    parser.add_argument('--again', action='store_true', help='keep the pictures that are already there and only redo the slots and the candidate pairs')
    args = parser.parse_args()
    calibrations = json.loads(Path(args.calibrations).read_text(encoding='utf-8'))
    half = load_half(args.spec, calibrations, 'B')
    fps, offset, direction = half['fps'], half['offset'], half['direction']
    out = Path(args.store) / 'players' / args.half_key
    out.mkdir(parents=True, exist_ok=True)
    scratch = out / '_frame.jpg'
    # the metres of every sighting of every track
    metres = {}
    for frame, teams in half['by_frame'].items():
        for team, rows in teams.items():
            for tid, x, y in rows:
                metres.setdefault(tid, {})[frame] = (x, y)
    team_of = {}
    for tid, rows in half['result']['tracks'].items():
        votes = Counter(r['team'] for r in rows if r['team'] in ('A', 'B'))
        if votes:
            team_of[tid] = votes.most_common(1)[0][0]
    tracks = []
    for tid, rows in half['result']['tracks'].items():
        if len(rows) < args.min_rows or tid not in metres:
            continue
        if tid not in team_of:
            continue
        team = team_of[tid]
        frames = sorted(metres[tid])
        if len(frames) < args.min_rows // 2:
            continue
        sign = direction if team == 'B' else -direction
        mid = frames[len(frames) // 2]
        near = {t: v for t, v in ((t2, metres[t2].get(mid)) for t2 in metres) if v is not None}          # everybody of this team seen at the middle frame
        same_team = [(t2, x, y) for t2, (x, y) in near.items() if team_of.get(t2) == team]
        slot = assign_slots(same_team, sign)
        heights = sorted(r['box'][3] - r['box'][1] for r in rows)
        tracks.append({'id': str(tid), 'team': team, 'first': round(offset + frames[0] / fps, 1), 'last': round(offset + frames[-1] / fps, 1), 'rows': len(rows),
                       'first_pos': [round(metres[tid][frames[0]][0] * sign, 1), round(metres[tid][frames[0]][1] * sign, 1)], 'last_pos': [round(metres[tid][frames[-1]][0] * sign, 1), round(metres[tid][frames[-1]][1] * sign, 1)],
                       'u': round(sum(metres[tid][f][0] * sign for f in frames) / len(frames), 1), 'y': round(sum(metres[tid][f][1] * sign for f in frames) / len(frames), 1),
                       'height': round(heights[len(heights) // 2]), 'slot': slot['slots'].get(tid), 'formation': slot['formation'], '_frames': frames, '_rows': rows})
    tracks.sort(key=lambda t: (t['team'], t['first']))
    old_pictures = {t['id']: t.get('pictures', []) for t in json.loads((out / 'index.json').read_text(encoding='utf-8')).get('tracks', [])} if args.again and (out / 'index.json').is_file() else {}
    # three pictures of every track: a quarter, a half and three quarters of its life
    for number, track in enumerate(tracks, 1):
        if args.again:
            track['pictures'] = old_pictures.get(track['id'], [])
            continue
        rows = {r['frame']: r for r in track['_rows']}
        names = []
        for k, share in enumerate((0.25, 0.5, 0.75)):
            frame = track['_frames'][int(len(track['_frames']) * share)]
            row = rows.get(frame)
            if row is None:
                continue
            image = cut(args.ffmpeg, args.video, offset + frame / fps, scratch)
            x1, y1, x2, y2 = row['box']
            w, h = x2 - x1, y2 - y1
            pad = 0.45 * h
            crop = image[max(0, int(y1 - 0.25 * h)):int(y2 + 0.25 * h), max(0, int(x1 - pad)):int(x2 + pad)]
            if crop.size == 0:
                continue
            scale = max(1.0, 220.0 / crop.shape[0])
            crop = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
            name = f'{track["id"]}_{k}.jpg'
            cv2.imwrite(str(out / name), crop, [cv2.IMWRITE_JPEG_QUALITY, 88])
            names.append(name)
        track['pictures'] = names
        if number % 25 == 0:
            print(f'{number} of {len(tracks)} tracks', flush=True)
    # pairs that may be one person
    candidates = []
    by_team = {'A': [], 'B': []}
    for t in tracks:
        by_team[t['team']].append(t)
    for team, items in by_team.items():
        for a in items:
            a_last = metres[a['id']][a['_frames'][-1]]
            for b in items:
                gap = b['first'] - a['last']
                if b is a or gap < 0 or gap > 4.0:
                    continue
                b_first = metres[b['id']][b['_frames'][0]]
                distance = ((a_last[0] - b_first[0]) ** 2 + (a_last[1] - b_first[1]) ** 2) ** 0.5
                if distance <= 3.0 + 3.0 * gap:
                    candidates.append({'a': a['id'], 'b': b['id'], 'gap': round(gap, 1), 'distance': round(distance, 1)})
    candidates.sort(key=lambda c: c['distance'] + 2 * c['gap'])
    if args.again and (out / 'index.json').is_file():                      # the clips and hints made by scripts/make_pair_clips.py stay with their pairs
        old = {(c['a'], c['b']): c for c in json.loads((out / 'index.json').read_text(encoding='utf-8')).get('candidates', [])}
        for c in candidates:
            for key in ('clip', 'near_others'):
                if key in old.get((c['a'], c['b']), {}):
                    c[key] = old[(c['a'], c['b'])][key]
    index = {'name': half['name'], 'direction': direction, 'offset': offset, 'fps': fps,
             'tracks': [{k: v for k, v in t.items() if not k.startswith('_')} for t in tracks], 'candidates': candidates}
    (out / 'index.json').write_text(json.dumps(index, ensure_ascii=False), encoding='utf-8')
    scratch.unlink(missing_ok=True)
    print(f'wrote {len(tracks)} tracks and {len(candidates)} candidate pairs to {out}')


if __name__ == '__main__':
    main()
