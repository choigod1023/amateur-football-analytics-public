"""Draw the tracked players of one clip on a pitch map in metres, with per-frame team shape measures.

Usage: python scripts/build_team_minimap.py <tracks.json from track_review_clip.py> <calibrations.json> <camera> <output folder> [--fps 5]

Refuses to run without a saved calibration for the camera, and refuses a calibration whose own error is above 5 m.
Everything is a measurement aid: pitch size is an estimate, tracks are fragmented, team labels come from a classifier
trained on one match, and a player standing within 0.7 body heights of another one is marked as crowded because the
detector may have merged or dropped people there. Nothing is sent anywhere.
"""
import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.pitch_map import feet_to_metres, fit, pitch_lines, team_shape  # noqa: E402

COLOURS = {'A': (58, 255, 215), 'B': (200, 179, 159), 'R': (174, 111, 255)}      # BGR: yellow-green, grey-blue, pink
CROWDED_HEIGHTS = 0.7


def crowded_flags(entries):
    """entries: [(track id, box)]. A box is crowded when another box is closer than CROWDED_HEIGHTS body heights."""
    flags = set()
    for tid, box in entries:
        height = max(1.0, box[3] - box[1])
        cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
        for other, ob in entries:
            if other != tid and math.hypot((ob[0] + ob[2]) / 2 - cx, (ob[1] + ob[3]) / 2 - cy) < CROWDED_HEIGHTS * height:
                flags.add(tid)
                break
    return flags


def parse_schedule(text):
    """'0:-1.8,6.8;1950:0.3,0.3' -> [(0, (-1.8, 6.8)), (1950, (0.3, 0.3))]: the camera shift that holds from a frame on."""
    entries = []
    for part in text.split(';'):
        frame, shift = part.split(':')
        dx, dy = shift.split(',')
        entries.append((int(frame), (float(dx), float(dy))))
    return sorted(entries)


def shift_at(schedule, frame, default=(0.0, 0.0)):
    current = default
    for start, shift in schedule:
        if frame >= start:
            current = shift
    return current


def measure_frame(tracks, frame, fitted, width, height, shift=(0.0, 0.0), bg=None):
    """Positions in metres per team for one frame, plus counts of players that could not be placed."""
    rows = [(tid, row) for tid, rs in tracks.items() for row in rs if row['frame'] == frame and row['team'] in COLOURS]
    crowded = crowded_flags([(tid, row['box']) for tid, row in rows])
    placed = {'A': [], 'B': [], 'R': []}
    outside = 0
    for tid, row in rows:
        m = feet_to_metres(fitted, row['box'], width, height, shift, bg)
        if m is None:
            outside += 1
            continue
        placed[row['team']].append({'track': tid, 'x': m[0], 'y': m[1], 'crowded': tid in crowded, 'interpolated': bool(row.get('interpolated'))})
    return placed, outside


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('tracks')
    parser.add_argument('calibrations')
    parser.add_argument('camera')
    parser.add_argument('output')
    parser.add_argument('--fps', type=float, default=5.0)
    parser.add_argument('--team-size', type=int, default=11, help='players per team in this match; the metrics report how many of them were seen in each frame')
    parser.add_argument('--pitch-length', type=float, help='use this pitch length (m) instead of the one saved with the calibration')
    parser.add_argument('--pitch-width', type=float, help='use this pitch width (m) instead of the one saved with the calibration')
    parser.add_argument('--reference-image', help='the scene photo the calibration was clicked on; with --clip-frame the camera shift of the clip is measured and removed')
    parser.add_argument('--reference-bg', type=float, nargs=4, metavar=('A', 'B', 'TX', 'TY'), help='the stored background registration of the reference photo (scene list field bg)')
    parser.add_argument('--shift-schedule', help="camera shift that changes over the stretch, e.g. '0:-1.8,6.8;1950:0.3,0.3' (frame:dx,dy from that frame on); replaces the single measured shift")
    parser.add_argument('--clip-frame', help='one frame of the clip (for example f_025.jpg)')
    args = parser.parse_args()
    result = json.loads(Path(args.tracks).read_text(encoding='utf-8'))
    calibrations = json.loads(Path(args.calibrations).read_text(encoding='utf-8'))
    record = calibrations.get(args.camera)
    if not record:
        raise SystemExit(f'No saved calibration for {args.camera}. Nothing is drawn without one.')
    override = {k: v for k, v in (('length', args.pitch_length), ('width', args.pitch_width)) if v}
    if override:
        record = {**record, 'pitch': {**(record.get('pitch') or {}), **override}}      # the clicks stay, only the assumed pitch size changes
    fitted = fit(record)
    if 'H' not in fitted:
        raise SystemExit('Calibration refused: ' + fitted['error'])
    import cv2
    import numpy as np
    shift, bg = (0.0, 0.0), (tuple(args.reference_bg) if args.reference_bg else None)
    if args.reference_image and args.clip_frame:
        from app.pitch_map import frame_shift_images
        shift = frame_shift_images(cv2.imread(args.reference_image), cv2.imread(args.clip_frame))
        print(f'camera shift of the clip against the reference photo: {shift[0]:.1f}, {shift[1]:.1f} px (removed)')
    schedule = parse_schedule(args.shift_schedule) if args.shift_schedule else []
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    width, height, frames = 1920, 1080, result['frames']
    pitch = fitted['pitch']
    cw, ch, pad = 720, 460, 28
    scale = min((cw - 2 * pad) / pitch['length'], (ch - 2 * pad) / pitch['width'])
    to_px = lambda x, y: (int(cw / 2 + x * scale), int(ch / 2 + y * scale))
    writer = cv2.VideoWriter(str(out / 'minimap.mp4'), cv2.VideoWriter_fourcc(*'mp4v'), args.fps, (cw, ch))
    per_frame = []
    for frame in range(frames):
        placed, outside = measure_frame(result['tracks'], frame, fitted, width, height, shift_at(schedule, frame, shift), bg)
        canvas = np.full((ch, cw, 3), (42, 90, 31), np.uint8)
        for line in pitch_lines(pitch):
            cv2.polylines(canvas, [np.array([to_px(x, y) for x, y in line], np.int32)], False, (229, 245, 233), 1)
        for team, items in placed.items():
            for item in items:
                x, y = to_px(item['x'], item['y'])
                cv2.circle(canvas, (x, y), 6 if team == 'R' else 5, COLOURS[team], 1 if item['interpolated'] else -1)      # hollow: no detection in this frame
                if item['crowded']:
                    cv2.circle(canvas, (x, y), 9, (255, 255, 255), 1)              # white ring: crowded, less reliable
        cv2.putText(canvas, f'frame {frame + 1}/{frames}  calibration error {fitted["rms"]:.2f} m (pitch size is an estimate)', (10, 18),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)
        writer.write(canvas)
        shapes = {team: team_shape([(i['x'], i['y']) for i in placed[team]]) for team in ('A', 'B')}
        everyone = [i for items in placed.values() for i in items]
        per_frame.append({'frame': frame, 'placed': {team: len(items) for team, items in placed.items()}, 'outside_pitch': outside,
                          'interpolated_share': round(sum(i['interpolated'] for i in everyone) / len(everyone), 2) if everyone else None,
                          'seen_share': {team: round(len(placed[team]) / args.team_size, 2) for team in ('A', 'B')},
                          'crowded_share': round(sum(i['crowded'] for i in everyone) / len(everyone), 2) if everyone else None,
                          'team_a': shapes['A'], 'team_b': shapes['B']})
    writer.release()
    summary = {'clip': result['clip'], 'camera': args.camera, 'calibration_rms_m': round(fitted['rms'], 2), 'calibration_points': fitted['points'],
               'pitch_m': {k: pitch[k] for k in ('length', 'width')}, 'camera_shift_px': [round(shift[0], 1), round(shift[1], 1)], 'shift_schedule': schedule, 'reference_bg': list(bg) if bg else None,
               'team_size': args.team_size, 'caution': 'seen_share is the share of the team that was placed in the frame (the rest was missed, hidden or outside the pitch); pitch size is an estimate; tracks are fragmented; team labels are unverified for this clip; crowded players are less reliable',
               'frames': per_frame}
    (out / 'metrics.json').write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding='utf-8')
    print('wrote', out / 'minimap.mp4', 'and metrics.json; calibration error', round(fitted['rms'], 2), 'm')


if __name__ == '__main__':
    main()
