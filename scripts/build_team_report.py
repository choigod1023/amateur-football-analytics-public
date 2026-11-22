"""Video report for one team and one half: good and poor attacking scenes with the key player highlighted, a pop-up minimap and coaching text.

Usage: python scripts/build_team_report.py <tracks.json> <calibrations.json> <camera> <video> <output folder> --team B --direction 1
       [--half-name 후반] [--pitch-length 89 --pitch-width 62] [--reference-bg A B TX TY] [--shift-schedule "0:0,0;1950:0.3,0.3"]
       [--good 3] [--poor 3] [--window 15] [--ffmpeg ffmpeg]

--direction is the way the focus team attacks along the pitch length in minimap metres (+1 toward +x, -1 toward -x). The video
time of a track frame is first_second + frame / fps (from the tracks file). Output: report.mp4, report.md and scenes.json. There is no
ball in this data (see app/report_scenes.py): scenes are chosen by where and how the team stood and moved, and the texts say so.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from app.pitch_map import feet_to_metres, fit  # noqa: E402
from app.profile_teams import shirt_accepts  # noqa: E402
from app.team_style import short_name, team_name as team_name_of  # noqa: E402
from app.report_scenes import coaching_text, key_player, pick_windows, second_metrics, window_scores  # noqa: E402
from app.tactical_concepts import box_presence, line_change, local_balance, runs_in_behind, standing_still  # noqa: E402
import team_profile_cli  # noqa: E402
from build_tactical_report import clock, metre_rows  # noqa: E402
from build_team_minimap import parse_schedule, shift_at  # noqa: E402
from report_motion import choose_key_track  # noqa: E402
from report_video import ACCENTS, card, minimap_inset, scene_frame  # noqa: E402

OUT_FPS = 10
LEAD, TAIL = 3, 2          # seconds of play shown before and after the scene window


def extract_frames(ffmpeg, video, start, seconds, fps, folder):
    """Cut the frames of [start, start + seconds) at exactly `fps` per second with ffmpeg and return their files in order. Seeking with
    OpenCV is not frame exact and the recording does not report a steady frame rate, which let the overlay drift away from the picture."""
    folder = Path(folder)
    shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir(parents=True, exist_ok=True)
    subprocess.run([ffmpeg, '-hide_banner', '-loglevel', 'error', '-threads', '2', '-y', '-ss', f'{start:.3f}', '-t', f'{seconds:.3f}', '-i', video, '-vf', f'fps={fps}', '-q:v', '2', str(folder / 'f_%04d.jpg')],
                   check=True, creationflags=0x4000 if os.name == 'nt' else 0)
    return sorted(folder.glob('f_*.jpg'))


def series_of(by_frame, team, other, direction, fps, frames, minimum=7):
    series = {}
    for frame in range(0, frames, int(fps)):
        players = by_frame.get(frame, {})
        metrics = second_metrics(players.get(team, []), players.get(other, []), direction, minimum)
        if metrics:
            series[frame // int(fps)] = metrics
    return series


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('tracks')
    parser.add_argument('calibrations')
    parser.add_argument('camera')
    parser.add_argument('video')
    parser.add_argument('output')
    parser.add_argument('--team', choices=('A', 'B'), default='B')
    team_profile_cli.add_argument(parser)
    parser.add_argument('--direction', type=int, choices=(1, -1), required=True)
    parser.add_argument('--half-name', default='후반')
    parser.add_argument('--pitch-length', type=float)
    parser.add_argument('--pitch-width', type=float)
    parser.add_argument('--reference-bg', type=float, nargs=4)
    parser.add_argument('--shift-schedule')
    parser.add_argument('--good', type=int, default=3)
    parser.add_argument('--poor', type=int, default=3)
    parser.add_argument('--window', type=int, default=15)
    parser.add_argument('--goals', help='video seconds of goals scored by the focus team, comma separated; the report then shows these goals (the 25 s before and 3 s after) instead of picked scenes')
    parser.add_argument('--ball', help='ball paths from scripts/apply_ball_rerank.py: the ball is drawn where the path answers (red ring) and the team of the nearest player is named')
    parser.add_argument('--ffmpeg', default='ffmpeg')
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
    fps, offset = float(result['fps']), float(result['first_second'])
    other = 'A' if args.team == 'B' else 'B'
    schedule = parse_schedule(args.shift_schedule) if args.shift_schedule else []
    by_frame, _ = metre_rows(result['tracks'], fitted, schedule, tuple(args.reference_bg) if args.reference_bg else None, 0, result['frames'])
    ghosts_at = {}
    paths_by_track = {}
    for frame_number, teams in by_frame.items():
        for team_name, items in teams.items():
            for tid, x, y in items:
                paths_by_track.setdefault((tid, team_name), []).append((frame_number, x, y))
    for (tid, team_name), path in paths_by_track.items():
        path.sort()
        for (f0, x0, y0), (f1, _x1, _y1) in zip(path, path[1:]):
            for f in range(f0 + 1, min(f1, f0 + 51)):
                ghosts_at.setdefault(f, {}).setdefault(team_name, []).append((x0, y0))
        f_last, x_last, y_last = path[-1]
        for f in range(f_last + 1, f_last + 51):
            ghosts_at.setdefault(f, {}).setdefault(team_name, []).append((x_last, y_last))
    series = series_of(by_frame, args.team, other, args.direction, fps, result['frames'], 6 if args.goals else 7)
    if len(series) < 60:
        raise SystemExit('Fewer than 60 measured seconds: not enough to report.')
    scores = window_scores(series, args.window)
    scenes = []
    if args.goals:
        goal_scores = {w['start']: w for w in window_scores(series, 25)}
        for moment in [float(g) for g in args.goals.split(',')]:
            relative = int(moment - offset)
            window = goal_scores.get(relative - 22)
            if window is None:
                print(f'goal at {clock(moment)}: not enough measured seconds before it, skipped')
                continue
            leader = series.get(relative - 1, {}).get('leader')
            scenes.append({'kind': 'goal', 'start': window['start'], 'end': window['end'], 'video_start': offset + window['start'], 'phase': window['phase'], 'score': window['good'],
                           'player': leader, 'means': window['means'], 'text': coaching_text('goal', window), 'moment': moment})
    for kind, count in (() if args.goals else (('good', args.good), ('poor', args.poor))):
        for window in pick_windows(scores, kind, count, spacing=40, minimum=0.5 if kind == 'good' else 0.3):
            player = key_player(series, window, kind)
            scenes.append({'kind': kind, 'start': window['start'], 'end': window['end'], 'video_start': offset + window['start'], 'phase': window['phase'],
                           'score': window[kind], 'player': player, 'means': window['means'], 'text': coaching_text(kind, window)})
    scenes.sort(key=lambda s: (s['kind'] != 'good', s['start']))
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    name = {'good': '구조가 좋은 장면', 'poor': '보완할 장면', 'goal': '득점 장면'}
    tag = {'good': '구조가 좋은 장면', 'poor': '보완 장면', 'goal': '득점 장면'}
    ball_at = {}
    if args.ball:
        for clip in json.loads(Path(args.ball).read_text(encoding='utf-8')).values():
            for frame_name, (bx, by, probability) in clip['path'].items():
                ball_at[round(clip['start'] + (int(frame_name[2:5]) - 1) / clip['fps'], 1)] = (bx, by, probability)
    probe = cv2.VideoCapture(args.video)
    from app.team_role_features import FEATURE_NAMES, box_features
    neon_index = list(FEATURE_NAMES).index('neon')

    def shirt_matches(tid, path):
        if teams is not None:                        # the colours the coach chose decide, not the neon share of the first match
            frames = sorted(path)
            letters = []
            for f in (frames[len(frames) // 5], frames[len(frames) // 2], frames[4 * len(frames) // 5]):
                probe.set(cv2.CAP_PROP_POS_MSEC, (offset + f / fps) * 1000)
                ok, image = probe.read()
                if ok:
                    letters.append(teams.letter_of_box(image, path[f]))
            return shirt_accepts(letters, args.team)
        # without a profile: the followed player must look like his team: bright neon vests belong to team A, dark clothes to team B (checked on three frames)
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
        return mean < 0.10 if args.team == 'B' else mean >= 0.05

    writer = cv2.VideoWriter(str(out / 'raw.mp4'), cv2.VideoWriter_fourcc(*'mp4v'), OUT_FPS, (1280, 720))
    metre_at = {}
    for (tid, _team_name), path in paths_by_track.items():
        metre_at.setdefault(tid, {}).update({f: (x, y) for f, x, y in path})
    bg = tuple(args.reference_bg) if args.reference_bg else None
    step_frames = int(fps)
    pitch = fitted['pitch']
    back_line = {s: m['opponent_back_line'] for s, m in series.items()}
    u_paths = {tid: [(f, x * args.direction, y) for f, x, y in path] for (tid, team_name), path in paths_by_track.items() if team_name == args.team}

    def hold(image, seconds):
        for _ in range(int(seconds * OUT_FPS)):
            writer.write(image)

    # per scene: the player to follow, the side he works on and the football events read from the positions
    for scene in scenes:
        first_f, last_f = scene['start'] * step_frames, scene['end'] * step_frames
        mean_u = {}
        for (tid, team_name), path in paths_by_track.items():
            inside = [x * args.direction for f, x, _y in path if first_f <= f <= last_f]
            if team_name == args.team and len(inside) >= 0.3 * (last_f - first_f):
                mean_u[tid] = sum(inside) / len(inside)
        key_tid, key_path = choose_key_track(result['tracks'], scene['player'], args.team, first_f, last_f, mean_u, accept=shirt_matches)
        scene['key_track'], scene['key_path'] = key_tid, key_path
        ys = [metre_at[key_tid][f][1] for f in range(first_f, last_f + 1) if key_tid in metre_at and f in metre_at[key_tid]] if key_tid else []
        side = ('near' if sum(ys) / len(ys) > 12 else 'far' if sum(ys) / len(ys) < -12 else 'centre') if ys else None
        window_paths = {tid: [p for p in path if first_f - 25 <= p[0] <= last_f] for tid, path in u_paths.items()}
        window_paths = {tid: path for tid, path in window_paths.items() if len(path) >= 25}
        runs = [r for r in runs_in_behind(window_paths, back_line, fps) if scene['start'] <= r['end'] <= scene['end'] + 1]
        end_f = last_f - 2 * step_frames if scene['kind'] != 'goal' else int(round((scene['moment'] - offset) * fps)) - step_frames
        at_end = by_frame.get(end_f, {})
        events = {'runs': runs, 'measured_runs': len(window_paths) >= 4, 'line_change': line_change(back_line, scene['start'], scene['end'])}
        if key_tid in metre_at and end_f in metre_at[key_tid] and at_end.get(args.team):
            ours = [(x, y) for _t, x, y in at_end.get(args.team, [])]
            theirs = [(x, y) for _t, x, y in at_end.get(other, [])]
            events['balance'] = local_balance(ours, theirs, metre_at[key_tid][end_f], pitch_width=pitch['width'])
            events['box'] = box_presence([(x * args.direction, y) for x, y in ours], [(x * args.direction, y) for x, y in theirs], pitch['length'])
        frames_u = {f: [(t, x * args.direction, y) for team_name in ('A', 'B') for t, x, y in by_frame.get(f, {}).get(team_name, [])] for f in range(max(0, first_f), last_f + 1)}
        events['set_piece'] = standing_still(frames_u, max(0, first_f), last_f, pitch['length'], fps)
        scene['events'] = events
        scene['banners'] = [(offset + r['end'] - 3.0, offset + r['end'] + 1.0, '침투 포착') for r in runs]
        if scene['kind'] == 'goal':
            scene['banners'].append((scene['moment'] - 1.0, scene['moment'] + 2.0, '득점 순간'))
        scene['text'] = coaching_text(scene['kind'], {'phase': scene['phase'], 'means': scene['means'], 'side': side, 'events': events})
        scene['side'] = side

    team_label = team_name_of(style, args.team)
    goal_n = sum(s['kind'] == 'goal' for s in scenes)
    count_words = f'확정된 득점 장면 {goal_n}개' if goal_n else f'구조가 좋은 장면 {sum(s["kind"] == "good" for s in scenes)}개와 보완할 장면 {sum(s["kind"] == "poor" for s in scenes)}개'
    hold(card(f'{team_label} {args.half_name}', [
        ('이 리포트는', [f'{count_words}을 골라, 장면마다 상황 요약, 따라가는 핵심 선수, 이동 궤적, 잘한 점과 아쉬운 점, 조언, 선수에게 던질 질문 순서로 보여 드립니다. 마지막에는 이 하프에서 반복된 장점과 다음 경기 과제를 정리합니다.']),
        ('영상 읽는 법', ['노란 궤적과 화살표는 따라가는 핵심 선수의 최근 움직임입니다. 하단 왼쪽 화면은 그 선수를 확대해서 따라갑니다.',
                          '하단 오른쪽 미니맵의 가는 선은 최근 3초 동안의 선수 이동이고, 굵은 노란 선은 핵심 선수의 이동입니다. 빈 원은 최근 10초 안에 화면에서 사라진 선수의 마지막 위치입니다.']),
        ('먼저 알아 두실 점', ['공의 흐름은 따로 판정하지 않고 선수들의 위치와 움직임만으로 분석했습니다. 침투, 수비 라인 변화, 측면과 중원의 숫자 싸움, 박스 안 인원은 위치로 읽은 것이고 위치는 자동 측정값이라 오차가 있습니다.'])],
        f'{team_label} 기준 · 공격 방향 {"오른쪽" if args.direction == 1 else "왼쪽"}(미니맵)', ACCENTS['info'], tag='영상 분석 리포트'), 7)
    counts = {}
    for number, scene in enumerate(scenes, 1):
        accent = ACCENTS[scene['kind']]
        text = scene['text']
        ordinal = sum(1 for s in scenes[:number] if s['kind'] == scene['kind'])
        title = f'{args.half_name} {name[scene["kind"]]} {ordinal}  ·  {clock(scene["moment"] if scene["kind"] == "goal" else scene["video_start"])}'
        page = f'{number} / {len(scenes)}'
        hold(card(title, [('상황 요약', [text['summary']]), ('볼 포인트', [text['watch']])], f'{text["phase"]}', accent, tag=tag[scene['kind']], page=page), 5)
        begin = scene['video_start'] - LEAD
        frame_files = extract_frames(args.ffmpeg, args.video, begin, args.window + LEAD + TAIL, OUT_FPS, out / 'frames')
        key_path = scene['key_path']
        replay_from = (scene['moment'] if scene['kind'] == 'goal' else scene['video_start'] + args.window) - 8 - offset
        replay_cache = []

        def compose(frame, t, spotlight=False, replay=False):
            track_frame = int(round((t - offset) * fps))
            players = {team: by_frame.get(track_frame, {}).get(team, []) for team in ('A', 'B')}
            metrics = series.get(int(t - offset))
            box = key_path.get(track_frame) or next((key_path[track_frame + d] for d in (-1, 1, -2, 2, -3, 3, -5, 5) if track_frame + d in key_path), None)
            trail_px = [((key_path[f][0] + key_path[f][2]) / 2, key_path[f][3]) for f in range(track_frame - 20, track_frame + 1) if f in key_path]
            trails = {tid: [metre_at[tid][f] for f in range(track_frame - 15, track_frame + 1, 3) if f in metre_at.get(tid, {})] for team in players.values() for tid, _x, _y in team}
            key_trail = [metre_at[scene['key_track']][f] for f in range(track_frame - 30, track_frame + 1) if scene['key_track'] in metre_at and f in metre_at[scene['key_track']]]
            ball = None
            for shift in (0.0, -0.1, 0.1, -0.2, 0.2):
                ball = ball_at.get(round(round((t + shift) * 5) / 5, 1))
                if ball:
                    break
            ball_m = ball_note = None
            if ball:
                moved = feet_to_metres(fitted, [ball[0] - 2, ball[1] - 4, ball[0] + 2, ball[1]], 1920, 1080, shift_at(schedule, track_frame), bg)
                ball_m = tuple(moved) if moved else None
                near = []
                for tid, rows in result['tracks'].items():
                    for row in rows:
                        if abs(row['frame'] - track_frame) <= 1 and row['team'] in ('A', 'B'):
                            height = max(1.0, row['box'][3] - row['box'][1])
                            distance = ((((row['box'][0] + row['box'][2]) / 2 - ball[0]) ** 2 + (row['box'][3] - ball[1]) ** 2) ** 0.5) / height
                            if distance < 1.2:
                                near.append((distance, row['team']))
                            break
                ball_note = f'공 근처: {short_name(min(near)[1])}' if near else '공 위치(근처 선수 없음)'
            ghost_list = {}
            for team_name, items in ghosts_at.get(track_frame, {}).items():
                shown = [(x, y) for _tid, x, y in players.get(team_name, [])]
                ghost_list[team_name] = [g for g in items if all(((g[0] - sx) ** 2 + (g[1] - sy) ** 2) ** 0.5 > 3.0 for sx, sy in shown)][:12]
            inset = minimap_inset(pitch, players, scene['key_track'], args.team, metrics['opponent_back_line'] if metrics else None, args.direction,
                                  ball_m=ball_m, ghosts=ghost_list, trails=trails, key_trail=key_trail)
            subtitle = f'{text["phase"]}' + ('  ·  노란 궤적이 핵심 선수의 움직임입니다' if box is not None else '  ·  핵심 선수를 특정하지 못했습니다')
            banner = '하이라이트 리플레이 · 0.5배속' if replay else next((label for a, b, label in scene['banners'] if a <= t <= b), None)
            return scene_frame(frame, title, subtitle, inset, box, trail_px, spotlight, banner, ball[:2] if ball else None, ball_note, accent)

        for k, frame_file in enumerate(frame_files):
            frame = cv2.imread(str(frame_file))
            if frame is None:
                break
            t = begin + k / OUT_FPS                                  # the frames were cut at exact 0.1 s steps, so the time of a frame is known
            writer.write(compose(frame, t))
            if t - offset >= replay_from and len(replay_cache) < 100:
                replay_cache.append((t, cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 92])[1]))
        if replay_cache:
            hold(card('하이라이트 리플레이', [('다시 한 번, 천천히', ['핵심 선수 주변을 밝게 비추고 절반 속도로 다시 보여 드립니다. 노란 궤적을 따라 어디서 받고 어디로 움직이는지 확인해 보세요.'])], f'{title}', accent, tag='리플레이', page=page), 2)
            for t, encoded in replay_cache:
                image = compose(cv2.imdecode(encoded, cv2.IMREAD_COLOR), t, spotlight=True, replay=True)
                writer.write(image)
                writer.write(image)
        hold(card(f'{title}  ·  평가', [('columns', [('잘한 점', text['strengths']), ('아쉬운 점', text['cautions'])])], text['phase'], accent, tag=tag[scene['kind']], page=page), 8)
        hold(card(f'{title}  ·  제안', [('이렇게 해 보세요', [text['advice']]), ('선수들에게 던질 질문', [text['question']])], text['phase'], accent, tag='제안', page=page), 8)
        for key in ('strengths', 'cautions'):
            for sentence in text[key]:
                counts.setdefault(key, {}).setdefault(sentence, []).append(scene['video_start'])

    def repeated(key, limit=3):
        items = sorted(counts.get(key, {}).items(), key=lambda kv: -len(kv[1]))
        return [f'{sentence} ({len(times)}개 장면에서 반복)' if len(times) > 1 else sentence for sentence, times in items[:limit] if not sentence.startswith(('뚜렷하게', '이 장면의 위치에서는'))]

    hold(card(f'{team_label} {args.half_name} 요약', [('columns', [('반복해서 잘한 점', repeated('strengths') or ['뚜렷하게 반복된 장점은 찾지 못했습니다.']),
                                                                    ('반복해서 보인 보완점', repeated('cautions') or ['뚜렷하게 반복된 약점은 찾지 못했습니다.'])])],
              '선수 위치를 바탕으로 한 관찰이며 사람의 확인이 필요합니다.', ACCENTS['info'], tag='하프 요약'), 10)
    writer.release()
    subprocess.run([args.ffmpeg, '-hide_banner', '-loglevel', 'error', '-y', '-i', str(out / 'raw.mp4'), '-c:v', 'libx264', '-crf', '26', '-pix_fmt', 'yuv420p', str(out / 'report.mp4')], check=True)
    (out / 'raw.mp4').unlink()
    shutil.rmtree(out / 'frames', ignore_errors=True)
    for scene in scenes:
        scene.pop('key_path', None)
    (out / 'scenes.json').write_text(json.dumps(scenes, ensure_ascii=False, indent=1, default=str), encoding='utf-8')
    lines = [f'# {team_label} {args.half_name} 영상 분석 리포트', '', '선수들의 위치와 움직임만 바탕으로 한 관찰입니다. 공의 흐름은 영상으로 함께 확인해 주세요.', '']
    for number, scene in enumerate(scenes, 1):
        text = scene['text']
        moment = scene['moment'] if scene['kind'] == 'goal' else scene['video_start']
        lines += [f'## {number}. {name[scene["kind"]]} ({clock(moment)})', '', f'**상황 요약.** {text["summary"]}', '', '**잘한 점**'] + [f'- {p}' for p in text['strengths']] + ['', '**아쉬운 점**'] + [f'- {p}' for p in text['cautions']]
        lines += ['', f'**이렇게 해 보세요.** {text["advice"]}', '', f'**선수들에게 던질 질문.** {text["question"]}', '']
    lines += ['## 이 하프의 정리', '', '**반복해서 잘한 점**'] + [f'- {p}' for p in repeated('strengths')] + ['', '**반복해서 보인 보완점**'] + [f'- {p}' for p in repeated('cautions')] + ['']
    (out / 'report.md').write_text(chr(10).join(lines), encoding='utf-8')
    print('wrote', out / 'report.mp4', '| scenes', len(scenes))


if __name__ == '__main__':
    main()
