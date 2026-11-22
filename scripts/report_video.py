"""Frames of the video report in one consistent broadcast style: title and summary cards, scene frames of the original video with a
lower-third title, the followed player with a trail, an optional spotlight (replay) and a pop-up minimap with movement trails."""
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.pitch_map import pitch_lines  # noqa: E402

FONT = 'C:/Windows/Fonts/malgun.ttf'
FONT_BOLD = 'C:/Windows/Fonts/malgunbd.ttf'
SIZE = (1280, 720)
INSET = (420, 270)
BRAND = 'TACTICAL REPORT'

# one palette for every card and overlay (RGB for Pillow, BGR for OpenCV below)
NAVY, PANEL, TEXT, MUTED = (14, 20, 27), (24, 33, 44), (240, 244, 248), (150, 165, 180)
ACCENTS = {'good': (46, 196, 182), 'poor': (255, 138, 101), 'goal': (255, 200, 87), 'info': (120, 170, 255)}
TEAM_COLOURS = {'A': (58, 255, 215), 'B': (200, 179, 159)}          # BGR: A bright clothes, B dark clothes; with --team-profile scripts/team_profile_cli.py overwrites these and LEGEND
LEGEND = {'text': '노랑=팀 A(밝은 옷)  하늘=팀 B(어두운 옷)'}
KEY_BGR = (87, 200, 255)                                              # the followed player: amber


def font(size, bold=False):
    return ImageFont.truetype(FONT_BOLD if bold else FONT, size)


def wrap(text, face, limit):
    lines, line = [], ''
    for ch in text:
        if face.getlength(line + ch) > limit:
            lines.append(line)
            line = ch
        else:
            line += ch
    return lines + [line]


def _frame_header(draw, accent, title, tag, page):
    draw.rectangle([0, 0, SIZE[0], 6], fill=accent)
    draw.text((56, 30), BRAND, font=font(16, True), fill=accent)
    draw.text((56, 52), title, font=font(36, True), fill=TEXT)
    if tag:
        width = font(18, True).getlength(tag) + 28
        draw.rounded_rectangle([SIZE[0] - 56 - width, 34, SIZE[0] - 56, 66], radius=16, fill=accent)
        draw.text((SIZE[0] - 56 - width + 14, 38), tag, font=font(18, True), fill=NAVY)
    if page:
        draw.text((SIZE[0] - 56 - font(16).getlength(page), SIZE[1] - 40), page, font=font(16), fill=MUTED)


def _paragraphs(draw, x, y, paragraphs, width, size=24, bullet=True, fill=TEXT):
    face = font(size)
    for paragraph in paragraphs:
        lines = wrap(paragraph, face, width - (22 if bullet else 0))
        for index, line in enumerate(lines):
            if bullet and index == 0:
                draw.ellipse([x, y + size // 2 - 3, x + 7, y + size // 2 + 4], fill=fill)
            draw.text((x + (22 if bullet else 0), y), line, font=face, fill=fill)
            y += int(size * 1.5)
        y += 8
    return y


def card(title, blocks, footer=None, accent=ACCENTS['info'], tag=None, page=None):
    """A text card. blocks: [(heading, [paragraphs])]; a block ('columns', [(heading, paragraphs), (heading, paragraphs)]) puts two side by side."""
    image = Image.new('RGB', SIZE, NAVY)
    draw = ImageDraw.Draw(image)
    _frame_header(draw, accent, title, tag, page)
    y = 128
    for heading, paragraphs in blocks:
        if heading == 'columns':
            top = y
            ends = []
            for column, (name, items) in enumerate(paragraphs):
                x = 56 + column * 590
                draw.rounded_rectangle([x - 16, top - 10, x + 560, SIZE[1] - 70], radius=14, fill=PANEL)
                draw.text((x, top), name, font=font(26, True), fill=accent if column == 0 else ACCENTS['poor'])
                ends.append(_paragraphs(draw, x, top + 44, items, 535, 23))
            y = max(ends)
            continue
        draw.text((56, y), heading, font=font(26, True), fill=accent)
        y = _paragraphs(draw, 56, y + 42, paragraphs, SIZE[0] - 140, 24, bullet=len(paragraphs) > 1) + 12
    if footer:
        draw.text((56, SIZE[1] - 40), footer, font=font(16), fill=MUTED)
    return cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)


def _fade_line(canvas, points, colour, thickness, floor=0.25):
    """A polyline that fades toward its old end (points oldest first)."""
    for k in range(1, len(points)):
        share = floor + (1 - floor) * k / (len(points) - 1)
        shade = tuple(int(c * share) for c in colour)
        cv2.line(canvas, points[k - 1], points[k], shade, max(1, int(round(thickness * (0.5 + 0.5 * share)))), cv2.LINE_AA)


def minimap_inset(pitch, players, focus_track, focus_team, back_line_u, direction, lane_pairs=(), ball_m=None, ghosts=None, trails=None, key_trail=None):
    """The pop-up minimap. players: {'A': [(tid, x, y)], 'B': [...]} in metres; trails: {tid: [(x, y), ...] oldest first} of the last seconds, drawn
    faint behind every player; key_trail: the followed player's longer path, drawn bold with a glow; ghosts: lost from sight in the last 10 s (hollow)."""
    width, height = INSET
    pad = 14
    scale = min((width - 2 * pad) / pitch['length'], (height - 2 * pad) / pitch['width'])
    to_px = lambda x, y: (int(width / 2 + x * scale), int(height / 2 + y * scale))
    canvas = np.full((height, width, 3), (42, 90, 31), np.uint8)
    for line in pitch_lines(pitch):
        cv2.polylines(canvas, [np.array([to_px(x, y) for x, y in line], np.int32)], False, (229, 245, 233), 1)
    if back_line_u is not None:
        x = back_line_u * direction
        for y in range(-int(pitch['width'] / 2), int(pitch['width'] / 2), 4):
            cv2.line(canvas, to_px(x, y), to_px(x, y + 2), (80, 200, 255), 2)
    team_of = {tid: team for team, items in players.items() for tid, _x, _y in items}
    for tid, path in (trails or {}).items():
        if tid != focus_track and len(path) >= 2:
            _fade_line(canvas, [to_px(x, y) for x, y in path], TEAM_COLOURS.get(team_of.get(tid, 'B'), (200, 200, 200)), 1, floor=0.15)
    where = {tid: (x, y) for team in players.values() for tid, x, y in team}
    for a, b in lane_pairs:
        if a in where and b in where:
            cv2.arrowedLine(canvas, to_px(*where[a]), to_px(*where[b]), (255, 255, 255), 1, tipLength=0.05)
    for team, items in (ghosts or {}).items():
        for x, y in items:
            cv2.circle(canvas, to_px(x, y), 4, TEAM_COLOURS[team], 1)
    for team, items in players.items():
        for tid, x, y in items:
            cv2.circle(canvas, to_px(x, y), 4, TEAM_COLOURS[team], -1)
    if key_trail and len(key_trail) >= 2:
        points = [to_px(x, y) for x, y in key_trail]
        _fade_line(canvas, points, (0, 0, 0), 7, floor=0.9)                        # dark outline
        _fade_line(canvas, points, KEY_BGR, 4, floor=0.2)
        if len(points) >= 3:
            cv2.arrowedLine(canvas, points[-3], points[-1], KEY_BGR, 3, tipLength=0.9)
    if ball_m is not None:
        cv2.circle(canvas, to_px(*ball_m), 5, (255, 255, 255), -1)
        cv2.circle(canvas, to_px(*ball_m), 7, (0, 0, 0), 1)
    if focus_track in where:
        point = to_px(*where[focus_track])
        cv2.circle(canvas, point, 11, KEY_BGR, 2)
        cv2.circle(canvas, point, 4, TEAM_COLOURS[focus_team], -1)
    cv2.rectangle(canvas, (0, 0), (width - 1, height - 1), (255, 255, 255), 2)
    return canvas


def scene_frame(frame, title, subtitle, inset, focus_box=None, trail_px=None, spotlight=False, banner=None, ball_xy=None, ball_note=None, accent=ACCENTS['info']):
    """One frame of a scene: the original video, the followed player (ring, arrow, trail; optionally a spotlight that darkens the rest), a
    lower-third title bar, a following zoom at the bottom left and the pop-up minimap at the bottom right.
    trail_px: [(x, y), ...] in original-frame pixels, oldest first."""
    scale_x, scale_y = SIZE[0] / frame.shape[1], SIZE[1] / frame.shape[0]
    canvas = cv2.resize(frame, SIZE)
    zoom = None
    centre = None
    if focus_box is not None:
        cx, cy = (focus_box[0] + focus_box[2]) / 2, (focus_box[1] + focus_box[3]) / 2
        player_h = max(20.0, focus_box[3] - focus_box[1])
        crop_h = float(min(380, max(150, 4.2 * player_h)))
        crop_w = crop_h * INSET[0] / INSET[1]
        x0 = int(min(max(0, cx - crop_w / 2), frame.shape[1] - crop_w))
        y0 = int(min(max(0, cy - crop_h / 2), frame.shape[0] - crop_h))
        zoom = cv2.resize(frame[y0:y0 + int(crop_h), x0:x0 + int(crop_w)], INSET, interpolation=cv2.INTER_CUBIC)
        cv2.circle(zoom, (int((cx - x0) * INSET[0] / crop_w), int((cy - y0) * INSET[1] / crop_h)), int(max(26, 0.8 * player_h * INSET[1] / crop_h)), KEY_BGR, 2, cv2.LINE_AA)
        cv2.rectangle(zoom, (0, 0), (INSET[0] - 1, INSET[1] - 1), (255, 255, 255), 2)
        centre = (int(cx * scale_x), int(cy * scale_y))
        if spotlight:
            mask = np.zeros(canvas.shape[:2], np.float32)
            cv2.circle(mask, centre, 170, 1.0, -1)
            mask = cv2.GaussianBlur(mask, (0, 0), 60)[..., None]
            canvas = (canvas * (0.38 + 0.62 * mask)).astype(np.uint8)
    if trail_px and len(trail_px) >= 2:
        points = [(int(x * scale_x), int(y * scale_y)) for x, y in trail_px]
        _fade_line(canvas, points, (0, 0, 0), 8, floor=0.9)
        _fade_line(canvas, points, KEY_BGR, 5, floor=0.2)
    if focus_box is not None:
        x1, y1, x2, y2 = [int(v * s) for v, s in zip(focus_box, (scale_x, scale_y, scale_x, scale_y))]
        base = ((x1 + x2) // 2, y2)
        cv2.ellipse(canvas, base, (max(18, x2 - x1), max(7, (x2 - x1) // 3)), 0, 0, 360, KEY_BGR, 3, cv2.LINE_AA)
        cv2.arrowedLine(canvas, (base[0], max(0, y1 - 50)), (base[0], max(0, y1 - 8)), KEY_BGR, 3, tipLength=0.4)
    if ball_xy is not None:
        bx, by = int(ball_xy[0] * scale_x), int(ball_xy[1] * scale_y)
        cv2.circle(canvas, (bx, by), 12, (0, 0, 255), 2, cv2.LINE_AA)
        cv2.circle(canvas, (bx, by), 3, (255, 255, 255), -1)
    h, w = INSET[1], INSET[0]
    canvas[SIZE[1] - h - 16:SIZE[1] - 16, SIZE[0] - w - 16:SIZE[0] - 16] = inset
    if zoom is not None:
        canvas[SIZE[1] - h - 16:SIZE[1] - 16, 16:16 + w] = zoom
    image = Image.fromarray(cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(image, 'RGBA')
    draw.rectangle([0, 0, SIZE[0], 6], fill=accent)                                  # top accent line and a lower-third title bar
    draw.rectangle([0, 6, 560, 74], fill=(14, 20, 27, 215))
    draw.text((20, 12), BRAND, font=font(13, True), fill=accent)
    draw.text((20, 28), title, font=font(24, True), fill=TEXT)
    draw.text((20, 56), subtitle, font=font(14), fill=(200, 210, 220))
    if banner:
        width = font(20, True).getlength(banner) + 40
        draw.rounded_rectangle([SIZE[0] // 2 - width / 2, 84, SIZE[0] // 2 + width / 2, 120], radius=18, fill=(255, 200, 87, 235))
        draw.text((SIZE[0] // 2 - width / 2 + 20, 90), banner, font=font(20, True), fill=NAVY)
    if ball_note:
        draw.rounded_rectangle([SIZE[0] - 330, 84, SIZE[0] - 16, 116], radius=16, fill=(0, 0, 0, 175))
        draw.text((SIZE[0] - 318, 88), ball_note, font=font(18, True), fill=(255, 120, 120))
    draw.text((SIZE[0] - w - 16, SIZE[1] - h - 38), f"미니맵: {LEGEND['text']}  점선=상대 수비 라인", font=font(13), fill=(255, 255, 255, 235))
    if zoom is not None:
        draw.text((16, SIZE[1] - h - 38), '핵심 선수 따라가기', font=font(13), fill=(255, 255, 255, 235))
    return cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
