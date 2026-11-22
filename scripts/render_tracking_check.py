"""Show what the player tracking really does: boxes, track numbers and short trails drawn on the original video.

Usage: python scripts/render_tracking_check.py <tracks.json from track_from_cache.py> <video> <start second> <seconds> <output.mp4> [ffmpeg] [--team-profile <team_profile.json>]

Team A (bright clothes) in yellow, team B (dark clothes) in sky blue, referees pink, other labels grey. A hollow box means the row was filled in by
interpolation (no detection in that frame). The top left shows how many players of each team are drawn in the frame, so a missing player is visible
as a count below 11. Nothing here is a measurement of accuracy: it only shows what the tracker produced.
"""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np

COLOURS = {'A': (58, 255, 215), 'B': (235, 190, 120), 'R': (200, 120, 255)}


def main():
    argv = sys.argv
    if '--team-profile' in argv:                       # optional: draw the two teams in the colours of the team profile (letters stay: B own team, A opponent)
        at = argv.index('--team-profile')
        profile_path = argv[at + 1]
        del argv[at:at + 2]
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import team_profile_cli

        class _Args:
            team_profile = profile_path
        team_profile_cli.setup(_Args)
    tracks_file, video, start, seconds, output = argv[1], argv[2], float(argv[3]), float(argv[4]), argv[5]
    ffmpeg = argv[6] if len(argv) > 6 else 'ffmpeg'
    data = json.loads(Path(tracks_file).read_text(encoding='utf-8'))
    fps, offset = float(data['fps']), float(data['first_second'])
    by_frame = {}
    for tid, rows in data['tracks'].items():
        for row in rows:
            by_frame.setdefault(row['frame'], []).append((tid, row))
    folder = Path(tempfile.mkdtemp(prefix='tc_'))
    out_fps = 10
    subprocess.run([ffmpeg, '-hide_banner', '-loglevel', 'error', '-y', '-ss', f'{start:.3f}', '-t', f'{seconds:.3f}', '-i', video, '-vf', f'fps={out_fps}', '-q:v', '2', str(folder / 'f_%04d.jpg')], check=True)
    files = sorted(folder.glob('f_*.jpg'))
    writer = cv2.VideoWriter(output, cv2.VideoWriter_fourcc(*'mp4v'), out_fps, (1280, 720))
    centres = {}
    for k, file in enumerate(files):
        frame = cv2.imread(str(file))
        if frame is None:
            break
        t = start + k / out_fps
        track_frame = int(round((t - offset) * fps))
        image = cv2.resize(frame, (1280, 720))
        scale = 1280 / frame.shape[1]
        count = {'A': 0, 'B': 0}
        for tid, row in by_frame.get(track_frame, []):
            team = row['team']
            if team not in COLOURS:
                continue
            b = [int(v * scale) for v in row['box']]
            colour = COLOURS[team]
            count[team] = count.get(team, 0) + (1 if team in count else 0)
            cx, y2 = (b[0] + b[2]) // 2, b[3]
            trail = centres.setdefault(tid, [])
            trail.append((cx, y2))
            del trail[:-20]
            for a, c in zip(trail, trail[1:]):
                cv2.line(image, a, c, colour, 1, cv2.LINE_AA)
            cv2.rectangle(image, (b[0], b[1]), (b[2], b[3]), colour, 1 if row.get('interpolated') else 2)
            cv2.putText(image, str(tid)[-4:], (b[0], max(10, b[1] - 3)), cv2.FONT_HERSHEY_SIMPLEX, 0.4, colour, 1, cv2.LINE_AA)
        cv2.rectangle(image, (0, 0), (520, 34), (0, 0, 0), -1)
        cv2.putText(image, f'{int(t) // 60}:{int(t) % 60:02d}  A {count["A"]} / B {count["B"]}  (11 expected)  hollow=interpolated', (8, 23), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)
        writer.write(image)
    writer.release()
    shutil.rmtree(folder, ignore_errors=True)


if __name__ == '__main__':
    main()
