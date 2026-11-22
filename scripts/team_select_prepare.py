"""Make the pictures for the team choice page (/team-select) from the first seconds of a source.

python scripts/team_select_prepare.py <source> --store <review store folder> [--start 64 --seconds 10] [--calibrations calibrations.json --camera cam1 [--reference-bg a b tx ty]]
                                      [--tile-camera cam1|cam3] [--detector yolo11n.pt] [--device 0|cpu]

It detects the people of about one frame per second (the tile detector of the live run), keeps boxes at least 40 pixels tall (on the pitch when a calibration is given), splits their shirt colours
into two team groups (app/team_color_profile.py) and writes to <store>/service/team_select/: candidates.json and three pictures of each group (g0_0.jpg ...). The coach then opens /team-select, looks at the
pictures and says once which group is the own team; the page writes <store>/service/team_profile.json. No profile is written here and nothing is decided by this script.
The address of a stream is never written. The detector runs on the GPU like the live run; use --device cpu while another job needs the GPU.
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
    args = parser.parse_args()
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    import cv2
    from app.team_color_profile import colour_name, shirt_colour, split_teams
    from startup_check import calibration_check, public_source, read_source
    source = int(args.source) if args.source.isdigit() else args.source
    is_file = isinstance(source, str) and Path(source).exists()
    kept, _, _, _, _ = read_source(cv2, source, args.start, args.seconds, is_file)
    if not kept:
        raise SystemExit('The source could not be read.')
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
    out = Path(args.store) / 'service' / 'team_select'
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob('g*_*.jpg'):
        old.unlink()
    split = split_teams(colours)
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
    (out / 'candidates.json').write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f'{len(colours)} people read in {len(kept)} frames; ' + (f'groups: {[(g["people"], g["colour_text"]) for g in groups]}, separation {split["separation"]}' if groups else split['reason']))
    print('Open /team-select on the review server and choose the own team.')


if __name__ == '__main__':
    main()
