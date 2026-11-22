"""A video that checks the goals: for each confirmed goal the full picture with the ball and the paths of the attacking players drawn on it, the same seconds
enlarged on the goal area (a fixed close-up, nobody is followed), and then the cards: what went well, what to fix, and the rules and drill for the players.

No tactical board and no 'key player' box. What is drawn is limited to what can be checked on the picture:
  the ball      a ring where the ball finder placed it with at least 70 % confidence and a thin line through the last positions (the finder finds the ball in about
                4 of 10 frames, so the ring comes and goes)
  the paths     of the attacking team's players. The player who was nearest to the ball in the 3 s before the goal and 1 s after it (when the ball was found) is drawn
                thick and named 'the one closest to the ball'; up to two more players who ended 15 m or more into the opponent half are drawn thin. A path is only drawn
                on frames where the tracker still labels that track as the attacking team and is cut where it jumps (an identity swap), so it never moves on to another team.

python scripts/build_goal_check_video.py <output folder> <calibrations.json> <video> <ffmpeg> --half "<name>|<tracks.json>|<camera>|<direction>|<offset>|<bg a,b,tx,ty>|<schedule>|<goals>" ...
       [--team B] [--ball ball-paths-goals.json]
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from app.attack_options import analyse, describe  # noqa: E402
from app.review_text import attack_instructions, attack_story, coaching  # noqa: E402
from build_match_report import Page, load_half, metres_to_pixel  # noqa: E402
from build_tactical_report import clock  # noqa: E402
from build_team_minimap import shift_at  # noqa: E402
from build_team_report import extract_frames  # noqa: E402
from app.team_role_features import FEATURE_NAMES, box_features  # noqa: E402
from report_motion import box_path  # noqa: E402
from track_review_clip import PITCH_TOP  # noqa: E402
from review_shots import KIND_COLOURS, MUTED, OUT, _fade_line, font, _put_text, analysis_card, caption, chip, description_card, px, rules_card, subtitle  # noqa: E402

import review_shots as _shots  # noqa: E402

SCALE = 2                                    # the page is drawn at 3840 x 2160 so that the slot for the video is 1920 x 1080: the recording is shown pixel for pixel
OUT = (_shots.OUT[0] * SCALE, _shots.OUT[1] * SCALE)
_shots.OUT = OUT
_shots.K = OUT[0] / _shots.SIZE[0]
FPS_OUT = 10
BEFORE, AFTER = 10.0, 4.0
AMBER, CORAL, PINK = (87, 200, 255), (101, 138, 255), (255, 120, 200)
THIN_COLOURS = [CORAL, PINK]
LOOK_BACK = 8.0
MIN_PATH = 8.0                    # metres a supporting player must have run toward the goal (a player who only stands in the scrum is not shown)
MIN_VOTES = 3                     # sightings of the ball next to a player before he is called the one closest to the ball
JUMP_PX = 140                     # a path that jumps further than this between two frames is cut (a swap of identities)
BALL_CONFIDENCE = 0.7
CARD_SECONDS = 6
DRAW_BALL = True                  # the ball ring and its last 1.5 s are drawn (the user asked for it on 2026-11-16; earlier videos had none)
DRAW_TRAILS = False               # the paths of players were drawn on players who were not the ones of the finish, so the video shows the ball and the passing lanes only
MISSED_PER_HALF = 4
GREEN = (182, 196, 46)


def load_ball(path, camera=None, height=1080):
    """{time rounded to 0.1 s: (x, y, confidence)} of all clips in a ball-paths file (scripts/apply_ball_rerank.py)."""
    found = {}
    if not path:
        return found
    for clip in json.loads(Path(path).read_text(encoding='utf-8')).values():
        for name, value in clip['path'].items():
            if value and value[2] >= BALL_CONFIDENCE and (camera is None or value[1] >= (PITCH_TOP[camera] - 0.05) * height):    # a ball above the pitch is a light or a spectator
                found[round(clip['start'] + (int(name[2:5]) - 1) / clip['fps'], 1)] = (value[0], value[1], value[2])
    return found


def inside_pitch(half, ball, margin=5.0):
    """The ball points that project onto the pitch plus `margin` metres (a ball in the air projects a little beyond the ground it is above). A point on the running track,
    in the stands or beyond the touchline is a person or a light, not the ball."""
    from app.pitch_map import apply
    pitch, fitted = half['fitted']['pitch'], half['fitted']
    kept = {}
    for t, (bx, by, p) in ball.items():
        frame = int(round((t - half['offset']) * half['fps']))
        x, y = bx, by
        dx, dy = shift_at(half['schedule'], frame)
        x, y = x - dx, y - dy
        if half['bg']:
            a, b, tx, ty = half['bg']
            x, y = a * x - b * y + tx, b * x + a * y + ty
        m = apply(fitted['H'], x / 1920.0, y / 1080.0)
        if m is not None and abs(m[0]) <= pitch['length'] / 2 + margin and abs(m[1]) <= pitch['width'] / 2 + margin:
            kept[t] = (bx, by, p)
    return kept


def team_rows(half, team, first, last):
    """{track id: [row]} of the rows of `team` in the frames first..last (rows the tracker labels with another team are left out)."""
    out = {}
    for tid, rows in half['result']['tracks'].items():
        mine = [r for r in rows if first - 60 <= r['frame'] <= last + 60 and r['team'] == team]
        if mine:
            out[tid] = mine
    return out


def nearest_to_ball(half, team, goal, ball):
    """The track of `team` that was most often within one body height of the ball in [goal - 3 s, goal + 1 s], or None when the ball was not found then."""
    fps, offset = half['fps'], half['offset']
    votes = {}
    for t, (bx, by, _p) in ball.items():
        if not goal - 3.0 <= t <= goal + 1.0:
            continue
        frame = int(round((t - offset) * fps))
        for tid, rows in half['result']['tracks'].items():
            for r in rows:
                if r['frame'] == frame and r['team'] == team:
                    x1, y1, x2, y2 = r['box']
                    if ((bx - (x1 + x2) / 2) ** 2 + (by - y2) ** 2) ** 0.5 <= max(40.0, 1.0 * (y2 - y1)):
                        votes[tid] = votes.get(tid, 0) + 1
                    break
    return (max(votes, key=votes.get), votes[max(votes, key=votes.get)]) if votes else (None, 0)


def supporters(half, team, goal, skip):
    """Up to two more players of `team` who ended 15 m or more into the opponent half after moving at least MIN_PATH metres in the LOOK_BACK seconds before the goal."""
    fps, offset, direction = half['fps'], half['offset'], half['direction']
    first, last = int(round((goal - LOOK_BACK - offset) * fps)), int(round((goal - offset) * fps))
    paths = {}
    for frame in range(first, last + 1):
        for tid, x, y in half['by_frame'].get(frame, {}).get(team, []):
            paths.setdefault(tid, []).append((frame, x * direction, y))
    found = []
    for tid, rows in paths.items():
        if tid == skip or len(rows) < 2.5 * fps:
            continue
        progress = rows[-1][1] - rows[0][1]
        if progress >= MIN_PATH and rows[-1][1] >= 15:
            found.append((tid, rows[-1][1] + max(0.0, rows[-1][1] - rows[0][1])))
    return [tid for tid, _ in sorted(found, key=lambda f: -f[1])[:2]]


def goal_crop(half, goal, frame_shape):
    """A fixed 16:9 window on the goal area of the goal attacked, in picture pixels (x0, y0, width, height)."""
    pitch, direction = half['fitted']['pitch'], half['direction']
    length = pitch['length']
    tf = int(round((goal - half['offset']) * half['fps']))
    shift = shift_at(half['schedule'], tf)
    points = []
    for u in (length / 2 - 26, length / 2 + 1):
        for y in (-22, 10):
            points.append(metres_to_pixel(half['fitted'], u * direction, y, shift, half['bg'], frame_shape[1], frame_shape[0]))
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    width_px = max(max(xs) - min(xs), (max(ys) - min(ys)) * 16 / 9, 420) * 1.08
    height_px = width_px * 9 / 16
    x0 = int(min(max(0, cx - width_px / 2), frame_shape[1] - width_px))
    y0 = int(min(max(0, cy - height_px / 2), frame_shape[0] - height_px))
    return x0, y0, int(width_px), int(height_px)


def foot_path(rows, first, last):
    """{frame: (x, y)} of the feet from the smoothed boxes of rows that are all of the attacking team (a gap in the labels leaves a gap in the path)."""
    return {f: ((b[0] + b[2]) / 2, b[3]) for f, b in box_path(rows, first, last, max_gap=10).items()}


def segments(points):
    """Split [(frame, (x, y))] where the path jumps further than JUMP_PX (the tracker handed the track to somebody else)."""
    out, current = [], []
    for item in points:
        if current and ((item[1][0] - current[-1][1][0]) ** 2 + (item[1][1] - current[-1][1][1]) ** 2) ** 0.5 > JUMP_PX:
            out.append(current)
            current = []
        current.append(item)
    return out + [current]


def draw_trails(canvas, feet, tf, first, scale=1.0, origin=(0, 0)):
    """feet: [(path, colour, thick)]; the part of every path up to frame `tf`, the newest segment with a dot at its end."""
    for path, colour, thick in feet:
        parts = segments([(f, p) for f, p in sorted(path.items()) if first <= f <= tf])
        for part in parts:
            points = [(int((x - origin[0]) * scale), int((y - origin[1]) * scale)) for _f, (x, y) in part]
            if len(points) >= 2:
                _fade_line(canvas, points, colour, px(5 if thick else 3), floor=0.25)
        if parts and len(parts[-1]) >= 1 and parts[-1][-1][0] >= tf - 3:
            end = parts[-1][-1][1]
            centre = (int((end[0] - origin[0]) * scale), int((end[1] - origin[1]) * scale))
            cv2.circle(canvas, centre, px(8 if thick else 5), colour, -1, cv2.LINE_AA)
            cv2.circle(canvas, centre, px(8 if thick else 5), (11, 17, 24), px(1), cv2.LINE_AA)


def draw_ball(canvas, ball, t, scale=1.0, origin=(0, 0)):
    """The ball where it was found (within 0.1 s of `t`): a bold yellow ring with a dark outline, and a yellow line through the positions of the last 1.5 s that fades toward the past.
    Only positions that a person confirmed or that the finder gave with at least BALL_CONFIDENCE are drawn, so a frame without a ring means the ball was not found."""
    near = sorted((tt, v) for tt, v in ball.items() if t - 1.5 <= tt <= t + 0.05)
    pts = [(tt, (int((v[0] - origin[0]) * scale), int((v[1] - origin[1]) * scale))) for tt, v in near]
    for (t0, a), (t1, b) in zip(pts, pts[1:]):
        if t1 - t0 > 0.45:
            continue
        fade = 1.0 - (t - t1) / 1.6
        colour = tuple(int(c * fade + 20 * (1 - fade)) for c in (40, 220, 255))
        cv2.line(canvas, a, b, (11, 17, 24), px(5), cv2.LINE_AA)
        cv2.line(canvas, a, b, colour, px(3), cv2.LINE_AA)
    now = [p for tt, p in pts if abs(tt - t) <= 0.1]
    if now:
        cv2.circle(canvas, now[0], px(15), (11, 17, 24), px(7), cv2.LINE_AA)
        cv2.circle(canvas, now[0], px(15), (40, 220, 255), px(4), cv2.LINE_AA)


def feet_at(half, tid, frame, tolerance=1):
    """Picture pixels (x, y) of the feet of track `tid` at the sighting nearest to `frame` (within `tolerance` frames of the tracker, 0.2 s each), or None. A ring is only
    drawn on a picture when the track was seen at that moment: a position from 0.6 s earlier would sit on whoever stands there now."""
    rows = [r for r in half['result']['tracks'].get(str(tid), []) if abs(r['frame'] - frame) <= tolerance]
    if not rows:
        return None
    r = min(rows, key=lambda r: abs(r['frame'] - frame))
    return int((r['box'][0] + r['box'][2]) / 2), int(r['box'][3])


def box_of(half, tid, frame, tolerance=1):
    rows = [r for r in half['result']['tracks'].get(str(tid), []) if abs(r['frame'] - frame) <= tolerance]
    return min(rows, key=lambda r: abs(r['frame'] - frame))['box'] if rows else None


def shirt_allowed(half, image, frame, team, neon_limit=0.10):
    """The track ids of `team` near `frame` whose shirt fits the team (the tracker sometimes carries the label of one team on a player of the other). Team B wears dark
    clothes, so a bright neon share of 0.10 or more in the upper body means the player is not team B; for team A the share must be at least 0.05. None when nothing could be measured."""
    neon = FEATURE_NAMES.index('neon')
    h, w = image.shape[:2]
    ids = set()
    for f in range(frame - 3, frame + 4):
        ids |= {t for t, _x, _y in half['by_frame'].get(f, {}).get(team, [])}
    keep = set()
    for tid in ids:
        box = box_of(half, tid, frame)
        if box is None:
            continue
        share = float(box_features(image, [box[0] / w, box[1] / h, box[2] / w, box[3] / h])[neon])
        if (team == 'B' and share < neon_limit) or (team == 'A' and share >= 0.05):
            keep.add(tid)
    return keep or None


def ball_carrier(half, team, time, ball, allowed):
    """The track of `team` that the ball finder saw the ball next to (within one and a half body heights of the feet) within 0.4 s of `time`, or None."""
    fps, offset = half['fps'], half['offset']
    votes = {}
    for t, (bx, by, _p) in ball.items():
        if abs(t - time) > 0.4:
            continue
        frame = int(round((t - offset) * fps))
        for tid in {tid for tid, _x, _y in half['by_frame'].get(frame, {}).get(team, [])}:
            box = box_of(half, tid, frame)
            if box is None or (allowed is not None and tid not in allowed):
                continue
            if ((bx - (box[0] + box[2]) / 2) ** 2 + (by - box[3]) ** 2) ** 0.5 <= max(50.0, 1.5 * (box[3] - box[1])):
                votes[tid] = votes.get(tid, 0) + 1
    return max(votes, key=votes.get) if votes else None


def dashed_line(canvas, start, end, colour, thickness, dash):
    length = max(1.0, ((end[0] - start[0]) ** 2 + (end[1] - start[1]) ** 2) ** 0.5)
    steps = max(2, int(length // dash))
    for k in range(0, steps, 2):
        a = (int(start[0] + (end[0] - start[0]) * k / steps), int(start[1] + (end[1] - start[1]) * k / steps))
        b = (int(start[0] + (end[0] - start[0]) * (k + 1) / steps), int(start[1] + (end[1] - start[1]) * (k + 1) / steps))
        cv2.line(canvas, a, b, colour, thickness, cv2.LINE_AA)


RED = (101, 101, 255)


def draw_options(image, half, facts, frame, who='앞선 선수'):
    """A close-up of the play with the passing lanes from the player with the ball: dashed green lines to teammates the ball could reach (no opponent next to the line,
    the ones across the pitch first) and dashed red lines where an opponent stands on the line, with a red ring on that defender. The window is cut around the players
    involved and enlarged to the output size so that lines and words are easy to read."""
    carrier = feet_at(half, facts['carrier'], frame)
    if carrier is None:
        return cv2.resize(image, OUT, interpolation=cv2.INTER_AREA)
    opened = sorted([l for l in facts['lanes'] if l['open']], key=lambda l: (not l['across'], not l['forward'], l['length']))[:3]
    blocked = sorted([l for l in facts['lanes'] if not l['open']], key=lambda l: (not l['forward'], l['length']))[:3]
    shown = opened + blocked
    targets = []
    for lane in shown:
        spot = feet_at(half, lane['track'], frame)
        blocker = feet_at(half, lane['blocker'], frame) if lane['blocker'] is not None else None
        if spot is not None:
            targets.append((spot, lane, blocker))
    points = [carrier] + [t[0] for t in targets] + [t[2] for t in targets if t[2] is not None]
    x0, x1 = min(p[0] for p in points) - 160, max(p[0] for p in points) + 160
    y0, y1 = min(p[1] for p in points) - 120, max(p[1] for p in points) + 90
    width = max(x1 - x0, (y1 - y0) * 16 / 9, 640)
    height = width * 9 / 16
    left = int(min(max(0, (x0 + x1) / 2 - width / 2), image.shape[1] - width))
    top = int(min(max(0, (y0 + y1) / 2 - height / 2), image.shape[0] - height))
    scale = OUT[0] / width
    canvas = cv2.resize(image[top:top + int(height), left:left + int(width)], OUT, interpolation=cv2.INTER_CUBIC)
    blur = cv2.GaussianBlur(canvas, (0, 0), 2.5)
    canvas = cv2.addWeighted(canvas, 1.5, blur, -0.5, 0)

    def to_canvas(point):
        return int((point[0] - left) * scale), int((point[1] - top) * scale)
    start = to_canvas(carrier)
    labelled = set()
    for tid, colour in [(facts['carrier'], AMBER)] + [(l['track'], GREEN if l['open'] else RED) for l in facts['lanes'] if any(l['track'] == t[1]['track'] for t in targets)]:
        box = box_of(half, tid, frame)
        if box is not None:
            p1, p2 = to_canvas((box[0], box[1])), to_canvas((box[2], box[3]))
            cv2.rectangle(canvas, p1, p2, colour, px(1), cv2.LINE_AA)
    for spot, lane, blocker in targets:
        end = to_canvas(spot)
        colour = GREEN if lane['open'] else RED
        dashed_line(canvas, start, end, colour, px(4), px(18))
        cv2.circle(canvas, end, px(20), colour, px(4), cv2.LINE_AA)
        if blocker is not None:
            if lane['blocker'] not in labelled:
                labelled.add(lane['blocker'])
                cv2.circle(canvas, to_canvas(blocker), px(20), (255, 255, 255), px(3), cv2.LINE_AA)
                canvas = _put_text(canvas, '막는 수비수', (to_canvas(blocker)[0] + px(24), to_canvas(blocker)[1] - px(44)), 18, (255, 255, 255))
        else:
            canvas = _put_text(canvas, '패스길 열림', (end[0] + px(24), end[1] - px(44)), 18, GREEN[::-1])
    cv2.circle(canvas, start, px(22), AMBER, px(4), cv2.LINE_AA)
    return _put_text(canvas, who, (start[0] + px(26), start[1] - px(46)), 20, AMBER[::-1])


def slot():
    """Where the picture goes on the page (pixels): the same place as on the report page (logical 56, 124, 640 x 360)."""
    return px(56), px(124), px(640), px(360)


def report_layout(title, tone, words, story, instructions):
    """The static part of a page of the report (title, the scene and the space on the right, what went well, what to fix and how to move at the bottom) as a picture; the
    video of the moment is put into the empty slot on the left, so that every frame looks like the report page."""
    page = Page(title, '장면 분석', tone)
    page.draw.text((56, 488), '주황: 앞선 선수 · 초록: 열린 패스길 · 빨강: 수비수가 막은 패스길 · 흰 원: 막는 수비수', font=font(13), fill=MUTED)
    page.panel([716, 124, 1224, 484])
    y = 134
    for heading, lines, colour in (('장면', (words or {}).get('scene', []), KIND_COLOURS['info']), ('공간', (words or {}).get('space', []), KIND_COLOURS['good'])):
        page.heading(736, y, heading, colour, 20)
        y += 30
        y = page.bullets(736, y, lines or ['위치가 충분히 잡히지 않아 설명하지 못했습니다'], 460, 15, colour, 4) + 6
    columns = [('잘한 점', (story or {}).get('good', [])[:3], KIND_COLOURS['good']), ('보완할 점', ((story or {}).get('fix') or ['특별히 지적할 선택은 없었습니다'])[:3], KIND_COLOURS['poor']),
               ('이렇게 움직이세요', instructions[:3], KIND_COLOURS['info'])]
    for k, (heading, lines, colour) in enumerate(columns):
        x = 56 + k * 394
        page.panel([x, 510, x + 380, 676])
        page.heading(x + 16, 514, heading, colour, 17)
        page.bullets(x + 16, 540, lines, 346, 13, colour, 3)
    return page.result()


def in_slot(background, picture, phase, colour):
    """The page with `picture` (any size) in the slot and a small label of what is shown at its top-left corner."""
    x, y, w, h = slot()
    canvas = background.copy()
    canvas[y:y + h, x:x + w] = picture if picture.shape[1] == w and picture.shape[0] == h else cv2.resize(picture, (w, h), interpolation=cv2.INTER_AREA if picture.shape[1] > w else cv2.INTER_CUBIC)
    cv2.rectangle(canvas, (x, y), (x + px(10) + len(phase) * px(13), y + px(24)), (24, 17, 11), -1)
    return _put_text(canvas, phase, (x + px(6), y + px(3)), 13, colour[::-1] if False else colour)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('output')
    parser.add_argument('calibrations')
    parser.add_argument('video')
    parser.add_argument('ffmpeg')
    parser.add_argument('--half', action='append', required=True)
    parser.add_argument('--team', choices=('A', 'B'), default='B')
    parser.add_argument('--ball')
    parser.add_argument('--intro', nargs='*', default=[], help='picture files (report pages) shown first, each for --intro-seconds')
    parser.add_argument('--intro-seconds', type=float, default=8.0)
    parser.add_argument('--outro', nargs='*', default=[], help='picture files (report pages) shown last, each for --intro-seconds')
    args = parser.parse_args()
    calibrations = json.loads(Path(args.calibrations).read_text(encoding='utf-8'))
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    parts = []
    if args.intro:
        intro = out / 'intro.mp4'
        parts.append(intro)
        if not intro.with_suffix('.done').exists():
            writer = cv2.VideoWriter(str(intro), cv2.VideoWriter_fourcc(*'mp4v'), FPS_OUT, OUT)
            for name in args.intro:
                picture = cv2.imread(name)
                picture = cv2.resize(picture, OUT, interpolation=cv2.INTER_CUBIC) if picture.shape[1] != OUT[0] else picture
                for _ in range(int(args.intro_seconds * FPS_OUT)):
                    writer.write(picture)
            writer.release()
            intro.with_suffix('.done').write_text('ok')
    for half_number, spec in enumerate(args.half, 1):
        half = load_half(spec, calibrations, args.team)
        ball_all = load_ball(args.ball, half['camera'])
        ball = inside_pitch(half, ball_all)
        print(half['name'], 'ball points kept on the pitch:', len(ball), 'of', len(ball_all))
        fps, offset, direction = half['fps'], half['offset'], half['direction']
        moments = [{'kind': 'goal', 'time': g, 'before': BEFORE, 'after': AFTER} for g in half['goals']]
        missed = [e for e in half['events'] if e['kind'] in ('box_attack', 'isolated') and not e.get('goal_follow') and all(abs(e['time'] - g) > 40 for g in half['goals'])]
        chosen_missed = []
        for e in sorted(missed, key=lambda e: -e['strength']):
            if len(chosen_missed) < MISSED_PER_HALF and all(abs(e['time'] - c['time']) > 30 for c in chosen_missed):
                chosen_missed.append(e)
        for e in chosen_missed:
            moments.append({'kind': e['kind'], 'time': e['time'], 'before': 6.0, 'after': 6.0})
        other = 'A' if args.team == 'B' else 'B'
        for number, moment in enumerate(sorted(moments, key=lambda m: m['time']), 1):
            goal, kind = moment['time'], moment['kind']
            is_goal = kind == 'goal'
            before, after = moment['before'], moment['after']
            part = out / f'moment_h{half_number}_{number}.mp4'
            parts.append(part)
            if part.with_suffix('.done').exists():
                continue
            start = goal - before
            # who is who at the moment of the options: the shirts decide which tracks are really of the attacking team, the ball finder (when it saw the ball next to a player) who has the ball
            option_time = goal - 2.0 if is_goal else goal + 1.5
            still_file = extract_frames(args.ffmpeg, args.video, option_time, 0.2, FPS_OUT, out / 'option_frame')[0]
            still = cv2.imread(str(still_file))
            option_frame = int(round((option_time - offset) * fps))
            allowed = shirt_allowed(half, still, option_frame, args.team)
            carrier = ball_carrier(half, args.team, option_time, ball, allowed)
            facts = analyse(half['by_frame'], args.team, other, direction, fps, offset, option_time, carrier=carrier, allowed=allowed)
            story = attack_story(facts, is_goal) if facts else None
            words = describe(half['by_frame'], args.team, other, direction, fps, offset, option_time, facts, half['fitted']['pitch']['length'], half['fitted']['pitch']['width'], allowed) if facts else None
            tone = 'goal' if is_goal else 'poor'
            files = extract_frames(args.ffmpeg, args.video, start, before + after, FPS_OUT, out / 'frames')
            sample = cv2.imread(str(files[0]))
            first_f, last_f = int(round((goal - LOOK_BACK - offset) * fps)), int(round((goal + after - offset) * fps))
            rows = team_rows(half, args.team, first_f, last_f)
            closest, votes = nearest_to_ball(half, args.team, goal, ball)
            closest = closest if votes >= MIN_VOTES and (allowed is None or closest in allowed) else None
            if is_goal:
                chosen = [closest] if closest in rows else []        # only the player the ball was seen next to: the other runners could not be tied to the finish and were drawn on players far from it
            else:
                lead = facts['carrier'] if facts else None
                chosen = [lead] if lead in rows else []
            feet = [(foot_path(rows[t], first_f, last_f), AMBER if k == 0 else THIN_COLOURS[k % 2], k == 0) for k, t in enumerate(chosen)]
            if not DRAW_TRAILS:
                feet = []
            if not feet:
                note = None
            elif not is_goal:
                note = '공격 팀 공을 가진 것으로 보이는 선수의 이동 경로'
            elif closest in rows:
                note = '공과 가장 가까웠던 선수(굵은 선)와 공격 선수의 이동 경로'
            else:
                note = None
            writer = cv2.VideoWriter(str(part), cv2.VideoWriter_fourcc(*'mp4v'), FPS_OUT, OUT)
            title = f'{half["name"]} {clock(goal)} ' + ('득점' if is_goal else '골이 나오지 못한 공격')
            background = report_layout(title, tone, words, story, attack_instructions(facts, is_goal) if facts else [])
            gold = KIND_COLOURS['goal'] if is_goal else KIND_COLOURS['poor']

            def frame_of(index):
                t = start + index / FPS_OUT
                return cv2.imread(str(files[index])), int(round((t - offset) * fps)), t

            # 1. the moment itself in the slot of the page
            for index in range(0, len(files) if not is_goal else int((before + 1) * FPS_OUT)):
                image, _tf, _t = frame_of(index)
                if DRAW_BALL:
                    draw_ball(image, ball, _t)
                writer.write(in_slot(background, image, '장면 영상', gold))
            # 2. a goal: the goal area enlarged (a fixed window), the last 6 s before the goal and 4 s after
            if is_goal:
                x0, y0, w, h = goal_crop(half, goal, sample.shape)
                for index in range(int((before - 6) * FPS_OUT), len(files)):
                    image, _tf, _t = frame_of(index)
                    if DRAW_BALL:
                        draw_ball(image, ball, _t)
                    zoom = cv2.resize(image[y0:y0 + h, x0:x0 + w], (slot()[2], slot()[3]), interpolation=cv2.INTER_CUBIC)
                    blur = cv2.GaussianBlur(zoom, (0, 0), 2.5)
                    zoom = cv2.addWeighted(zoom, 1.5, blur, -0.5, 0)
                    writer.write(in_slot(background, zoom, '골 지역 확대', gold))
            # 3. the passing lanes of the moment before the finish, held for six seconds
            if facts:
                who = '공을 가진 선수' if facts['carrier_source'] == 'given' else '앞선 선수'
                picture = draw_options(still, half, facts, option_frame, who)
                for _ in range(6 * FPS_OUT):
                    writer.write(in_slot(background, picture, f'패스길 {clock(option_time)}', KIND_COLOURS['info']))
            # 4. the same seconds again, slower
            for k in range(len(files) * 2):
                image, _tf, _t = frame_of(min(len(files) - 1, k // 2))
                if DRAW_BALL:
                    draw_ball(image, ball, _t)
                writer.write(in_slot(background, image, '다시 보기(느리게)', gold))
            writer.release()
            part.with_suffix('.done').write_text('ok')
            lanes = [] if not facts else facts['lanes']
            print('wrote', part.name, kind, 'allowed shirts:', None if allowed is None else len(allowed), 'carrier:', None if not facts else (facts['carrier'], facts['carrier_source']), 'lanes open/blocked:', (sum(1 for l in lanes if l['open']), sum(1 for l in lanes if not l['open'])))
    if args.outro:
        outro = out / 'outro.mp4'
        parts.append(outro)
        if not outro.with_suffix('.done').exists():
            writer = cv2.VideoWriter(str(outro), cv2.VideoWriter_fourcc(*'mp4v'), FPS_OUT, OUT)
            for name in args.outro:
                picture = cv2.imread(name)
                picture = cv2.resize(picture, OUT, interpolation=cv2.INTER_CUBIC) if picture.shape[1] != OUT[0] else picture
                for _ in range(int(args.intro_seconds * 1.5 * FPS_OUT)):
                    writer.write(picture)
            writer.release()
            outro.with_suffix('.done').write_text('ok')
    listing = out / 'parts.txt'
    listing.write_text('\n'.join(f"file '{p.as_posix()}'" for p in parts), encoding='utf-8')
    final = out / 'goal_check.mp4'
    subprocess.run([args.ffmpeg, '-hide_banner', '-loglevel', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', str(listing), '-c:v', 'libx264', '-preset', 'fast', '-crf', '20', '-pix_fmt', 'yuv420p', str(final)], check=True)
    print('wrote', final)


if __name__ == '__main__':
    main()
