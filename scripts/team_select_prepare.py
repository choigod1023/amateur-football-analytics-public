"""Make the pictures for the team choice page (/team-select) from the first seconds of a source.

python scripts/team_select_prepare.py <source> --store <review store folder> [--start 64 --seconds 10] [--calibrations calibrations.json --camera cam1 [--reference-bg a b tx ty]]
                                      [--tile-camera cam1|cam3] [--detector yolo11n.pt] [--device 0|cpu]

It detects the people of about one frame per second (the tile detector of the live run), keeps boxes at least 40 pixels tall (on the pitch when a calibration is given), splits their shirt colours
into two team groups (app/team_color_profile.py) and writes to <store>/service/team_select/: candidates.json and three pictures of each group (g0_0.jpg ...). The coach then opens /team-select, looks at the
pictures and says once which group is the own team; the page writes <store>/service/team_profile.json. No profile is written here and nothing is decided by this script.
The address of a stream is never written. The detector runs on the GPU like the live run; use --device cpu while another job needs the GPU.
2026-11-25 (colour pick): --groups 5 offers 2 to 5 colour groups (app/team_color_profile.split_teams_multi; the coach then picks the own AND the opponent group,
the rest is dropped), and --retakes 2 reads the stream again by itself (at most two more samples) when no pair of groups is clear enough for the live run's
bib reader (app/colour_pick.sample_score); the clearest sample is kept. Without the two options the script works and writes exactly as before.
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

CROPS_PER_GROUP = 3
MIN_CROP_HEIGHT = 40


def pick_crops(entries, count=CROPS_PER_GROUP):
    """entries: [(height, second, crop)]. The tallest crops from different seconds."""
    chosen, used = [], set()
    for height, second, crop in sorted(entries, key=lambda e: -e[0]):
        if round(second) in used:
            continue
        chosen.append(crop)
        used.add(round(second))
        if len(chosen) == count:
            break
    if len(chosen) < count:                                        # fewer distinct seconds than crops: fill with the next tallest
        for height, second, crop in sorted(entries, key=lambda e: -e[0]):
            if len(chosen) == count:
                break
            if not any(crop is c for c in chosen):
                chosen.append(crop)
    return chosen


def write_progress(path, value):
    """<team_select>/progress.json while a sample is read: which sample (1..of), so that /setup can show "(2/3)" and the time left. Removed at the end."""
    try:
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(value), encoding='utf-8')
        temporary.replace(path)
    except OSError:
        pass


def remove_progress(path):
    try:
        path.unlink()
    except OSError:
        pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('source')
    parser.add_argument('--store', required=True)
    parser.add_argument('--start', type=float, default=0.0)
    parser.add_argument('--seconds', type=float, default=10.0)
    parser.add_argument('--calibrations')
    parser.add_argument('--camera', default='cam1')
    parser.add_argument('--reference-bg', type=float, nargs=4)
    parser.add_argument('--pitch-margin', type=float, help='metres outside the lines that still count as the pitch (default 2.0)')
    parser.add_argument('--tile-camera', choices=('cam1', 'cam3', 'cam4'))
    parser.add_argument('--detector', default='yolo11n.pt')
    parser.add_argument('--confidence', type=float, default=0.10)
    parser.add_argument('--device', default='0')
    parser.add_argument('--groups', type=int, default=2, help='largest number of colour groups offered (2 = the old two-group split; /setup passes 5)')
    parser.add_argument('--groups-when', choices=('last', 'first'), default='last',
                        help="with --retakes: 'last' = two groups and retakes first, more groups only when every sample is weak; 'first' = more groups at once")
    parser.add_argument('--retakes', type=int, default=0, help='samples taken again by themselves when no pair of groups is clear (/setup passes 2: three samples at most)')
    args = parser.parse_args()
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    import cv2
    from app.colour_pick import sample_score
    from app.team_color_profile import colour_name, shirt_colour, split_teams, split_teams_multi
    from startup_check import calibration_check, public_source, read_source
    source = int(args.source) if args.source.isdigit() else args.source
    is_file = isinstance(source, str) and Path(source).exists()
    out = Path(args.store) / 'service' / 'team_select'
    out.mkdir(parents=True, exist_ok=True)
    progress_path = out / 'progress.json'
    attempts_total = 1 + max(0, args.retakes)
    began = time.time()
    detector = tile_detector = feet_to_metres = None
    samples = []                     # [(score, colours, entries, split, attempt record)]
    for attempt in range(1, attempts_total + 1):
        attempt_began = time.time()
        write_progress(progress_path, {'attempt': attempt, 'of': attempts_total, 'began': began, 'attempt_began': attempt_began,
                                       'first_seconds': samples[0][4]['seconds'] if samples else None, 'seconds': args.seconds})
        start = args.start + (attempt - 1) * args.seconds if is_file else args.start      # a file: the next stretch, as a stream would show it
        kept, _, _, _, _ = read_source(cv2, source, start, args.seconds, is_file)
        if not kept:
            if samples:
                break
            remove_progress(progress_path)
            raise SystemExit('The source could not be read.')
        if detector is None:
            from ultralytics import YOLO
            import track_review_clip as tile_detector
            from app.pitch_map import feet_to_metres
            detector = YOLO(args.detector)
        device = 'cpu' if args.device == 'cpu' else int(args.device)
        tile_camera = args.tile_camera or ('cam3' if args.camera == 'cam2' else args.camera)
        fitted, shift = None, (0.0, 0.0)
        if args.calibrations:
            _, fitted, shift = calibration_check(cv2, args.calibrations, args.camera, kept[len(kept) // 2][1])
        colours, entries = [], []
        for t, frame in kept:
            height, width = frame.shape[:2]
            for d in tile_detector.detect(detector, frame, tile_camera, device, args.confidence):
                if (d[3] - d[1]) >= 90 or d[3] >= 0.84 * height:                  # very large or very low boxes are the stands
                    continue
                if fitted is not None and feet_to_metres(fitted, d, width, height, shift, tuple(args.reference_bg) if args.reference_bg else None, **({'margin': args.pitch_margin} if args.pitch_margin is not None else {})) is None:
                    continue                                                      # outside the pitch and its margin
                colour = shirt_colour(frame, d)
                if colour is None:
                    continue
                colours.append(colour)
                entries.append((d[3] - d[1], t, frame[max(0, int(d[1])):int(d[3]), max(0, int(d[0])):int(d[2])].copy()))
        many_now = args.groups > 2 and (args.groups_when == 'first' or attempts_total == 1)
        split = split_teams_multi(colours, max_groups=args.groups) if many_now else split_teams(colours)
        score = sample_score(split) if split.get('ok') else {'on': False, 'clarity': None, 'best': None}
        record = {'attempt': attempt, 'start': start, 'people_read': len(colours), 'groups': len(split.get('groups') or []), 'ok': bool(split.get('ok')),
                  'on': score['on'], 'clarity': score['clarity'], 'seconds': round(time.time() - attempt_began, 1)}
        samples.append((score, colours, entries, split, record))
        print(f'sample {attempt}/{attempts_total}: {len(colours)} people, {record["groups"]} groups, clear pair {score["on"]} (clarity {score["clarity"]})', flush=True)
        if score['on'] or attempt == attempts_total:
            break
    if args.groups > 2 and args.groups_when == 'last' and attempts_total > 1 and not any(s[0]['on'] for s in samples):
        # every sample was weak with two groups: only now each sample is split into more groups (11-20 test, 2026-11-25: offering more groups
        # on a first weak sample gave a narrow bright own group and fewer own players than the retake, work/match-1125/colour-pick/results.md)
        again = []
        for s in samples:
            split = split_teams_multi(s[1], max_groups=args.groups)
            score = sample_score(split) if split.get('ok') else {'on': False, 'clarity': None, 'best': None}
            again.append((score, s[1], s[2], split, {**s[4], 'groups': len(split.get('groups') or []), 'on': score['on'], 'clarity': score['clarity'], 'more_groups': True}))
        samples = again
    chosen = max(range(len(samples)), key=lambda i: (samples[i][3].get('ok', False), samples[i][0]['clarity'] if samples[i][0]['clarity'] is not None else -1.0, -i))
    score, colours, entries, split, _ = samples[chosen]
    for old in out.glob('g*_*.jpg'):
        old.unlink()
    groups = []
    for index, group in enumerate(split['groups']):
        crops = pick_crops([entries[m] for m in group['members']])
        names = []
        for k, crop in enumerate(crops):
            name = f'g{index}_{k}.jpg'
            cv2.imwrite(str(out / name), crop)
            names.append(name)
        groups.append({'id': index, 'people': len(group['members']), 'colour_text': colour_name(group['centre']), 'images': names})
    record = {'created': time.strftime('%Y-%m-%dT%H:%M:%S'), 'source': public_source(source), 'start': args.start, 'seconds': args.seconds, 'people_read': len(colours),
              'ok': split['ok'], 'weak': split['weak'], 'reason': split['reason'], 'separation': split['separation'], 'groups': groups,
              'others_people': sum(len(g['members']) for g in split['others']),
              'split': {'groups': [{'centre': g['centre'], 'scale': g['scale'], 'members': g['members']} for g in split['groups']],
                        'others': [{'centre': g['centre'], 'members': g['members']} for g in split['others']], 'separation': split['separation'], 'ok': split['ok'], 'weak': split['weak']}}
    if args.groups > 2 or args.retakes:                                # the old command writes the old file, key for key
        record.update(start=samples[chosen][4]['start'], clear=bool(score['on']), clarity=score['clarity'], best_pair=score['best'],
                      attempts=[s[4] for s in samples], attempt_used=chosen + 1, total_seconds=round(time.time() - began, 1))
    (out / 'candidates.json').write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding='utf-8')
    remove_progress(progress_path)
    print(f'{len(colours)} people read in {len(kept)} frames; ' + (f'groups: {[(g["people"], g["colour_text"]) for g in groups]}, separation {split["separation"]}' if groups else split['reason']))
    print('Open /team-select on the review server and choose the own team.')


if __name__ == '__main__':
    main()
