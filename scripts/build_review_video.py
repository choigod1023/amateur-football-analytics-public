"""A coaching review of a whole half: the moments worth talking about, each followed through to the end of the attack.

Usage: python scripts/build_review_video.py <tracks.json> <calibrations.json> <camera> <video> <output folder> --team B --direction 1
       [--half-name 후반] [--goals 300,450] [--max-events 10] [--pitch-length 89 --pitch-width 62] [--reference-bg A B TX TY]
       [--shift-schedule "0:0,0;1950:0.3,0.3"] [--ffmpeg ffmpeg]

The whole half is searched (app/event_miner.py) for runs in behind, runs the team allowed, an advanced player left alone and the back line dropping deep;
confirmed goals (--goals, video seconds) are added and a sequence that led into a goal is followed to the goal. Every moment is shown as
  a wide shot (the whole picture, a thin tracking box around the followed player, subtitles),
  a full-screen close-up that follows the player all the way to the end of the sequence (the goal when one follows),
  for one or two of the moments a top-down board of an 11 v 11 game (no trails, smooth positions, dashed circles for the players that were not seen),
  and an analysis card: what went well, what to fix, what to do next.
Output: review.mp4, review.md and events.json. There is no ball in the data, so a shot that is not a goal is never reported. Every moment is written as its own
part file, so a stopped run (power loss) continues with the moments that are not finished.
"""
import argparse
import bisect
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from app.event_miner import mine_events  # noqa: E402
from app.pitch_map import fit  # noqa: E402
from app.profile_teams import shirt_accepts  # noqa: E402
from app.team_style import team_name as team_name_of  # noqa: E402
from app.review_text import analysis, captions, coaching, half_summary, index_title  # noqa: E402
from app.tactical_concepts import box_presence  # noqa: E402
from app.tactical_feedback import estimate_missing  # noqa: E402
from app.team_role_features import FEATURE_NAMES, box_features  # noqa: E402
import team_profile_cli  # noqa: E402
from build_tactical_report import clock, metre_rows  # noqa: E402
from build_team_minimap import parse_schedule  # noqa: E402
from build_team_report import extract_frames, series_of  # noqa: E402
from report_motion import choose_key_track  # noqa: E402
from review_shots import OUT, Board, analysis_card, bullet_card, caption, index_card, rules_card, wide_shot, zoom_shot  # noqa: E402

FPS_OUT = 10
LEAD = 6.0                     # seconds before the moment that are cut from the video
ZOOM_MAX = 18.0                # longest follow-through shown in the close-up
KIND_OF = {'good': 'good', 'poor': 'poor', 'goal': 'goal'}


def smooth_at(frames, positions, frame, radius=3):
    """Position of a track at a (fractional) frame: the average of its sightings within +-`radius` frames, interpolated between the two whole frames around it.
    frames: sorted list of the frames the track was seen, positions: {frame: (x, y)}. None when the track was not seen near that frame."""
    def whole(f):
        low, high = bisect.bisect_left(frames, f - radius), bisect.bisect_right(frames, f + radius)
        near = frames[low:high]
        if not near:
            return None
        return sum(positions[k][0] for k in near) / len(near), sum(positions[k][1] for k in near) / len(near)
    f0 = int(frame // 1)
    a, b = whole(f0), whole(f0 + 1)
    if a is None or b is None:
        return a or b
    share = frame - f0
    return a[0] + (b[0] - a[0]) * share, a[1] + (b[1] - a[1]) * share


def main():
    parser = argparse.ArgumentParser()
    for name in ('tracks', 'calibrations', 'camera', 'video', 'output'):
        parser.add_argument(name)
    parser.add_argument('--team', choices=('A', 'B'), default='B')
    parser.add_argument('--direction', type=int, choices=(1, -1), required=True)
    parser.add_argument('--half-name', default='경기')
    parser.add_argument('--goals', default='')
    parser.add_argument('--max-events', type=int, default=10)
    parser.add_argument('--pitch-length', type=float)
    parser.add_argument('--pitch-width', type=float)
    parser.add_argument('--reference-bg', type=float, nargs=4)
    parser.add_argument('--shift-schedule')
    parser.add_argument('--ffmpeg', default='ffmpeg')
    parser.add_argument('--detector', default=os.environ.get('FOOTBALL_REPORT_DETECTOR', 'yolo11n.pt'), help='person detector used to put the tracking box on a real person')
    parser.add_argument('--ball-candidates', help='ball candidate weights (with --ball-reranker the ball is searched in every sequence and drawn where it is found)')
    parser.add_argument('--ball-reranker')
    team_profile_cli.add_argument(parser)
    args = parser.parse_args()
    style, teams = team_profile_cli.setup(args)
    result = json.loads(Path(args.tracks).read_text(encoding='utf-8'))
    record = json.loads(Path(args.calibrations).read_text(encoding='utf-8')).get(args.camera)
    if not record:
        raise SystemExit(f'No saved calibration for {args.camera}.')
    override = {k: v for k, v in (('length', args.pitch_length), ('width', args.pitch_width)) if v}
    if override:
        record = {**record, 'pitch': {**(record.get('pitch') or {}), **override}}
    fitted = fit(record)
    if 'H' not in fitted:
        raise SystemExit('Calibration refused: ' + fitted['error'])
    pitch = fitted['pitch']
    fps, offset = float(result['fps']), float(result['first_second'])
    other = 'A' if args.team == 'B' else 'B'
    team_name = team_name_of(style, args.team)
    by_frame, _ = metre_rows(result['tracks'], fitted, parse_schedule(args.shift_schedule) if args.shift_schedule else [], tuple(args.reference_bg) if args.reference_bg else None, 0, result['frames'])
    step_frames = int(fps)
    paths_by_track = {}
    for frame_number, teams in by_frame.items():
        for name, items in teams.items():
            for tid, x, y in items:
                paths_by_track.setdefault((tid, name), []).append((frame_number, x, y))
    metre_at, seen_frames, team_of_track = {}, {}, {}
    for (tid, name), path in paths_by_track.items():
        path.sort()
        metre_at.setdefault(tid, {}).update({f: (x, y) for f, x, y in path})
        team_of_track[tid] = name
    for tid in metre_at:
        seen_frames[tid] = sorted(metre_at[tid])
    centre_cache = {}

    def centre(name, frame):
        key = (name, frame)
        if key not in centre_cache:
            rows = by_frame.get(frame, {}).get(name, [])
            centre_cache[key] = (sum(x for _t, x, _y in rows) / len(rows), sum(y for _t, _x, y in rows) / len(rows)) if rows else None
        return centre_cache[key]

    series_team = series_of(by_frame, args.team, other, args.direction, fps, result['frames'], 6)
    series_other = series_of(by_frame, other, args.team, -args.direction, fps, result['frames'], 6)
    if len(series_team) < 60:
        raise SystemExit('Fewer than 60 measured seconds: not enough to review.')
    sign = {args.team: args.direction, other: -args.direction}
    u_paths = {name: {tid: [(f, x * sign[name], y) for f, x, y in path] for (tid, n), path in paths_by_track.items() if n == name} for name in (args.team, other)}
    goals = [float(g) for g in args.goals.split(',') if g.strip()]
    events = mine_events(u_paths[args.team], u_paths[other], series_team, series_other, goals, fps, offset, args.max_events, pitch_length=pitch['length'])
    if not events:
        raise SystemExit('No moment worth showing was found in this stretch.')
    # the board is shown for one or two moments only: the strongest good one and the strongest poor one
    board_for = set()
    best_good = max((i for i, e in enumerate(events) if e['polarity'] != 'poor'), key=lambda i: events[i]['strength'], default=None)
    best_poor = max((i for i, e in enumerate(events) if e['polarity'] == 'poor'), key=lambda i: events[i]['strength'], default=None)
    board_for.update(i for i in (best_good, best_poor) if i is not None)

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    probe = cv2.VideoCapture(args.video)
    neon_index = list(FEATURE_NAMES).index('neon')

    def shirt_matches(label):
        def check(tid, path):
            frames = sorted(path)
            shares = []
            for f in (frames[len(frames) // 5], frames[len(frames) // 2], frames[4 * len(frames) // 5]):
                probe.set(cv2.CAP_PROP_POS_MSEC, (offset + f / fps) * 1000)
                ok, image = probe.read()
                if ok:
                    h, w = image.shape[:2]
                    b = path[f]
                    shares.append(float(box_features(image, [max(0.0, b[0] / w), max(0.0, b[1] / h), min(1.0, b[2] / w), min(1.0, b[3] / h)])[neon_index]))
            if not shares:
                return True
            mean = sum(shares) / len(shares)
            return mean < 0.10 if label == 'B' else mean >= 0.05
        if teams is not None:
            def check(tid, path):                    # the colours the coach chose decide, not the neon share of the first match
                frames = sorted(path)
                letters = []
                for f in (frames[len(frames) // 5], frames[len(frames) // 2], frames[4 * len(frames) // 5]):
                    probe.set(cv2.CAP_PROP_POS_MSEC, (offset + f / fps) * 1000)
                    ok, image = probe.read()
                    if ok:
                        letters.append(teams.letter_of_box(image, path[f]))
                return shirt_accepts(letters, label)
        return check

    from ultralytics import YOLO
    detector = YOLO(args.detector)
    finder = None
    if args.ball_candidates and args.ball_reranker:
        from ball_finder import BallFinder
        finder = BallFinder(args.ball_candidates, args.ball_reranker, args.detector, args.camera)

    def snap_box(frame, expected):
        """Put the tracking box on a person the detector really sees: search around the expected place and take the detection closest to it (about the same height).
        Returns None when nobody is there, so the picture never shows an empty box."""
        height = max(20.0, expected[3] - expected[1])
        cx, cy = (expected[0] + expected[2]) / 2, (expected[1] + expected[3]) / 2
        half = max(2.5 * height, 150.0)
        x0, y0 = int(max(0, cx - half)), int(max(0, cy - half))
        crop = frame[y0:int(cy + half), x0:int(cx + half)]
        if crop.size == 0:
            return None
        found = detector.predict(crop, device=0, imgsz=640, conf=0.05, classes=[0], verbose=False)[0]
        best, best_distance = None, 0.8 * height
        for box in found.boxes.xyxy.cpu().numpy() if found.boxes is not None else []:
            bx = [float(box[0] + x0), float(box[1] + y0), float(box[2] + x0), float(box[3] + y0)]
            size = (bx[3] - bx[1]) / height
            distance = ((((bx[0] + bx[2]) / 2 - cx) ** 2 + ((bx[1] + bx[3]) / 2 - cy) ** 2) ** 0.5)
            if 0.55 <= size <= 1.8 and distance < best_distance:
                best, best_distance = bx, distance
        return best

    board = Board(pitch, args.direction)
    parts, writer, last_image = [], [None], [None]

    def open_part(name):
        path = out / f'part_{name}.mp4'
        parts.append(path)
        if path.exists() and (out / f'part_{name}.done').exists():
            return False
        writer[0] = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*'mp4v'), FPS_OUT, OUT)
        return True

    def close_part(name):
        writer[0].release()
        (out / f'part_{name}.done').write_text('ok')
        last_image[0] = None

    def put(image, repeat=1):
        for _ in range(repeat):
            writer[0].write(image)
        last_image[0] = image

    def hold(image, seconds):
        put(image, int(seconds * FPS_OUT))

    def fade_to(image, frames=4):
        if last_image[0] is not None:
            for k in range(1, frames + 1):
                writer[0].write(cv2.addWeighted(last_image[0], 1 - k / (frames + 1), image, k / (frames + 1), 0))

    def board_state(t):
        """The 11 v 11 board at time t: smooth positions of the seen players, dashed circles for the others (last seen up to a minute ago, else from the team shape)."""
        tf = (t - offset) * fps
        seen, predicted = {'A': [], 'B': []}, {'A': [], 'B': []}
        for name in ('A', 'B'):
            lost = []
            for tid, team in team_of_track.items():
                if team != name:
                    continue
                position = smooth_at(seen_frames[tid], metre_at[tid], tf)
                if position is not None:
                    seen[name].append((tid, position[0], position[1]))
                else:
                    index = bisect.bisect_left(seen_frames[tid], tf) - 1
                    if index >= 0 and tf - seen_frames[tid][index] <= 60 * fps:
                        lost.append((tf - seen_frames[tid][index], tid, seen_frames[tid][index]))
            seen[name] = sorted(seen[name], key=lambda p: -len(seen_frames[p[0]]))[:11]
            now = centre(name, int(round(tf)))
            for _age, tid, frame in sorted(lost):
                if len(seen[name]) + len(predicted[name]) >= 11:
                    break
                x, y = metre_at[tid][frame]
                before = centre(name, frame)
                if now and before:
                    x, y = x + now[0] - before[0], y + now[1] - before[1]
                if abs(x) <= pitch['length'] / 2 and abs(y) <= pitch['width'] / 2 and all(((x - sx) ** 2 + (y - sy) ** 2) ** 0.5 > 3.0 for _t, sx, sy in seen[name]) \
                        and all(((x - px) ** 2 + (y - py) ** 2) ** 0.5 > 2.5 for px, py in predicted[name]):
                    predicted[name].append((x, y))
            if seen[name] and len(seen[name]) + len(predicted[name]) < 11:
                present = [(x, y) for _t, x, y in seen[name]] + predicted[name]
                predicted[name] += [(g['x'], g['y']) for g in estimate_missing(present, [], pitch, 11, fill_holes=True)]
        return seen, predicted

    if open_part('00'):
        hold(index_card(f'{team_name} {args.half_name} 리뷰', [(clock(e['time']), KIND_OF[e['polarity']], index_title(e, clock(e['time']))) for e in events],
                        None), 6)
        close_part('00')
    markdown = [f'# {team_name} {args.half_name} 리뷰', '']
    for number, event in enumerate(events, 1):
        t0, end = event['time'], event['end']
        first_f, last_f = int(round((t0 - LEAD - offset) * fps)), int(round((end - offset) * fps))
        key_label = args.team if event['team'] == 'team' else other
        mean_u = {}
        for (tid, name), path in paths_by_track.items():
            inside = [x * sign[name] for f, x, _y in path if first_f <= f <= last_f]
            if name == key_label and len(inside) >= 0.3 * (last_f - first_f):
                mean_u[tid] = sum(inside) / len(inside)
        key_tid, key_path = choose_key_track(result['tracks'], event['track'], key_label, first_f, last_f, mean_u, accept=shirt_matches(key_label))
        ys = [metre_at[key_tid][f][1] for f in range(first_f, last_f + 1) if key_tid in metre_at and f in metre_at[key_tid]] if key_tid else []
        side = ('near' if sum(ys) / len(ys) > 12 else 'far' if sum(ys) / len(ys) < -12 else 'centre') if ys else None
        tf0 = int(round((t0 - offset) * fps))
        key_xy = metre_at.get(key_tid, {}).get(tf0) if key_tid else None
        rows = by_frame.get(tf0, {})
        near_enemy = sum(1 for _t, x, y in rows.get('A' if key_label == 'B' else 'B', []) if key_xy and ((x - key_xy[0]) ** 2 + (y - key_xy[1]) ** 2) ** 0.5 <= 10) if key_xy else 0
        near_own = sum(1 for tid, x, y in rows.get(key_label, []) if key_xy and tid != key_tid and ((x - key_xy[0]) ** 2 + (y - key_xy[1]) ** 2) ** 0.5 <= 12) if key_xy else 0
        at_end = by_frame.get(int(round(((event.get('goal_at') or end) - offset) * fps)) - step_frames, {})
        box = box_presence([(x * args.direction, y) for _t, x, y in at_end.get(args.team, [])], [(x * args.direction, y) for _t, x, y in at_end.get(other, [])], pitch['length'])
        facts = {'side': side, 'back_line': series_team.get(int(t0 - offset), {}).get('opponent_back_line', 20), 'defenders_near': near_enemy, 'support_near': near_own,
                 'box_ours': box['ours'], 'box_theirs': box['theirs'], 'speed_kmh': event.get('speed_kmh')}
        detail = analysis(event, facts)
        subs = captions(event, facts)
        kind = KIND_OF[event['polarity']]
        sub = f'{args.half_name} {clock(t0)}'
        part = f'{number:02d}'
        if open_part(part):
            files = extract_frames(args.ffmpeg, args.video, t0 - LEAD, end - t0 + LEAD, FPS_OUT, out / 'frames')

            def frame_at(t):
                index = max(0, min(len(files) - 1, int(round((t - (t0 - LEAD)) * FPS_OUT))))
                return cv2.imread(str(files[index]))

            def expected_at(track_frame):
                return key_path.get(track_frame) or next((key_path[track_frame + d] for d in (-1, 1, -2, 2, -3, 3, -4, 4, -5, 5) if track_frame + d in key_path), None)

            verified_cache = {}

            def box_at(track_frame, t=None):
                """The box of the followed player, confirmed by the detector on the picture of that moment (None when nobody is there)."""
                expected = expected_at(track_frame)
                if expected is None or t is None:
                    return expected
                if t not in verified_cache:
                    verified_cache[t] = snap_box(frame_at(t), expected)
                return verified_cache[t]

            ball_at = {}
            if finder is not None:
                images = [(t_i, cv2.imread(str(files[t_i]))) for t_i in range(int(max(0, (t0 - 2.0 - (t0 - LEAD)) * FPS_OUT)), len(files), 2)]
                if images:
                    found = finder.path([image for _i, image in images][:90])
                    ball_at = {round((t0 - LEAD) + images[i][0] / FPS_OUT, 1): (x, y) for i, (x, y, _p) in found.items()}

            def ball_for(t):
                return ball_at.get(round(round(t * 5) / 5, 1))

            def with_caption(image, t):
                text = next((text for off, dur, text in subs if t0 + off <= t < t0 + off + dur), None)
                return caption(image, text) if text else image

            # 1. wide: the whole picture, a thin tracking box, subtitles; a little slow motion around the moment
            for k, t in enumerate([t0 - 3.0 + k / FPS_OUT for k in range(int(4.0 * FPS_OUT))]):
                tf = int(round((t - offset) * fps))
                shot = with_caption(wide_shot(frame_at(t), box_at(tf, t), None, event['title'] if k < 22 else None, kind, sub, ball_for(t)), t)
                if k == 0:
                    fade_to(shot)
                put(shot, 2 if abs(t - t0) <= 0.7 else 1)
            # 2. the close-up follows the player all the way through the sequence
            if key_path:
                follow_end = min(end, t0 + 1.0 + ZOOM_MAX)
                last_box, missing = None, 0
                for k, t in enumerate([t0 + 1.0 + k / FPS_OUT for k in range(int((follow_end - t0 - 1.0) * FPS_OUT))]):
                    tf = int(round((t - offset) * fps))
                    b = box_at(tf, t)
                    if b is not None:
                        last_box, missing = b, 0
                    else:
                        missing += 1
                    if b is None and (last_box is None or missing > 10):
                        shot = with_caption(wide_shot(frame_at(t), None, None, None, kind, sub, ball_for(t)), t)             # the player is lost for more than a second: show the whole picture
                    else:
                        shot = with_caption(zoom_shot(frame_at(t), b or last_box, '핵심 선수를 따라갑니다' if k < 20 else None, kind, sub, draw_box=b is not None, ball=ball_for(t)), t)
                    if k == 0:
                        fade_to(shot)
                    put(shot)
            else:
                for k, t in enumerate([t0 + 1.0 + k / FPS_OUT for k in range(int((min(end, t0 + 10.0) - t0 - 1.0) * FPS_OUT))]):
                    put(with_caption(wide_shot(frame_at(t), None, None, None, kind, sub, ball_for(t)), t))
            # 3. the board, for one or two moments only
            if (number - 1) in board_for:
                for k, t in enumerate([t0 - 3.0 + k / FPS_OUT for k in range(int(7.0 * FPS_OUT))]):
                    seen, predicted = board_state(t)
                    metrics = series_team.get(int(t - offset))
                    shot = board.frame(seen, predicted, key_tid, metrics['opponent_back_line'] if metrics else None, '상황 보드 · 11 대 11' if k < 22 else None, kind, '같은 장면을 위에서 본 모습')
                    if k == 0:
                        fade_to(shot)
                    put(shot)
            # 4. the analysis
            card = analysis_card(event['title'], detail['summary'], detail['good'], detail['fix'], detail['next'], kind, f'{number} / {len(events)}  ·  {sub}')
            fade_to(card)
            hold(card, 9)
            tips = coaching(event, facts)
            hold(rules_card(tips['title'], tips['rules'], tips['drill'], kind, f'{number} / {len(events)}  ·  {sub}'), 11)
            close_part(part)
        markdown += [f'## {sub}  {event["title"]}' + (' → 골' if event['goal_follow'] else ''), '', f'- {detail["summary"]}', '- 잘한 점'] + [f'  - {b}' for b in detail['good']] + ['- 보완할 점'] + [f'  - {b}' for b in detail['fix']] + [f'- 다음에는: {detail["next"]}', f'- {coaching(event, facts)["title"]}'] + [f'  - {r}' for r in coaching(event, facts)['rules']] + [f'- 훈련: {coaching(event, facts)["drill"]["name"]}'] + [f'  - {x}' for x in coaching(event, facts)['drill']['setup']] + [f'  - 코칭 포인트: {coaching(event, facts)["drill"]["focus"]}', '']
        event['analysis'], event['key_track'], event['side'], event['facts'] = detail, key_tid, side, facts
    points = half_summary(events)
    if open_part('zz'):
        hold(bullet_card(f'{args.half_name} 한눈에', points, 'info', '이 하프에서 가져갈 것', None), 10)
        close_part('zz')
    markdown += ['## 이 하프에서 가져갈 것', ''] + [f'- {p}' for p in points] + ['']
    listing = out / 'parts.txt'
    listing.write_text(chr(10).join(f"file '{part.name}'" for part in parts), encoding='utf-8')
    subprocess.run([args.ffmpeg, '-hide_banner', '-loglevel', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', str(listing), '-c:v', 'libx264', '-preset', 'medium', '-crf', '20',
                    '-pix_fmt', 'yuv420p', str(out / 'review.mp4')], check=True)
    for leftover in list(out.glob('part_*')) + [listing]:
        leftover.unlink(missing_ok=True)
    shutil.rmtree(out / 'frames', ignore_errors=True)
    (out / 'events.json').write_text(json.dumps(events, ensure_ascii=False, indent=1, default=str), encoding='utf-8')
    (out / 'review.md').write_text(chr(10).join(markdown), encoding='utf-8')
    print('wrote', out / 'review.mp4', '| moments', len(events), [e['kind'] for e in events])


if __name__ == '__main__':
    main()
