"""The shots of the review video, drawn like a coach's telestrator and a broadcast tactical board instead of one crowded screen:

wide    the full picture with only a small label, a thin tracking box around the followed player and subtitles
zoom    a full-screen close-up that follows the player
board   a full-screen top-down board of an 11 v 11 game (dark pitch, positions only)
card    a few short bullet points, an analysis and the rules and drill for the player

Everything is laid out on a logical 1280 x 720 canvas and drawn at the real output size (1920 x 1080, the resolution of the recording), so that pictures
are never scaled down and text stays sharp. Design rules taken from broadcast and coaching practice: keep graphics light so they never hide the play, show a
label for about two seconds, use one plain bold typeface and keep the words to a few bullets.
"""
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.pitch_map import pitch_lines  # noqa: E402

SIZE = (1280, 720)                       # the logical layout
OUT = (1920, 1080)                       # what is drawn and written
K = OUT[0] / SIZE[0]
FONT, FONT_BOLD = 'C:/Windows/Fonts/malgun.ttf', 'C:/Windows/Fonts/malgunbd.ttf'
NAVY, PITCH, INK, MUTED = (11, 17, 24), (16, 30, 40), (238, 243, 247), (140, 156, 172)
GOLD = (255, 200, 87)
KIND_COLOURS = {'good': (46, 196, 182), 'poor': (255, 138, 101), 'goal': (255, 200, 87), 'info': (130, 170, 255)}
TEAM_BGR = {'A': (74, 216, 255), 'B': (255, 198, 124)}              # A bright clothes: yellow, B dark clothes: sky blue
KEY_BGR = (87, 200, 255)


def px(value):
    """A logical length as output pixels (at least 1)."""
    return max(1, int(round(value * K)))


class Face:
    """A font of a logical size; lengths are reported in logical units so that wrapping works on the logical layout."""

    def __init__(self, size, bold=False):
        self.real = ImageFont.truetype(FONT_BOLD if bold else FONT, px(size))

    def getlength(self, text):
        return self.real.getlength(text) / K


def font(size, bold=False):
    return Face(size, bold)


class Draw:
    """ImageDraw on the output canvas with logical coordinates."""

    def __init__(self, image, mode=None):
        self.d = ImageDraw.Draw(image, mode) if mode else ImageDraw.Draw(image)

    @staticmethod
    def _box(xy):
        return [v * K for v in xy]

    def rectangle(self, xy, **kw):
        self.d.rectangle(self._box(xy), **kw)

    def rounded_rectangle(self, xy, radius=0, **kw):
        self.d.rounded_rectangle(self._box(xy), radius=radius * K, **kw)

    def ellipse(self, xy, **kw):
        self.d.ellipse(self._box(xy), **kw)

    def text(self, xy, text, font=None, fill=None):
        self.d.text((xy[0] * K, xy[1] * K), text, font=font.real, fill=fill)


def _pil(canvas):
    return Image.fromarray(cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB))


def _bgr(image):
    return cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)


def _canvas(colour):
    return Image.new('RGB', OUT, colour)


def wrap(text, face, limit):
    lines, line = [], ''
    for ch in text:
        if face.getlength(line + ch) > limit:
            lines.append(line)
            line = ch
        else:
            line += ch
    return lines + [line]


def chip(canvas, label, kind='info', where='top', sub=None):
    """A small label. 'top' is the top-left corner, 'bottom' the bottom-left. It is meant to be shown for about two seconds."""
    image = _pil(canvas)
    draw = Draw(image, 'RGBA')
    colour = KIND_COLOURS[kind]
    face, small = font(24, True), font(15)
    width = max(face.getlength(label), small.getlength(sub or '')) + 36
    height = 54 if sub else 42
    y = 24 if where == 'top' else SIZE[1] - 24 - height
    draw.rounded_rectangle([24, y, 24 + width, y + height], radius=8, fill=(11, 17, 24, 205))
    draw.rectangle([24, y, 30, y + height], fill=colour)
    draw.text((42, y + 6), label, font=face, fill=INK)
    if sub:
        draw.text((42, y + 34), sub, font=small, fill=MUTED)
    return _bgr(image)


def _fade_line(canvas, points, colour, thickness, floor=0.2):
    for k in range(1, len(points)):
        share = floor + (1 - floor) * k / max(1, len(points) - 1)
        shade = tuple(int(c * share) for c in colour)
        cv2.line(canvas, points[k - 1], points[k], shade, max(1, int(round(thickness * (0.5 + 0.5 * share)))), cv2.LINE_AA)


def _put_text(canvas, text, xy, size, colour_rgb):
    """Bold text at output pixel xy (size in logical units)."""
    image = _pil(canvas)
    ImageDraw.Draw(image).text(xy, text, font=font(size, True).real, fill=colour_rgb)
    return _bgr(image)


def telestrate(canvas, box, trail_px, scale, tag='핵심 선수'):
    """Mark the followed player the way a detector draws its boxes: a thin rectangle with corner ticks and a small tag, nothing else on the picture."""
    if box is None:
        return
    sx, sy = scale
    x1, y1, x2, y2 = [int(round(v * s)) for v, s in zip(box, (sx, sy, sx, sy))]
    pad = max(px(3), int((x2 - x1) * 0.18))
    x1, y1, x2, y2 = x1 - pad, y1 - pad, x2 + pad, y2 + pad
    cv2.rectangle(canvas, (x1, y1), (x2, y2), KEY_BGR, px(1), cv2.LINE_AA)
    tick = max(px(6), min(px(18), (x2 - x1) // 3))
    for (cx, cy, dx, dy) in ((x1, y1, 1, 1), (x2, y1, -1, 1), (x1, y2, 1, -1), (x2, y2, -1, -1)):
        cv2.line(canvas, (cx, cy), (cx + dx * tick, cy), KEY_BGR, px(2), cv2.LINE_AA)
        cv2.line(canvas, (cx, cy), (cx, cy + dy * tick), KEY_BGR, px(2), cv2.LINE_AA)
    if tag:
        cv2.rectangle(canvas, (x1, y1 - px(17)), (x1 + px(20) + len(tag) * px(8), y1), KEY_BGR, -1)
        canvas[:] = _put_text(canvas, tag, (x1 + px(4), y1 - px(16)), 13, (11, 17, 24))


def caption(canvas, text):
    """A subtitle in the lower middle: one short line on a soft dark bar, small enough to leave the play visible."""
    image = _pil(canvas)
    draw = Draw(image, 'RGBA')
    face = font(26, True)
    width = face.getlength(text) + 44
    left = SIZE[0] / 2 - width / 2
    draw.rounded_rectangle([left, SIZE[1] - 92, left + width, SIZE[1] - 40], radius=10, fill=(11, 17, 24, 190))
    draw.text((left + 22, SIZE[1] - 87), text, font=face, fill=INK)
    return _bgr(image)


def subtitle(canvas, tag, text, kind='info'):
    """A subtitle for explaining a scene while its pictures are on screen: a small coloured tag ('장면', '공간', '잘한 점', '보완할 점') and up to two lines of text on a soft
    dark bar at the bottom, leaving the pitch visible."""
    image = _pil(canvas)
    draw = Draw(image, 'RGBA')
    face, tag_face = font(25, True), font(17, True)
    lines = wrap(text, face, 1000)[:2]
    height = 24 + 36 * len(lines)
    top = SIZE[1] - 30 - height
    draw.rounded_rectangle([60, top, SIZE[0] - 60, top + height], radius=10, fill=(11, 17, 24, 215))
    draw.rectangle([60, top, 66, top + height], fill=KIND_COLOURS[kind])
    draw.text((84, top + 8), tag, font=tag_face, fill=KIND_COLOURS[kind])
    for k, line in enumerate(lines):
        draw.text((84 + (80 if k == 0 else 0) if False else 84, top + 28 + 34 * k), line, font=face, fill=INK)
    return _bgr(image)


def mark_ball(canvas, xy, scale, shift=(0, 0)):
    """A small ring where the ball was found (xy in picture pixels)."""
    if xy is None:
        return
    x, y = int((xy[0] - shift[0]) * scale[0]), int((xy[1] - shift[1]) * scale[1])
    cv2.circle(canvas, (x, y), px(11), (11, 17, 24), px(3), cv2.LINE_AA)
    cv2.circle(canvas, (x, y), px(11), (255, 255, 255), px(1), cv2.LINE_AA)


def wide_shot(frame, box, trail_px, label=None, kind='info', sub=None, ball=None):
    """The full picture at the size of the recording. Only a small label (when given) and the tracking box are added."""
    canvas = frame if frame.shape[1] == OUT[0] and frame.shape[0] == OUT[1] else cv2.resize(frame, OUT, interpolation=cv2.INTER_AREA)
    canvas = canvas.copy()
    scale = (OUT[0] / frame.shape[1], OUT[1] / frame.shape[0])
    telestrate(canvas, box, trail_px, scale)
    mark_ball(canvas, ball, scale)
    return chip(canvas, label, kind, 'top', sub) if label else canvas


def zoom_shot(frame, box, label=None, kind='info', sub=None, draw_box=True, ball=None):
    """A full-screen close-up around the player (about six body heights tall, at least 150 px), sharpened a little after the enlargement."""
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    height = float(min(420, max(150, 6.0 * (box[3] - box[1]))))
    width = height * OUT[0] / OUT[1]
    x0 = int(min(max(0, cx - width / 2), frame.shape[1] - width))
    y0 = int(min(max(0, cy - height / 2), frame.shape[0] - height))
    canvas = cv2.resize(frame[y0:y0 + int(height), x0:x0 + int(width)], OUT, interpolation=cv2.INTER_CUBIC)
    blur = cv2.GaussianBlur(canvas, (0, 0), 2.0 * K)
    canvas = cv2.addWeighted(canvas, 1.5, blur, -0.5, 0)
    scale = OUT[0] / width
    if draw_box:
        telestrate(canvas, [(box[0] - x0) * scale, (box[1] - y0) * scale, (box[2] - x0) * scale, (box[3] - y0) * scale], None, (1.0, 1.0), tag='핵심 선수')
    if ball is not None and x0 <= ball[0] <= x0 + width and y0 <= ball[1] <= y0 + height:
        mark_ball(canvas, ball, (scale, scale), (x0, y0))
    return chip(canvas, label, kind, 'top', sub) if label else canvas


class Board:
    """The top-down tactical board: a dark pitch with light lines and team dots, the opponent back line, no trails."""

    def __init__(self, pitch, direction):
        self.pitch, self.direction = pitch, direction
        margin_x, margin_top, margin_bottom = 70 * K, 96 * K, 56 * K
        self.scale = min((OUT[0] - 2 * margin_x) / pitch['length'], (OUT[1] - margin_top - margin_bottom) / pitch['width'])
        self.cx, self.cy = OUT[0] / 2, margin_top + (OUT[1] - margin_top - margin_bottom) / 2
        base = np.full((OUT[1], OUT[0], 3), NAVY[::-1], np.uint8)
        corners = [self.to_px(-pitch['length'] / 2, -pitch['width'] / 2), self.to_px(pitch['length'] / 2, pitch['width'] / 2)]
        cv2.rectangle(base, corners[0], corners[1], PITCH[::-1], -1)
        for stripe in range(0, 10, 2):                                              # faint mowing stripes
            x0 = corners[0][0] + (corners[1][0] - corners[0][0]) * stripe // 10
            x1 = corners[0][0] + (corners[1][0] - corners[0][0]) * (stripe + 1) // 10
            overlay = base.copy()
            cv2.rectangle(overlay, (x0, corners[0][1]), (x1, corners[1][1]), (30, 48, 56), -1)
            base = cv2.addWeighted(overlay, 0.35, base, 0.65, 0)
        for line in pitch_lines(pitch):
            cv2.polylines(base, [np.array([self.to_px(x, y) for x, y in line], np.int32)], False, (190, 206, 218), px(1), cv2.LINE_AA)
        self.base = base

    def to_px(self, x, y):
        return int(self.cx + x * self.scale), int(self.cy + y * self.scale)

    def frame(self, seen, predicted, key_tid, back_line_u, label=None, kind='info', sub=None):
        """One board frame without trails: positions only, so the movement itself is what the eye follows.
        seen: {'A': [(tid, x, y)], 'B': [...]} solid dots; predicted: {'A': [(x, y)], 'B': [...]} dashed circles for the players of an 11 v 11 game that were not
        seen (placed from where they were last seen or from the shape of the team); the followed player gets a thin ring and a small tag."""
        canvas = self.base.copy()
        if back_line_u is not None:
            x = back_line_u * self.direction
            top, bottom = self.to_px(x, -self.pitch['width'] / 2), self.to_px(x, self.pitch['width'] / 2)
            for y in range(top[1], bottom[1], px(14)):
                cv2.line(canvas, (top[0], y), (top[0], min(bottom[1], y + px(7))), GOLD[::-1], px(2), cv2.LINE_AA)
        for team, items in predicted.items():
            for x, y in items:
                centre = self.to_px(x, y)
                for start in range(0, 360, 45):
                    cv2.ellipse(canvas, centre, (px(9), px(9)), 0, start, start + 24, TEAM_BGR[team], px(1), cv2.LINE_AA)
        for team, items in seen.items():
            for tid, x, y in items:
                cv2.circle(canvas, self.to_px(x, y), px(8), TEAM_BGR[team], -1, cv2.LINE_AA)
                cv2.circle(canvas, self.to_px(x, y), px(8), NAVY[::-1], px(1), cv2.LINE_AA)
        where = {tid: (x, y) for team in seen.values() for tid, x, y in team}
        if key_tid in where:
            point = self.to_px(*where[key_tid])
            cv2.circle(canvas, point, px(14), KEY_BGR, px(2), cv2.LINE_AA)
            canvas = _put_text(canvas, '핵심', (point[0] + px(16), point[1] - px(22)), 13, (255, 200, 87))
        canvas = chip(canvas, label, kind, 'top', sub) if label else canvas
        image = _pil(canvas)
        draw = Draw(image, 'RGBA')
        draw.text((24, SIZE[1] - 38), '실선 점: 확인된 선수   점선 원: 위치를 예측한 선수 (한 팀 11명 가정)', font=font(15), fill=MUTED)
        return _bgr(image)


def bullet_card(title, bullets, kind='info', tag=None, footer=None):
    """A calm card: a title and at most four short bullet points."""
    image = _canvas(NAVY)
    draw = Draw(image)
    colour = KIND_COLOURS[kind]
    draw.rectangle([56, 70, 64, 150], fill=colour)
    if tag:
        draw.text((86, 66), tag, font=font(18, True), fill=colour)
    draw.text((86, 92), title, font=font(46, True), fill=INK)
    y = 230
    face = font(32)
    for bullet in bullets[:4]:
        lines = wrap(bullet, face, SIZE[0] - 220)
        draw.ellipse([90, y + 14, 102, y + 26], fill=colour)
        for line in lines:
            draw.text((122, y), line, font=face, fill=INK)
            y += 48
        y += 22
    if footer:
        draw.text((86, SIZE[1] - 56), footer, font=font(17), fill=MUTED)
    return _bgr(image)


def index_card(title, items, footer=None):
    """The chapter list at the start: time, kind colour and a short title per moment."""
    image = _canvas(NAVY)
    draw = Draw(image)
    draw.rectangle([56, 56, 64, 128], fill=KIND_COLOURS['info'])
    draw.text((86, 56), title, font=font(44, True), fill=INK)
    y = 168
    for clock, kind, text in items[:10]:
        draw.rounded_rectangle([86, y, 86 + 96, y + 40], radius=8, fill=KIND_COLOURS[kind])
        draw.text((86 + 48 - font(22, True).getlength(clock) / 2, y + 6), clock, font=font(22, True), fill=NAVY)
        draw.text((204, y + 3), text, font=font(28), fill=INK)
        y += 50
    if footer:
        draw.text((86, SIZE[1] - 50), footer, font=font(17), fill=MUTED)
    return _bgr(image)


def analysis_card(title, summary, good, fix, nxt, kind='info', tag=None):
    """The card after a sequence: one summary line, what went well, what to fix and the next step, each as a short bullet."""
    image = _canvas(NAVY)
    draw = Draw(image)
    colour = KIND_COLOURS[kind]
    draw.rectangle([56, 48, 64, 118], fill=colour)
    if tag:
        draw.text((86, 44), tag, font=font(17, True), fill=colour)
    draw.text((86, 66), title, font=font(40, True), fill=INK)
    draw.text((86, 130), summary, font=font(26), fill=MUTED)
    for column, (name, items, accent) in enumerate((('잘한 점', good, KIND_COLOURS['good']), ('보완할 점', fix, KIND_COLOURS['poor']))):
        x = 56 + column * 600
        draw.rounded_rectangle([x, 190, x + 560, 560], radius=14, fill=(20, 29, 39))
        draw.text((x + 26, 208), name, font=font(26, True), fill=accent)
        y = 256
        for item in items[:3]:
            lines = wrap(item, font(23), 480)
            draw.ellipse([x + 26, y + 11, x + 36, y + 21], fill=accent)
            for line in lines:
                draw.text((x + 52, y), line, font=font(23), fill=INK)
                y += 34
            y += 14
    draw.rounded_rectangle([56, 580, 1224, 650], radius=12, fill=(20, 29, 39))
    draw.text((82, 594), '다음에는', font=font(20, True), fill=KIND_COLOURS['info'])
    draw.text((190, 592), nxt, font=font(24), fill=INK)
    draw.text((56, SIZE[1] - 36), 'Football Coach · 영상 리뷰', font=font(14), fill=MUTED)
    return _bgr(image)


def description_card(title, scene, space, kind='info', tag=None):
    """The card that tells what happened and what the space looked like: two columns of short sentences, 'the scene' on the left and 'the space' on the right."""
    image = _canvas(NAVY)
    draw = Draw(image)
    colour = KIND_COLOURS[kind]
    draw.rectangle([56, 48, 64, 118], fill=colour)
    if tag:
        draw.text((86, 44), tag, font=font(17, True), fill=colour)
    draw.text((86, 66), title, font=font(40, True), fill=INK)
    for column, (name, items, accent) in enumerate((('장면', scene, KIND_COLOURS['info']), ('공간', space, KIND_COLOURS['good']))):
        x = 56 + column * 600
        draw.rounded_rectangle([x, 160, x + 560, 640], radius=14, fill=(20, 29, 39))
        draw.text((x + 26, 180), name, font=font(28, True), fill=accent)
        y = 236
        for item in items[:4]:
            lines = wrap(item, font(24), 480)
            draw.ellipse([x + 26, y + 12, x + 36, y + 22], fill=accent)
            for line in lines:
                draw.text((x + 52, y), line, font=font(24), fill=INK)
                y += 36
            y += 18
    draw.text((56, SIZE[1] - 36), 'Football Coach · 영상 리뷰', font=font(14), fill=MUTED)
    return _bgr(image)


def rules_card(title, rules, drill, kind='info', tag=None):
    """The card for the player: three rules to act on (left) and one drill with its set-up and the point to coach (right)."""
    image = _canvas(NAVY)
    draw = Draw(image)
    colour = KIND_COLOURS[kind]
    draw.rectangle([56, 48, 64, 118], fill=colour)
    if tag:
        draw.text((86, 44), tag, font=font(17, True), fill=colour)
    draw.text((86, 66), title, font=font(38, True), fill=INK)
    draw.rounded_rectangle([56, 160, 700, 660], radius=14, fill=(20, 29, 39))
    draw.text((82, 178), '이렇게 움직이세요', font=font(26, True), fill=colour)
    y = 232
    for number, rule in enumerate(rules[:3], 1):
        draw.ellipse([82, y + 2, 112, y + 32], fill=colour)
        draw.text((90 if number < 10 else 86, y + 3), str(number), font=font(20, True), fill=NAVY)
        for line in wrap(rule, font(23), 540):
            draw.text((128, y), line, font=font(23), fill=INK)
            y += 33
        y += 20
    draw.rounded_rectangle([724, 160, 1224, 660], radius=14, fill=(20, 29, 39))
    draw.text((750, 178), '훈련으로 만들기', font=font(26, True), fill=KIND_COLOURS['info'])
    draw.text((750, 226), drill['name'], font=font(28, True), fill=INK)
    y = 276
    for item in drill['setup']:
        lines = wrap(item, font(21), 420)
        draw.ellipse([752, y + 10, 760, y + 18], fill=KIND_COLOURS['info'])
        for line in lines:
            draw.text((774, y), line, font=font(21), fill=INK)
            y += 31
        y += 10
    draw.rounded_rectangle([750, 560, 1198, 636], radius=10, fill=(30, 42, 55))
    draw.text((768, 568), '코칭 포인트', font=font(17, True), fill=MUTED)
    draw.text((768, 596), drill['focus'], font=font(24, True), fill=GOLD)
    draw.text((56, SIZE[1] - 36), 'Football Coach · 영상 리뷰', font=font(14), fill=MUTED)
    return _bgr(image)
