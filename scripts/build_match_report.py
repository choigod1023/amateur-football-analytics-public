"""A match analysis report for the players: annotated captures from the video, tactical diagrams drawn on a pitch, the rule for the situation and a drill.

Usage: python scripts/build_match_report.py <output folder> <calibrations.json> <video> <ffmpeg> --half "<name>|<tracks.json>|<camera>|<direction>|<offset>|<reference bg a,b,tx,ty>|<shift schedule>|<goals comma separated>" ...
       [--team B] [--title "..."] [--detector yolo11n.pt]

Writes one PNG per page (1920 x 1080) and pages.json; scripts/images_to_pdf.py joins the pages into a PDF. Everything is drawn from the positions of
the players in the recording: team and half summaries (where the team stood and attacked), one real capture per kind of situation with the lines, boxes and arrows
drawn on it, a clean tactical diagram of what the situation should look like, the rules for the player and one drill, and the research behind it.
"""
import argparse
import json
import math
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from app.event_miner import mine_events  # noqa: E402
from app.pitch_map import fit, pitch_lines  # noqa: E402
from app.review_text import coaching  # noqa: E402
from build_tactical_report import clock, metre_rows  # noqa: E402
from build_team_minimap import parse_schedule, shift_at  # noqa: E402
from build_team_report import series_of  # noqa: E402
from report_motion import box_path, choose_key_track  # noqa: E402
import team_profile_cli  # noqa: E402
from app.team_style import team_name as team_name_of  # noqa: E402
from review_shots import GOLD, INK, KEY_BGR, KIND_COLOURS, MUTED, NAVY, OUT, SIZE, TEAM_BGR, Draw, _bgr, _canvas, _pil, font, px, wrap  # noqa: E402

PANEL = (20, 29, 39)
TITLES = {'box_attack': '박스 침투 공격', 'run': '수비 라인 뒤 침투', 'conceded_run': '상대 침투 허용', 'isolated': '고립된 공격수', 'line_drop': '수비 라인 하락', 'goal': '득점 공격'}


# ---- geometry ---------------------------------------------------------------------------------------------------------------------
def metres_to_pixel(fitted, x, y, shift=(0.0, 0.0), bg=None, width=1920, height=1080):
    """The picture point of a place on the pitch (the inverse of pitch_map.feet_to_metres)."""
    inverse = np.linalg.inv(fitted['H'])
    v = inverse @ np.array([x, y, 1.0])
    u, w = v[0] / v[2], v[1] / v[2]
    px_, py_ = u * width, w * height
    if bg:
        a, b, tx, ty = bg
        det = a * a + b * b
        px_, py_ = (a * (px_ - tx) + b * (py_ - ty)) / det, (-b * (px_ - tx) + a * (py_ - ty)) / det
    return px_ + shift[0], py_ + shift[1]


class Pitch:
    """A small top-down pitch for diagrams: metres in, pixels out; the drawing is done on an OpenCV image."""

    def __init__(self, width, height, pitch, flip=False):
        self.w, self.h, self.pitch, self.flip = width, height, pitch, flip
        self.scale = min((width - 24) / pitch['length'], (height - 24) / pitch['width'])
        self.base = np.full((height, width, 3), (30, 52, 40), np.uint8)
        for line in pitch_lines(pitch):
            cv2.polylines(self.base, [np.array([self.p(x, y) for x, y in line], np.int32)], False, (220, 235, 225), max(1, width // 600), cv2.LINE_AA)

    def p(self, x, y):
        if self.flip:
            x = -x
        return int(self.w / 2 + x * self.scale), int(self.h / 2 + y * self.scale)

    def image(self):
        return self.base.copy()


def arrow(canvas, a, b, colour, thickness=3, tip=0.25):
    cv2.arrowedLine(canvas, a, b, colour, thickness, cv2.LINE_AA, tipLength=tip)


def dot(canvas, centre, colour, radius=9, ring=None):
    cv2.circle(canvas, centre, radius, colour, -1, cv2.LINE_AA)
    cv2.circle(canvas, centre, radius, NAVY[::-1], 1, cv2.LINE_AA)
    if ring:
        cv2.circle(canvas, centre, radius + 6, ring, 2, cv2.LINE_AA)


def dashed(canvas, a, b, colour, thickness=2, dash=14):
    length = math.hypot(b[0] - a[0], b[1] - a[1])
    count = max(1, int(length // dash))
    for k in range(0, count, 2):
        s, e = k / count, min(1.0, (k + 1) / count)
        cv2.line(canvas, (int(a[0] + (b[0] - a[0]) * s), int(a[1] + (b[1] - a[1]) * s)), (int(a[0] + (b[0] - a[0]) * e), int(a[1] + (b[1] - a[1]) * e)), colour, thickness, cv2.LINE_AA)


def label(canvas, text, xy, size=22, colour=(255, 255, 255), plate=True):
    image = _pil(canvas)
    d = Draw(image)
    face = font(size, True)
    width, height = d.d.textlength(text, font=face.real), face.real.size
    x = min(max(4, xy[0]), canvas.shape[1] - width - 8)
    y = min(max(2, xy[1]), canvas.shape[0] - height * 1.4)
    if plate:
        d.d.rectangle([x - 5, y - 2, x + width + 5, y + height * 1.3], fill=(11, 17, 24))
    d.d.text((x, y), text, font=face.real, fill=colour)
    canvas[:] = _bgr(image)


# ---- the data of a half ---------------------------------------------------------------------------------------------------------------
def load_half(spec, calibrations, team):
    name, tracks_path, camera, direction, offset, bg, schedule, goals = spec.split('|', 7)
    other = 'A' if team == 'B' else 'B'
    result = json.loads(Path(tracks_path).read_text(encoding='utf-8'))
    record = calibrations[camera]
    fitted = fit(record)
    if 'H' not in fitted:
        raise ValueError('Calibration refused: ' + fitted.get('error', 'unknown'))
    bg_values = tuple(float(v) for v in bg.split(',')) if bg else None
    sched = parse_schedule(schedule) if schedule else []
    direction = int(direction)
    evidence = {}
    by_frame, _ = metre_rows(result['tracks'], fitted, sched, bg_values, 0, result['frames'], evidence=evidence)
    fps, offset = float(result['fps']), float(offset)
    series_team = series_of(by_frame, team, other, direction, fps, result['frames'], 6)
    series_other = series_of(by_frame, other, team, -direction, fps, result['frames'], 6)
    sign = {team: direction, other: -direction}
    paths = {n: {} for n in (team, other)}
    for frame, teams in by_frame.items():
        for n, items in teams.items():
            for tid, x, y in items:
                paths[n].setdefault(tid, []).append((frame, x * sign[n], y))
    for n in paths:
        for tid in paths[n]:
            paths[n][tid].sort()
    goal_list = [float(g) for g in goals.split(',') if g.strip()]
    events = mine_events(paths[team], paths[other], series_team, series_other, goal_list, fps, offset, 10, pitch_length=fitted['pitch']['length'])
    return {'name': name, 'result': result, 'fitted': fitted, 'direction': direction, 'bg': bg_values, 'schedule': sched, 'by_frame': by_frame, 'fps': fps, 'offset': offset,
            'series_team': series_team, 'series_other': series_other, 'events': events, 'goals': goal_list, 'camera': camera,
            'evidence': {**evidence, 'policy': 'observed_only', 'pitch_dimensions_are_estimates': record.get('pitch_dimensions_are_estimates', True)}}


def cut_frame(ffmpeg, video, second, target):
    subprocess.run([ffmpeg, '-hide_banner', '-loglevel', 'error', '-y', '-ss', f'{second:.3f}', '-i', video, '-frames:v', '1', '-q:v', '2', str(target)], check=True)
    return cv2.imread(str(target))


def annotate(frame, half, event, key_path, label_text, wide=1.0):
    """Draw on a capture and crop it to where the play is: every tracked player as a thin box in the team colour, the opponent back line (dashed gold),
    the followed player (thick box and an arrow along his path)."""
    image = frame.copy()
    result, fitted = half['result'], half['fitted']
    fps, offset = half['fps'], half['offset']
    tf = int(round((event['time'] - offset) * fps))
    boxes = []
    for tid, rows in result['tracks'].items():
        for row in rows:
            if row['frame'] == tf and row['team'] in ('A', 'B'):
                b = [int(v) for v in row['box']]
                boxes.append(b)
                cv2.rectangle(image, (b[0], b[1]), (b[2], b[3]), TEAM_BGR[row['team']], 1, cv2.LINE_AA)
                break
    labels = []
    key_box = None
    if key_path:
        near = min(key_path, key=lambda f: abs(f - tf))
        key_box = [int(v) for v in key_path[near]]
        boxes.append(key_box)
    # the crop: the players with room around them, 16:9
    if boxes:
        xs = sorted(b[0] for b in boxes) + sorted(b[2] for b in boxes)
        ys = sorted(b[1] for b in boxes) + sorted(b[3] for b in boxes)
        x0, x1 = xs[len(boxes) // 10], xs[-1 - len(boxes) // 10]
        y0, y1 = ys[len(boxes) // 10], ys[-1 - len(boxes) // 10]
    else:
        x0, x1, y0, y1 = 300, 1600, 450, 800
    width = max(x1 - x0 + 220, 640) * wide
    width = min(width, image.shape[1])
    height = width * 9 / 16
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2 - 70
    left = int(min(max(0, cx - width / 2), image.shape[1] - width))
    top = int(min(max(0, cy - height / 2), image.shape[0] - height))
    crop = (left, top, int(width), int(height))
    # the opponent back line, projected from metres
    metrics = half['series_team'].get(int(event['time'] - offset))
    if metrics:
        shift = shift_at(half['schedule'], tf)
        line = []
        for y in range(-31, 32, 2):
            a_, b_ = metres_to_pixel(fitted, metrics['opponent_back_line'] * half['direction'], y, shift, half['bg'])
            line.append((int(a_), int(b_)))
        for k in range(0, len(line) - 1):
            if k % 2 == 0:
                cv2.line(image, line[k], line[k + 1], GOLD[::-1], 3, cv2.LINE_AA)
        inside = [pt for pt in line if left + 40 < pt[0] < left + width - 160 and top + 40 < pt[1] < top + height - 40]
        if inside:
            spot = min(inside, key=lambda pt: abs(pt[0] - (left + width * 0.78)))
            labels.append(('상대 수비 라인', (spot[0] + 8, spot[1] - 30), 14, GOLD))
    if key_box:
        x1_, y1_, x2_, y2_ = key_box
        cv2.rectangle(image, (x1_ - 4, y1_ - 4), (x2_ + 4, y2_ + 4), KEY_BGR, 3, cv2.LINE_AA)
        before, after = key_path.get(tf - 8) or key_path[min(key_path)], key_path.get(tf + 12) or key_path[max(key_path)]
        start = (int((before[0] + before[2]) / 2), int(before[3]))
        end = (int((after[0] + after[2]) / 2), int(after[3]))
        if math.hypot(end[0] - start[0], end[1] - start[1]) > 10:
            arrow(image, start, end, KEY_BGR, 4, 0.14)
        labels.append((label_text, (x1_ - 20, y1_ - 34), 14, (255, 200, 87)))
    cropped = image[top:top + int(height), left:left + int(width)].copy()
    for text, (lx, ly), size, colour in labels:
        label(cropped, text, (lx - left, ly - top), size, colour)
    return cropped


def crop_around(image, centre, width=1100, height=620):
    x0 = int(min(max(0, centre[0] - width / 2), image.shape[1] - width))
    y0 = int(min(max(0, centre[1] - height / 2), image.shape[0] - height))
    return image[y0:y0 + height, x0:x0 + width]


# ---- page building ---------------------------------------------------------------------------------------------------------------------
class Page:
    def __init__(self, title, tag=None, kind='info', number=None):
        self.image = _canvas(NAVY)
        self.draw = Draw(self.image)
        self.kind = kind
        colour = KIND_COLOURS[kind]
        self.draw.rectangle([56, 40, 64, 104], fill=colour)
        if tag:
            self.draw.text((84, 34), tag, font=font(17, True), fill=colour)
        self.draw.text((84, 56), title, font=font(36, True), fill=INK)
        if number:
            self.draw.text((1180, 686), f'{number}', font=font(15), fill=MUTED)
        self.draw.text((56, 686), 'Football Coach · 경기 분석 보고서', font=font(14), fill=MUTED)

    def panel(self, box):
        self.draw.rounded_rectangle(box, radius=14, fill=PANEL)

    def bullets(self, x, y, items, width, size=23, colour=None, gap=14):
        colour = colour or KIND_COLOURS[self.kind]
        face = font(size)
        for item in items:
            lines = wrap(item, face, width - 26)
            self.draw.ellipse([x, y + size * 0.45, x + 9, y + size * 0.45 + 9], fill=colour)
            for line in lines:
                self.draw.text((x + 24, y), line, font=face, fill=INK)
                y += size * 1.45
            y += gap
        return y

    def heading(self, x, y, text, colour=None, size=26):
        self.draw.text((x, y), text, font=font(size, True), fill=colour or KIND_COLOURS[self.kind])

    def paste(self, bgr, x, y, w, h):
        """Place an OpenCV image at logical coordinates, scaled to a logical width and height."""
        pixel = cv2.resize(bgr, (px(w), px(h)), interpolation=cv2.INTER_AREA)
        pil = _pil(pixel)
        self.image.paste(pil, (px(x), px(y)))

    def result(self):
        return _bgr(self.image)


def team_map(half, team, direction_sign):
    """A heat map of where a team stood during the half, on a pitch, with its mean defence, midfield and attack lines (in the direction the team attacks)."""
    pitch = half['fitted']['pitch']
    board = Pitch(900, 590, pitch)
    heat = np.zeros((board.h, board.w), np.float32)
    for frame, teams in half['by_frame'].items():
        for tid, x, y in teams.get(team, []):
            cx, cy = board.p(x * half['direction'], y)
            if 0 <= cx < board.w and 0 <= cy < board.h:
                heat[cy, cx] += 1
    heat = cv2.GaussianBlur(heat, (0, 0), 18)
    heat = heat / max(1e-6, heat.max())
    colour = cv2.applyColorMap((heat * 255).astype(np.uint8), cv2.COLORMAP_INFERNO)
    image = board.image()
    mask = (heat > 0.08)[..., None]
    image = np.where(mask, cv2.addWeighted(image, 0.35, colour, 0.65, 0), image)
    for line in pitch_lines(pitch):
        cv2.polylines(image, [np.array([board.p(x, y) for x, y in line], np.int32)], False, (235, 245, 238), 1, cv2.LINE_AA)
    series = half['series_team']
    for key, name in (('defence_line', '수비 라인'), ('middle_line', '중원 라인'), ('attack_line', '공격 라인')):
        values = [m[key] for m in series.values() if key in m]
        if values:
            u = sum(values) / len(values)
            a, b = board.p(u, -pitch['width'] / 2), board.p(u, pitch['width'] / 2)
            dashed(image, a, b, (255, 255, 255), 2, 12)
            label(image, name, (a[0] + 6, a[1] + 4), 18, (255, 255, 255))
    return image


def attack_map(half, team):
    """The paths of the followed players of the moments of a half, drawn as arrows on a pitch; goals are marked."""
    pitch = half['fitted']['pitch']
    board = Pitch(900, 590, pitch)
    image = board.image()
    fps, offset, result = half['fps'], half['offset'], half['result']
    metre = {}
    for frame, teams in half['by_frame'].items():
        for n, items in teams.items():
            for tid, x, y in items:
                metre.setdefault(tid, {})[frame] = (x, y)
    for event in half['events']:
        tid = event.get('track')
        if tid is None or tid not in metre:
            continue
        t0 = int(round((event['time'] - offset) * fps))
        pts = [(metre[tid][f][0] * half['direction'], metre[tid][f][1]) for f in range(t0 - 20, t0 + 40, 4) if f in metre[tid]]
        if len(pts) < 2:
            continue
        colour = {'good': (182, 196, 46), 'poor': (101, 138, 255), 'goal': GOLD[::-1]}[('goal' if event['kind'] == 'goal' or event.get('goal_follow') else ('poor' if event['polarity'] == 'poor' else 'good'))]
        points = [board.p(x, y) for x, y in pts]
        for a, b in zip(points, points[1:-1]):
            cv2.line(image, a, b, colour, 3, cv2.LINE_AA)
        arrow(image, points[-2], points[-1], colour, 3, 0.8)
        cv2.circle(image, points[0], 5, colour, -1, cv2.LINE_AA)
        label(image, clock(event['time']), (points[-1][0] + 6, points[-1][1] - 22), 17, (255, 255, 255))
    return image


DIAGRAM_TITLES = {'box_attack': '박스 안 세 자리를 나눠 섭니다', 'run': '수비 라인이 올라오는 순간 먼저 출발합니다', 'conceded_run': '한 명이 신호를 주고 라인이 함께 움직입니다',
                  'isolated': '앞선 선수 가까이에 15미터 안쪽 지원을 둡니다', 'line_drop': '라인을 올리고 내릴 때 함께 움직입니다', 'goal': '골 직후에도 라인을 올립니다'}


def diagram(kind, flip=False):
    """The clean tactical picture of a situation: what it should look like, in metres on a half pitch."""
    pitch = {'length': 89.0, 'width': 62.0}
    board = Pitch(900, 590, pitch)
    image = board.image()
    B, A = TEAM_BGR['B'], TEAM_BGR['A']

    def P(x, y):
        return board.p(x, y)
    if kind == 'box_attack':
        ball = P(30, 22)
        cv2.circle(image, ball, 7, (255, 255, 255), -1, cv2.LINE_AA)
        for name, (x, y), (dx, dy) in (('가까운 포스트', (40, 5), (43, 3)), ('먼 포스트', (40, -6), (43, -4)), ('뒤쪽(컷백)', (31, 0), (35, 2))):
            dot(image, P(x, y), B, 11, KEY_BGR)
            label(image, name, (P(x, y)[0] - 112, P(x, y)[1] - 10), 15, (255, 255, 255))
        dot(image, P(27, 22), B, 11)
        arrow(image, P(27, 22), P(40, 18), B, 3)
        arrow(image, P(30, 22), P(31, 4), (255, 255, 255), 2)
        for x, y in ((40, 2), (37, -3), (36, 8)):
            dot(image, P(x, y), A, 10)
        arrow(image, P(26, -10), P(36, -2), B, 3)
        dot(image, P(26, -10), B, 11)
        label(image, '반대편에서 대각선으로 진입', (P(4, -26)[0], P(4, -26)[1]), 15, (182, 255, 200))
    elif kind == 'run':
        for k, y in enumerate((-14, -5, 5, 14)):
            dot(image, P(20, y), A, 10)
        dashed(image, P(20, -28), P(20, 28), GOLD[::-1], 2, 14)
        label(image, '수비 라인', (P(20, -28)[0] + 8, P(20, -28)[1]), 15, GOLD)
        dot(image, P(8, 4), B, 12, KEY_BGR)
        arrow(image, P(8, 4), P(32, 2), KEY_BGR, 4)
        dot(image, P(-6, 14), B, 12)
        arrow(image, P(-6, 14), P(4, 8), (255, 255, 255), 2)
        label(image, '공 가진 선수의 신호', (P(-30, 22)[0], P(-30, 22)[1]), 15, (255, 255, 255))
    elif kind == 'conceded_run':
        for y in (-14, -5, 5, 14):
            dot(image, P(-10, y), B, 10, KEY_BGR if y == 5 else None)
            arrow(image, P(-10, y), P(-18, y), B, 3)
        label(image, '신호', (P(-10, 5)[0] - 4, P(-10, 5)[1] - 26), 15, (255, 200, 87))
        dot(image, P(-2, 8), A, 10)
        arrow(image, P(-2, 8), P(-22, 4), A, 3)
        dot(image, P(2, -2), A, 10)
        label(image, '가장 가까운 수비수가 먼저 따라붙음', (P(-40, -26)[0], P(-40, -26)[1]), 15, (182, 255, 200))
    elif kind == 'isolated':
        dot(image, P(30, 0), B, 12, KEY_BGR)
        for x, y, tx, ty in ((18, -9, 24, -6), (18, 9, 24, 6)):
            dot(image, P(x, y), B, 11)
            arrow(image, P(x, y), P(tx, ty), B, 3)
        cv2.circle(image, P(30, 0), int(15 * board.scale), (255, 255, 255), 1, cv2.LINE_AA)
        for x, y in ((38, -4), (36, 6)):
            dot(image, P(x, y), A, 10)
        label(image, '지원 반경 15미터', (P(30, 0)[0] - 56, P(30, 0)[1] + int(15 * board.scale) + 2), 15, (255, 255, 255))
    else:
        pass
    return image


def build(args):
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    calibrations = json.loads(Path(args.calibrations).read_text(encoding='utf-8'))
    halves = [load_half(spec, calibrations, args.team) for spec in args.half]
    style, _teams = team_profile_cli.setup(args)
    team_label = team_name_of(style, args.team)
    pages = []

    def save(page, name, links=None):
        path = out / f'page_{len(pages) + 1:02d}.png'
        cv2.imwrite(str(path), page.result())
        pages.append({'file': path.name, 'title': name, 'links': links or []})

    # 1. cover
    page = Page(args.title or f'{team_label} 경기 분석 보고서', '영상 분석 보고서', 'info')
    page.heading(84, 190, '이 보고서는', size=30)
    page.bullets(84, 240, ['경기 영상을 선수 위치로 읽어, 우리 팀이 어디에 서고 어떻게 공격했는지 정리했습니다', '장면마다 실제 영상 화면에 선과 상자를 그려 무슨 일이 있었는지 보여 줍니다',
                           '그 상황에서 선수가 어떻게 움직여야 하는지 행동 수칙과 훈련으로 이어 갑니다'], 1000, 26)
    page.heading(84, 470, '읽는 순서', size=26)
    page.bullets(84, 514, ['한눈에 보기 → 팀 구조와 공격 지도 → 상황별 전술(4가지) → 장점과 보완점 → 이번 주 훈련 → 연구 근거'], 1000, 22)
    save(page, '표지')

    # 2. at a glance
    counts = {}
    for half in halves:
        for e in half['events']:
            counts[e['kind']] = counts.get(e['kind'], 0) + 1
    boxes = [e for h in halves for e in h['events'] if e['kind'] == 'box_attack']
    goals_total = sum(len(h['goals']) for h in halves)
    territory = []
    for half in halves:
        values = [m['centre'] for m in half['series_team'].values()]
        territory.append(round(100 * sum(1 for v in values if v > 0) / max(1, len(values))))
    page = Page('한눈에 보기', '요약', 'good')
    page.panel([56, 130, 620, 660])
    page.heading(84, 148, '경기에서 확인된 것')
    page.bullets(84, 196, [f'영상으로 확인한 우리 팀 득점은 {goals_total}개입니다(두 번째 카메라 구간 제외)', f'박스 안으로 사람이 모인 공격 {len(boxes)}번 중 {sum(1 for e in boxes if e["goal_follow"])}번이 골로 이어졌습니다',
                           f'팀이 상대 진영에 머문 시간은 {halves[0]["name"]} {territory[0]}%' + (f', {halves[1]["name"]} {territory[1]}%' if len(territory) > 1 else ''),
                           f'상대 침투를 허용한 장면 {counts.get("conceded_run", 0)}번, 앞선 선수가 홀로 남은 장면 {counts.get("isolated", 0)}번'], 520, 23)
    page.panel([660, 130, 1224, 660])
    page.heading(688, 148, '가장 먼저 가져갈 세 가지', KIND_COLOURS['info'])
    page.bullets(688, 196, ['공격은 박스 안 세 자리(가까운 포스트, 먼 포스트, 뒤쪽)를 나눠 서면 더 위협적입니다', '수비 라인은 한 명이 신호를 주고 같이 올리고 내려야 뒷공간을 주지 않습니다',
                            '앞선 선수 가까이에 15미터 안쪽 지원을 만들어 홀로 남지 않게 합니다'], 520, 23, KIND_COLOURS['info'])
    save(page, '한눈에 보기')

    # 3-4. team structure and attack map per half
    for half in halves:
        page = Page(f'{half["name"]} 팀 구조와 공격 지도', '팀 구조', 'info')
        page.paste(team_map(half, args.team, half['direction']), 56, 130, 560, 367)
        page.paste(attack_map(half, args.team), 640, 130, 560, 367)
        page.draw.text((56, 504), '활동 지도(밝을수록 오래 머문 곳)와 평균 라인(오른쪽이 공격 방향)', font=font(16, True), fill=MUTED)
        page.draw.text((640, 504), '장면별 핵심 선수의 이동 (청록 좋은 장면 · 주황 아쉬운 장면 · 금색 골)', font=font(16, True), fill=MUTED)
        lines = []
        series = half['series_team']
        ahead = round(100 * sum(1 for m in series.values() if m['centre'] > 0) / max(1, len(series)))
        if series:
            attack = sum(m['attack_line'] for m in series.values()) / len(series)
            defence = sum(m['defence_line'] for m in series.values()) / len(series)
            lines = [f'팀의 중심이 상대 진영에 있던 시간은 {ahead}%였고, 공격 라인과 수비 라인의 평균 간격은 약 {int(round(attack - defence))}미터였습니다']
        page.bullets(56, 544, lines + ['간격이 너무 벌어지면 공을 잃었을 때 수비와 공격 사이가 비어 되찾기 어려워집니다'], 1130, 21, KIND_COLOURS['info'], 6)
        save(page, f'{half["name"]} 팀 구조')

    # team level tactics from the positions (shape, zones, open sides, activity, surges)
    from tactics_pages import add_pages  # noqa: E402
    add_pages(halves, args.team, Page, save, clock)

    # 5-.. situations: one capture each
    probe = cv2.VideoCapture(args.video)
    drills = {}
    wanted = [('box_attack', 'good'), ('run', 'good'), ('conceded_run', 'poor'), ('isolated', 'poor')]
    used = set()
    picks = []
    for kind, polarity in wanted:
        for half in halves:                                   # one situation of every kind from each half, so that neither half is left out
            found = sorted([e for e in half['events'] if e['kind'] == kind], key=lambda e: (-int(e.get('goal_follow', False)), -e['strength']))
            if found:
                picks.append((kind, polarity, (half, found[0])))
    for kind, polarity, pick in picks:
        half, event = pick
        fps, offset = half['fps'], half['offset']
        first_f, last_f = int(round((event['time'] - 4 - offset) * fps)), int(round((event['time'] + 6 - offset) * fps))
        mean_u = {}
        for tid, rows in half['result']['tracks'].items():
            pts = [r for r in rows if first_f <= r['frame'] <= last_f and r['team'] in ('A', 'B')]
            if len(pts) >= 20:
                mean_u[tid] = sum(r['box'][0] for r in pts) / len(pts)
        key_tid, key_path = choose_key_track(half['result']['tracks'], event.get('track'), args.team if event['team'] == 'team' else ('A' if args.team == 'B' else 'B'), first_f, last_f, mean_u)
        frame = cut_frame(args.ffmpeg, args.video, event['time'], out / f'capture_{kind}_{halves.index(half)}.jpg')
        text = '앞선 선수' if kind != 'conceded_run' else '뛰어드는 상대'
        crop = annotate(frame, half, event, key_path, text)
        tips = coaching({'kind': kind}, {'defenders_near': 0})
        tone = 'good' if polarity == 'good' else 'poor'
        page = Page(f'{TITLES[kind]}: 이럴 때는 이렇게', f'상황 {len(used) + 1} · {half["name"]} {clock(event["time"])}', tone)
        page.paste(crop, 56, 124, 700, 395)
        page.draw.text((56, 523), '얇은 상자: 선수 · 금색 점선: 상대 수비 라인 · 굵은 상자와 화살표: 앞선 선수의 움직임', font=font(15), fill=MUTED)
        page.paste(diagram(kind), 780, 124, 444, 291)
        page.draw.text((780, 418), '이상적인 모양: ' + DIAGRAM_TITLES[kind], font=font(15, True), fill=MUTED)
        page.panel([780, 446, 1224, 664])
        page.heading(800, 456, '이렇게 움직이세요', size=21)
        yy = 486
        for number, rule in enumerate(tips['rules'][:3], 1):
            lines = wrap(rule, font(16), 396)
            page.draw.text((800, yy), f'{number}.', font=font(16, True), fill=KIND_COLOURS[tone])
            for line in lines:
                page.draw.text((820, yy), line, font=font(16), fill=INK)
                yy += 22
            yy += 4
        from app.review_text import analysis as scene_analysis  # noqa: E402
        detail = scene_analysis({'kind': kind, 'goal_follow': event.get('goal_follow', False)}, {'side': None, 'back_line': half['series_team'].get(int(event['time'] - half['offset']), {}).get('opponent_back_line', 20),
                                                                                         'defenders_near': 0, 'support_near': 0, 'box_ours': 2, 'box_theirs': 0})
        drills.setdefault(kind, tips['drill'])
        page.panel([56, 550, 406, 664])
        page.heading(74, 554, '잘한 점', KIND_COLOURS['good'], 17)
        page.bullets(74, 578, detail['good'][:2], 316, 13, KIND_COLOURS['good'], 2)
        page.panel([414, 550, 764, 664])
        page.heading(432, 554, '보완할 점', KIND_COLOURS['poor'], 17)
        page.bullets(432, 578, detail['fix'][:2], 316, 13, KIND_COLOURS['poor'], 2)
        save(page, TITLES[kind])
        used.add((kind, half['name']))

    # every goal and the attacks that did not end in a goal, one page each: the picture with the passing lanes, the scene, the space, what went well and what to fix
    from app.attack_options import analyse, describe  # noqa: E402
    from app.review_text import attack_story  # noqa: E402
    from build_goal_check_video import draw_options, shirt_allowed  # noqa: E402
    team_other = 'A' if args.team == 'B' else 'B'
    moments = []
    for index, half in enumerate(halves):
        for g in half['goals']:
            moments.append((half, index, g, True, None))
        missed = [e for e in half['events'] if e['kind'] in ('box_attack', 'isolated') and not e.get('goal_follow') and all(abs(e['time'] - g) > 40 for g in half['goals'])]
        picked = []
        for e in sorted(missed, key=lambda e: -e['strength']):
            if len(picked) < 3 and all(abs(e['time'] - c['time']) > 30 for c in picked):
                picked.append(e)
        for e in picked:
            moments.append((half, index, e['time'], False, e))
    moments.sort(key=lambda m: (m[1], m[2]))
    summary_rows = []
    for half, index, t, is_goal, event in moments:
        option_time = t - 2.0 if is_goal else t + 1.5
        still = cut_frame(args.ffmpeg, args.video, option_time, out / f'moment_{index}_{int(t)}.jpg')
        frame_number = int(round((option_time - half['offset']) * half['fps']))
        allowed = shirt_allowed(half, still, frame_number, args.team)
        facts = analyse(half['by_frame'], args.team, team_other, half['direction'], half['fps'], half['offset'], option_time, allowed=allowed)
        if not facts:
            continue
        words = describe(half['by_frame'], args.team, team_other, half['direction'], half['fps'], half['offset'], option_time, facts, half['fitted']['pitch']['length'], half['fitted']['pitch']['width'], allowed)
        story = attack_story(facts, is_goal)
        lanes = facts['lanes']
        summary_rows.append((half['name'], t, is_goal, (words or {}).get('path', ''), sum(1 for l in lanes if l['open']), sum(1 for l in lanes if not l['open']), facts['goal_side']))
        tone = 'goal' if is_goal else 'poor'
        from app.review_text import attack_instructions  # noqa: E402
        page = Page(f'{half["name"]} {clock(t)} ' + ('득점' if is_goal else '골이 나오지 못한 공격'), '장면 분석', tone)
        page.paste(draw_options(still, half, facts, facts['frame'], '앞선 선수'), 56, 124, 640, 360)
        page.draw.text((56, 488), '주황: 앞선 선수 · 초록: 열린 패스길 · 빨강: 수비수가 막은 패스길 · 흰 원: 막는 수비수', font=font(13), fill=MUTED)
        page.panel([716, 124, 1224, 484])
        y = 134
        for heading, lines, colour in (('장면', (words or {}).get('scene', []), KIND_COLOURS['info']), ('공간', (words or {}).get('space', []), KIND_COLOURS['good'])):
            page.heading(736, y, heading, colour, 20)
            y += 30
            y = page.bullets(736, y, lines or ['위치가 충분히 잡히지 않아 설명하지 못했습니다'], 460, 15, colour, 4) + 6
        columns = [('잘한 점', story['good'][:3], KIND_COLOURS['good']), ('보완할 점', (story['fix'] or ['특별히 지적할 선택은 없었습니다'])[:3], KIND_COLOURS['poor']),
                   ('이렇게 움직이세요', attack_instructions(facts, is_goal)[:3], KIND_COLOURS['info'])]
        for k, (heading, lines, colour) in enumerate(columns):
            x = 56 + k * 394
            page.panel([x, 510, x + 380, 676])
            page.heading(x + 16, 514, heading, colour, 17)
            page.bullets(x + 16, 540, lines, 346, 13, colour, 3)
        save(page, f'{half["name"]} {clock(t)}')

    # the table of all of them
    if summary_rows:
        page = Page('골과 골이 나오지 못한 공격 한눈에', '정리', 'info')
        page.draw.text((56, 128), '시각', font=font(16, True), fill=MUTED)
        page.draw.text((190, 128), '공격 위치의 이동', font=font(16, True), fill=MUTED)
        page.draw.text((900, 128), '열린 길', font=font(16, True), fill=MUTED)
        page.draw.text((990, 128), '막힌 길', font=font(16, True), fill=MUTED)
        page.draw.text((1090, 128), '골문 쪽 수비', font=font(16, True), fill=MUTED)
        y = 158
        for name, t, is_goal, path, opened, blocked, ahead in summary_rows[:17]:
            colour = KIND_COLOURS['goal'] if is_goal else KIND_COLOURS['poor']
            page.draw.rectangle([56, y + 3, 62, y + 25], fill=colour)
            page.draw.text((74, y), f'{name} {clock(t)}' + (' 득점' if is_goal else ''), font=font(15, True), fill=INK)
            page.draw.text((190, y), (path[:46] + '...') if len(path) > 46 else path, font=font(14), fill=INK)
            page.draw.text((920, y), f'{opened}개', font=font(15), fill=KIND_COLOURS['good'])
            page.draw.text((1010, y), f'{blocked}개', font=font(15), fill=KIND_COLOURS['poor'])
            page.draw.text((1120, y), f'{ahead}명', font=font(15), fill=INK)
            y += 30
        page.draw.text((56, 676), '열린 길과 막힌 길은 앞선 선수를 기준으로 한 패스길 수이고, 검출된 선수 사이에서 센 값입니다.', font=font(14), fill=MUTED)
        save(page, '한눈에 정리')

    # strengths and weaknesses
    page = Page('장점과 보완점', '정리', 'info')
    page.panel([56, 130, 620, 660])
    page.heading(84, 148, '잘한 점', KIND_COLOURS['good'])
    page.bullets(84, 196, ['박스 안으로 사람이 모이는 공격이 골로 자주 이어졌습니다', '공격 라인을 상대 진영 깊숙이 올려 압박과 2선 공을 잡기 좋은 위치를 유지했습니다', '수비 라인 뒤로 먼저 출발하는 침투가 나왔습니다'], 520, 23, KIND_COLOURS['good'])
    page.panel([660, 130, 1224, 660])
    page.heading(688, 148, '보완할 점', KIND_COLOURS['poor'])
    page.bullets(688, 196, ['수비 라인이 함께 움직이지 못해 뒷공간을 내준 장면이 있었습니다', '앞선 선수가 홀로 남아 연결이 끊기는 장면이 있었습니다', '박스 안 인원이 적을 때는 마무리 선택지가 줄었습니다'], 520, 23, KIND_COLOURS['poor'])
    save(page, '장점과 보완점')

    # one slide for all the training: a drill for every situation of the report and the written sessions to read
    page = Page('훈련: 한 장으로 정리', '훈련', 'info')
    extra = {'box_attack': ['진행: 3분 x 4세트, 세트 사이 1분 휴식, 측면 시작 위치는 세트마다 좌우로 바꿈', '성공 기준: 크로스가 나가는 순간 박스 안에 세 자리(가까운 포스트, 먼 포스트, 뒤쪽)가 채워져 있음', '단계 올리기: 수비를 5명으로 늘리거나 공격은 두 터치로 제한'],
             'run': ['진행: 3분 x 4세트, 수비 라인이 올라오는 신호는 코치가 손으로 줌', '성공 기준: 침투하는 선수가 라인이 올라오는 순간 어깨 너머로 확인하고 출발', '단계 올리기: 수비 한 명이 늦게 따라 나오게 해서 오프사이드 위치를 신경 쓰게 함'],
             'conceded_run': ['진행: 3분 x 4세트, 수비 신호 담당(가운데 수비수)을 세트마다 교대', '성공 기준: 뒤로 뛰는 공격수에게 가장 가까운 수비수가 먼저 따라붙고 라인이 함께 내려감', '단계 올리기: 공격수를 한 명 더 넣어 신호가 늦으면 실점하게 함'],
             'isolated': ['진행: 3분 x 4세트, 공을 받는 순간마다 코치가 지원 거리를 줄자로 확인', '성공 기준: 공을 받은 공격수 주변 15미터 안에 동료가 있고, 공을 잃어도 바로 되찾음', '단계 올리기: 지원이 올라오는 시간을 3초 안으로 제한']}
    kinds = [k for k, _ in wanted]
    for k in kinds:
        if k not in drills:
            drills[k] = coaching({'kind': k}, {'defenders_near': 0})['drill']
    for number, k in enumerate(kinds):
        x, y = 56 + (number % 2) * 590, 120 + (number // 2) * 220
        page.panel([x, y, x + 578, y + 208])
        page.heading(x + 18, y + 8, f'{TITLES[k]}: {drills[k]["name"]}', KIND_COLOURS['info'], 18)
        yy = y + 40
        for item in drills[k]['setup'][:2]:
            for line in wrap(item, font(14), 540):
                page.draw.text((x + 20, yy), line, font=font(14), fill=INK)
                yy += 20
            yy += 4
        for line in wrap('코칭 포인트: ' + drills[k]['focus'], font(14, True), 540):
            page.draw.text((x + 20, yy + 2), line, font=font(14, True), fill=GOLD)
            yy += 20
        yy += 4
        for item in extra.get(k, [])[:3]:
            for line in wrap(item, font(13), 540):
                page.draw.text((x + 20, yy), line, font=font(13), fill=MUTED)
                yy += 18
            yy += 2
    links, y = [], 566
    page.draw.text((56, y), '더 읽어 볼 훈련 자료(PDF에서 눌러 열 수 있습니다)', font=font(15, True), fill=MUTED)
    y += 24
    for label_text, url in [('FIFA Training Centre: 5대3에서 5대5까지', 'https://www.fifatrainingcentre.com/en/practice/talent-coach-programme/create-and-finish/attack-vs-defence-from-5v3-to-5v5.php'),
                            ('Cupello: 크로스와 마무리', 'https://my.cupello.com/coaching/drills/crossing-and-finishing-phase-play'),
                            ('Sportplan: 수비 라인이 한 덩어리로 이동', 'https://www.sportplan.net/sketches/Football/openSketch/12067278'),
                            ('Cupello: 공격 방향 전환 세션', 'https://my.cupello.com/coaching/sessions/switching-play'),
                            ('World Class Coaching: 어깨 너머 확인 게임', 'https://worldclasscoaching.com/two-ball-check-your-shoulder-game-scanning-decision-making-drill/')]:
        page.draw.text((74, y), label_text, font=font(13), fill=INK)
        width = font(13).getlength(label_text)
        links.append({'rect': [74 * 1.5, y * 1.5, (74 + width) * 1.5, (y + 18) * 1.5], 'url': url})
        y += 19
    save(page, '훈련 정리', links)

    # research and method
    page = Page('연구 근거와 분석 방법', '참고', 'info')
    page.heading(56, 130, '근거로 삼은 연구와 자료', size=24)
    page.bullets(56, 172, ['수비 라인 높이가 수비 성공과 가장 강하게 연관됨 (Fujii 외, 2025, arXiv 2511.06191)', '수비 성공은 팀 전체보다 공 가까이의 수비수 밀집도와 관련됨 (Forcher 외, 2024)',
                           '수비 라인을 가르는 패스는 득점 가능성을 약 2배로 높임 (arXiv 2506.06666)', '수비 라인 뒤 침투는 수비 라인을 넘어 그 뒤 공간으로 들어가는 움직임으로 정의 (SkillCorner, Driblab)',
                           '공간은 누가 먼저 도달하는지로 판단 (Spearman 2016, Fernandez와 Bornn 2018)'], 1100, 20, KIND_COLOURS['info'], 6)
    page.heading(56, 440, '분석 방법과 한계', size=24)
    page.bullets(56, 482, ['영상 한 대의 화면에서 선수를 자동으로 찾고 경기장 좌표로 바꿔 위치를 읽었습니다', '선수는 팀당 평균 9~10명만 인식되므로 수치는 경향으로 보시고, 판단은 영상으로 함께 확인해 주세요',
                           '공의 흐름은 분석에 쓰지 않았으므로 패스와 슈팅은 판정하지 않았습니다'], 1100, 20, KIND_COLOURS['info'], 6)
    save(page, '연구 근거와 방법')

    (out / 'pages.json').write_text(json.dumps(pages, ensure_ascii=False, indent=1), encoding='utf-8')
    print('wrote', len(pages), 'pages to', out)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('output')
    parser.add_argument('calibrations')
    parser.add_argument('video')
    parser.add_argument('ffmpeg')
    parser.add_argument('--half', action='append', required=True)
    parser.add_argument('--team', choices=('A', 'B'), default='B')
    parser.add_argument('--title')
    team_profile_cli.add_argument(parser)
    build(parser.parse_args())


if __name__ == '__main__':
    main()
