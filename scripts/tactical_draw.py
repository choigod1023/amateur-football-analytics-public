"""Draws the tactical minimap video for scripts/build_tactical_report.py (pitch in metres, Korean captions through Pillow)."""
import math

import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.pitch_map import pitch_lines

from app.team_style import short_name  # noqa: E402
COLOURS = {'A': (58, 255, 215), 'B': (200, 179, 159)}          # BGR; with --team-profile scripts/team_profile_cli.py overwrites these and LEGEND
LEGEND = {'text': '노랑=팀 A(밝은 옷)  하늘=팀 B(어두운 옷)'}
FONT = 'C:/Windows/Fonts/malgun.ttf'
WIDTH, PITCH_HEIGHT, PANEL, PAD = 960, 560, 190, 30
TRAIL = 10                                                        # frames a breakthrough marker stays


def caption_lines(notes, font, limit=900):
    """Wraps Korean notes into lines that fit `limit` pixels."""
    out = []
    for note in notes:
        line = ''
        for ch in note:
            if font.getlength(line + ch) > limit:
                out.append(line)
                line = '  ' + ch
            else:
                line += ch
        out.append(line)
    return out


def render(path, drawn, runs, summary, pitch, first, last, fps, offset, window_frames, direction, clock):
    scale = min((WIDTH - 2 * PAD) / pitch['length'], (PITCH_HEIGHT - 2 * PAD) / pitch['width'])
    to_px = lambda x, y: (int(WIDTH / 2 + x * scale), int(PITCH_HEIGHT / 2 + y * scale))
    base = np.full((PITCH_HEIGHT, WIDTH, 3), (42, 90, 31), np.uint8)
    for line in pitch_lines(pitch):
        cv2.polylines(base, [np.array([to_px(x, y) for x, y in line], np.int32)], False, (229, 245, 233), 1)
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*'mp4v'), fps, (WIDTH, PITCH_HEIGHT + PANEL))
    big, small = ImageFont.truetype(FONT, 15), ImageFont.truetype(FONT, 13)
    by_frame_runs = {}
    for run in runs:
        for k in range(TRAIL):
            by_frame_runs.setdefault(run['frame'] + k, []).append(run)
    last_state = {}
    for frame in range(first, last):
        canvas = base.copy()
        state = drawn.get(frame) or last_state
        last_state = state
        for team, data in state.items():
            colour = COLOURS[team]
            if data['lines']:
                for key in ('defence', 'midfield', 'attack'):
                    x = data['lines'][key] * direction[team]
                    for y in range(-int(pitch['width'] / 2), int(pitch['width'] / 2), 4):
                        cv2.line(canvas, to_px(x, y), to_px(x, y + 2), colour, 1)
            ordered = sorted(data['lanes'], key=lambda l: -(data['everyone'][l['to']][0] - data['everyone'][l['from']][0]) * direction[team])[:6]
            for lane in ordered:
                a, b = data['everyone'][lane['from']], data['everyone'][lane['to']]
                cv2.arrowedLine(canvas, to_px(*a), to_px(*b), colour, 1, tipLength=0.04)
            for x, y in data['seen']:
                cv2.circle(canvas, to_px(x, y), 6, colour, -1)
                cv2.circle(canvas, to_px(x, y), 6, (20, 20, 20), 1)
            for guess in data['guesses']:
                x, y = to_px(guess['x'], guess['y'])
                cv2.circle(canvas, (x, y), 8, colour, 2)
                cv2.putText(canvas, '?', (x - 4, y + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.45, colour, 2)
        panel = Image.new('RGB', (WIDTH, PITCH_HEIGHT + PANEL), (24, 24, 24))
        panel.paste(Image.fromarray(cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB)), (0, 0))
        draw = ImageDraw.Draw(panel)
        seconds = offset + frame / fps
        index = (frame - first) // window_frames
        draw.text((10, 6), f'{clock(seconds)}  {LEGEND["text"]}  채운 원=확인  빈 원(?)=사라진 선수 예상  점선=라인  화살표=열린 전진 패스길', font=small, fill=(255, 255, 255))
        for run in by_frame_runs.get(frame, []):
            draw.text((10, PITCH_HEIGHT - 22), f'돌파성 달리기 포착: {short_name(run["team"])} (공 소유는 확인되지 않음)', font=small, fill=(255, 220, 90))
        y = PITCH_HEIGHT + 8
        for team in ('A', 'B'):
            entry = summary.get(f'{index}:{team}')
            if not entry:
                continue
            seen_text = f'{short_name(team)} (확인 {entry["seen"]}명 + 예상 {entry["estimated"]}명, 나머지 {max(0.0, 11 - entry["seen"] - entry["estimated"]):.1f}명은 위치 불명)'
            draw.text((10, y), seen_text, font=big, fill=tuple(reversed(COLOURS[team])))
            y += 20
            for line in caption_lines(entry['notes'][1:] or ['이 구간은 평소와 뚜렷하게 다른 점이 없습니다.'], small)[:3]:
                draw.text((22, y), line, font=small, fill=(235, 235, 235))
                y += 17
            y += 4
        writer.write(cv2.cvtColor(np.array(panel), cv2.COLOR_RGB2BGR))
    writer.release()
