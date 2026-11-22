"""Detailed match report in categories (HTML, prints to PDF), for two matches of the same team.

python scripts/build_detailed_report.py --out report.html \
    --prev-h1 positions.jsonl --prev-h2 positions.jsonl --prev-alerts-h1 a.jsonl --prev-alerts-h2 b.jsonl \
    --cur-h1 positions.jsonl --cur-h2 positions.jsonl --cur-alerts-h1 a.jsonl --cur-alerts-h2 b.jsonl --cur-h2-end 1405

Categories: team shape (lines, gaps, length, width), attack routes (entries into the final third and the box by lane), how the opponent attacked and how we answered
(waves into our final third, our line response, whether they reached the box), second balls and space (Voronoi share and contested zones, only for seconds in which both
teams are seen by 8 to 12 players), comparison of the two matches, and the tasks for the next match. Without the ball: every statement is about where players stood and moved.
Everything is drawn from our team's point of view: our goal on the left, we attack to the right. "Left" and "right" in the lanes are the team's own left and right.
"""
import argparse
import html
import json
import math
import re
import statistics
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

L, W = 89.0, 62.0
S = 6.0
PAD = 18
BOX_D, BOX_H = 16.5, 20.15
THIRD = L / 2 - L / 3                       # u of the line of the final third (+14.8) in our view
LANE_EDGES = [-W / 2 * 0.6, -W / 2 * 0.2, W / 2 * 0.2, W / 2 * 0.6]            # +-18.6 and +-6.2 m
LANES = ['왼쪽 측면', '왼쪽 하프스페이스', '가운데', '오른쪽 하프스페이스', '오른쪽 측면']
MIN_BALANCED, MAX_BALANCED = 8, 12


# ---- reading -----------------------------------------------------------------------------------------------------------------------
def read(path, end=None):
    header, out = None, {}
    for line in Path(path).read_text(encoding='utf-8').splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r['type'] == 'header':
            header = r
        elif r['type'] == 'second' and (end is None or r['time'] <= end):
            d = int(header['direction'])
            out[int(round(r['time']))] = {'ours': merge_close([(i, x * d, y * d) for i, x, y in r['team']]), 'theirs': merge_close([(i, x * d, y * d) for i, x, y in r['other']])}
    return out


def merge_close(points, metres=1.5):
    """Two tracks closer than 1.5 m are one player (a player who got a new track number while the old one is still held)."""
    kept = []
    for p in points:
        if all(math.hypot(p[1] - k[1], p[2] - k[2]) >= metres for k in kept):
            kept.append(p)
    return kept


def lane(v):
    for k, e in enumerate(LANE_EDGES):
        if v < e:
            return k
    return 4


def outfield(points):
    pts = sorted(points, key=lambda p: p[1])
    if pts and pts[0][1] < -30:
        pts = pts[1:]
    return pts


def shape(points):
    pts = outfield(points)
    if len(pts) < 7:
        return None
    xs = sorted(p[1] for p in pts)
    ys = sorted(p[2] for p in pts)
    n = len(xs)
    d, a, m = statistics.mean(xs[:3]), statistics.mean(xs[-2:]), statistics.mean(xs[3:n - 2])
    return {'def': d, 'mid': m, 'att': a, 'width': ys[int(0.9 * (n - 1))] - ys[int(0.1 * (n - 1))], 'centre': statistics.mean(xs)}


def mean(values):
    values = [v for v in values if v is not None]
    return statistics.mean(values) if values else None


def height(v):
    return None if v is None else v + L / 2


def fmt(v, digits=0):
    return '-' if v is None else f'{v:.{digits}f}'


# ---- team shape --------------------------------------------------------------------------------------------------------------------
def half_shape(data):
    rows = [shape(r['ours']) for r in data.values()]
    rows = [r for r in rows if r]
    if not rows:
        return None
    out = {k: mean([r[k] for r in rows]) for k in ('def', 'mid', 'att', 'width', 'centre')}
    out['def'], out['mid'], out['att'] = height(out['def']), height(out['mid']), height(out['att'])
    out['gap_dm'], out['gap_ma'], out['length'] = out['mid'] - out['def'], out['att'] - out['mid'], out['att'] - out['def']
    theirs = [shape([(i, -x, -y) for i, x, y in r['theirs']]) for r in data.values()]
    out['odef'] = height(mean([t['def'] for t in theirs if t]))
    return out


def bin_rows(data, size=300):
    groups = {}
    for t in sorted(data):
        groups.setdefault(t // size, {})[t] = data[t]
    rows = []
    t0 = min(data)
    for k in sorted(groups):
        part = groups[k]
        r = half_shape(part)
        if r and len(part) >= 60:
            r['label'] = f'{(min(part) - t0) // 60}~{(min(part) - t0) // 60 + 5}분'
            rows.append(r)
    return rows


# ---- entries and waves -------------------------------------------------------------------------------------------------------------
def entries(data, side, kind, margin=3.0):
    """Players who cross into the final third ('third') or into the box ('box') of the goal they attack: events (t, id, lane, (u0, v0), (u1, v1)).
    A player counts when two seconds earlier he was at least `margin` metres outside and now is inside, so that standing on the line does not count again and again."""
    sign = 1 if side == 'ours' else -1

    def depth(u, v):
        if kind == 'third':
            return sign * u - THIRD
        return min(sign * u - (L / 2 - BOX_D), BOX_H - abs(v))
    out, last = [], {}
    for t in sorted(data):
        prev = data.get(t - 2)
        if not prev:
            continue
        before = {i: (u, v) for i, u, v in prev[side]}
        for i, u, v in data[t][side]:
            if i not in before:
                continue
            u0, v0 = before[i]
            if math.hypot(u - u0, v - v0) > 20:
                continue
            if depth(u0, v0) <= -margin and depth(u, v) >= 0 and t - last.get(i, -99) >= 12:
                last[i] = t
                out.append((t, i, lane(v), (u0, v0), (u, v)))
    return merge_doubles(out)


def merge_doubles(events, seconds=8, metres=8.0):
    """The same player can get a new track number after a gap, which would count one entry twice: events close in time and place are one entry."""
    kept = []
    for e in sorted(events):
        if any(abs(e[0] - k[0]) <= seconds and math.hypot(e[4][0] - k[4][0], e[4][1] - k[4][1]) < metres for k in kept):
            continue
        kept.append(e)
    return kept


def waves(events, gap=8):
    out = []
    for e in sorted(events):
        if out and e[0] - out[-1][-1][0] <= gap:
            out[-1].append(e)
        else:
            out.append([e])
    return out


def wave_info(w, data, side, box_times, window=10):
    t = w[0][0]
    lanes = [e[2] for e in w]
    main = max(set(lanes), key=lanes.count)
    speeds = []
    for tt, i, ln, (u0, v0), (u1, v1) in w:
        speeds.append(math.hypot(u1 - u0, v1 - v0))
    reached = any(t <= b <= t + window for b in box_times)
    return {'t': t, 'lane': main, 'players': len({e[1] for e in w}), 'max_speed': max(speeds), 'reached': reached, 'events': w}


def response(data, t):
    """Our line before (t-3) and after (t+5) an opponent wave: (line height change, gap after)."""
    def at(tt):
        rows = [shape(data[x]['ours']) for x in range(tt - 1, tt + 2) if x in data]
        rows = [r for r in rows if r]
        return (mean([r['def'] for r in rows]), mean([r['mid'] - r['def'] for r in rows])) if rows else (None, None)
    b, _ = at(t - 3)
    a, gap = at(t + 5)
    if b is None or a is None:
        return None
    return a - b, gap


def lane_counts(events):
    c = [0] * 5
    for e in events:
        c[e[2]] += 1
    return c


# ---- space (Voronoi) and contested zones -------------------------------------------------------------------------------------------
GU = np.arange(-L / 2 + 1, L / 2, 2.0)
GV = np.arange(-W / 2 + 1, W / 2, 2.0)
CELLS = np.array([(u, v) for u in GU for v in GV])


def balanced(row):
    return MIN_BALANCED <= len(row['ours']) <= MAX_BALANCED and MIN_BALANCED <= len(row['theirs']) <= MAX_BALANCED


def voronoi_owner(row):
    pts = np.array([(u, v) for _, u, v in row['ours']] + [(u, v) for _, u, v in row['theirs']])
    own = np.array([1] * len(row['ours']) + [0] * len(row['theirs']))
    dist = ((CELLS[:, None, :] - pts[None, :, :]) ** 2).sum(axis=2)
    return own[dist.argmin(axis=1)]


def space_shares(data):
    thirds = [0.0, 0.0, 0.0]
    count = 0
    contested = np.zeros((int(L // 8) + 1, int(W // 8) + 1))
    by_bin = {}
    t0 = min(data)
    for t in sorted(data):
        row = data[t]
        if not balanced(row):
            continue
        own = voronoi_owner(row)
        for k, (lo, hi) in enumerate(((-L / 2, -THIRD), (-THIRD, THIRD), (THIRD, L / 2))):
            mask = (CELLS[:, 0] >= lo) & (CELLS[:, 0] < hi)
            thirds[k] += own[mask].mean()
        count += 1
        by_bin.setdefault((t - t0) // 300, []).append(own.mean())
        for _, u, v in row['ours']:
            for _, u2, v2 in row['theirs']:
                if math.hypot(u - u2, v - v2) < 4.0:
                    contested[int((u2 + u) / 2 + L / 2) // 8, int((v + v2) / 2 + W / 2) // 8] += 1
    shares = [x / count for x in thirds] if count else None
    return {'seconds': count, 'thirds': shares, 'contested': contested, 'by_bin': {k: statistics.mean(v) for k, v in by_bin.items()}}


# ---- drawing -----------------------------------------------------------------------------------------------------------------------
def px(u, v):
    return PAD + (u + L / 2) * S, PAD + (v + W / 2) * S


def pitch_svg_start():
    w, h = L * S + 2 * PAD, W * S + 2 * PAD
    x0, y0 = px(-L / 2, -W / 2)
    parts = [f'<svg viewBox="0 0 {w:.0f} {h:.0f}" width="100%" role="img">',
             f'<rect x="{x0}" y="{y0}" width="{L * S}" height="{W * S}" fill="#2d6a3e" stroke="#cfe8d4" stroke-width="2"/>']
    return parts


def pitch_lines():
    out = []
    x0, y0 = px(-L / 2, -W / 2)
    cx, cy = px(0, 0)
    out.append(f'<line x1="{cx}" y1="{y0}" x2="{cx}" y2="{y0 + W * S}" stroke="#cfe8d4" stroke-width="2"/><circle cx="{cx}" cy="{cy}" r="{9.15 * S}" fill="none" stroke="#cfe8d4" stroke-width="2"/>')
    for sx in (-1, 1):
        ax, ay = px(sx * (L / 2 - BOX_D), -BOX_H)
        bx = px(sx * L / 2, 0)[0]
        out.append(f'<rect x="{min(ax, bx)}" y="{ay}" width="{BOX_D * S}" height="{2 * BOX_H * S}" fill="none" stroke="#cfe8d4" stroke-width="2"/>')
    for e in LANE_EDGES:
        y = px(0, e)[1]
        out.append(f'<line x1="{x0}" y1="{y:.1f}" x2="{x0 + L * S}" y2="{y:.1f}" stroke="#cfe8d4" stroke-width="1" stroke-dasharray="2 8" opacity="0.5"/>')
    for ex in (-THIRD, THIRD):
        x = px(ex, 0)[0]
        out.append(f'<line x1="{x:.1f}" y1="{y0}" x2="{x:.1f}" y2="{y0 + W * S}" stroke="#cfe8d4" stroke-width="1" stroke-dasharray="2 8" opacity="0.5"/>')
    return ''.join(out)


def arrow(u0, v0, u1, v1, colour, width=2.2, opacity=0.85):
    x0, y0 = px(u0, v0)
    x1, y1 = px(u1, v1)
    length = math.hypot(x1 - x0, y1 - y0)
    if length < 6:
        return f'<circle cx="{x1:.1f}" cy="{y1:.1f}" r="5" fill="{colour}" opacity="0.9"/>'
    ang = math.atan2(y1 - y0, x1 - x0)
    hx, hy = 8 + width, 4.5 + width / 2
    p1 = (x1 - hx * math.cos(ang) + hy * math.sin(ang), y1 - hx * math.sin(ang) - hy * math.cos(ang))
    p2 = (x1 - hx * math.cos(ang) - hy * math.sin(ang), y1 - hx * math.sin(ang) + hy * math.cos(ang))
    return (f'<line x1="{x0:.1f}" y1="{y0:.1f}" x2="{x1:.1f}" y2="{y1:.1f}" stroke="{colour}" stroke-width="{width}" opacity="{opacity}"/>'
            f'<polygon points="{x1:.1f},{y1:.1f} {p1[0]:.1f},{p1[1]:.1f} {p2[0]:.1f},{p2[1]:.1f}" fill="{colour}"/>'
            f'<circle cx="{x0:.1f}" cy="{y0:.1f}" r="2.5" fill="{colour}" opacity="0.5"/>')


BLUE, RED = '#6db8ff', '#ff8a6b'


def scene_svg(data, t, lookback=3, shade=False, ball=None):
    now, then = data.get(int(round(t))), data.get(int(round(t)) - lookback)
    if not now or not then:
        return None, {}
    parts = pitch_svg_start()
    if shade and balanced(now):
        own = voronoi_owner(now)
        for (u, v), o in zip(CELLS, own):
            x, y = px(u - 1, v - 1)
            parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{2 * S:.1f}" height="{2 * S:.1f}" fill="{"#3a7bd5" if o else "#d9583b"}" opacity="0.28"/>')
    parts.append(pitch_lines())
    stats = {}
    for key, colour in (('theirs', RED), ('ours', BLUE)):
        before = {i: (x, y) for i, x, y in then[key]}
        speeds = []
        for i, x, y in now[key]:
            if i in before:
                bx, by = before[i]
                sp = math.hypot(x - bx, y - by) / lookback
                parts.append(arrow(bx, by, x, y, colour, 3.2 if sp >= 4.0 else 2.0))
                speeds.append(sp)
            else:
                cx, cy = px(x, y)
                parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="5" fill="{colour}" opacity="0.9"/>')
        stats[key] = speeds
        s = shape(now[key] if key == 'ours' else [(i, -x, -y) for i, x, y in now[key]])
        if s:
            line_u = s['def'] if key == 'ours' else -s['def']
            x1, y1 = px(line_u, -W / 2)
            parts.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x1:.1f}" y2="{y1 + W * S:.1f}" stroke="{colour}" stroke-width="2" stroke-dasharray="6 5" opacity="0.8"/>')
    if ball and len(ball) >= 2:
        for a, b in zip(ball, ball[1:]):
            if math.hypot(b[1] - a[1], b[2] - a[2]) <= 40 and b[0] - a[0] <= 1.0:
                x0, y0 = px(a[1], a[2])
                x1, y1 = px(b[1], b[2])
                parts.append(f'<line x1="{x0:.1f}" y1="{y0:.1f}" x2="{x1:.1f}" y2="{y1:.1f}" stroke="#ffe14a" stroke-width="3.5" opacity="0.95"/>')
        for t0, u0, v0 in ball:
            x, y = px(u0, v0)
            parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="#ffe14a"/>')
        x, y = px(ball[-1][1], ball[-1][2])
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="7" fill="none" stroke="#ffe14a" stroke-width="3"/>')
    parts.append('</svg>')
    return ''.join(parts), stats


def path_svg(data, t, before=5, after=3, ball=None, highlight=None):
    """Where every player went from `before` seconds before the scene to `after` seconds after it: a trail with an arrow head at the end (thick when the player ran fast), the dot is where he stood at the
    moment of the scene. Our players blue, the opponent's orange, the ball yellow. Works on paper, nothing moves."""
    t = int(round(t))
    seconds = [x for x in range(t - before, t + after + 1) if x in data]
    if len(seconds) < 4:
        return None, {}
    parts = pitch_svg_start()
    parts.append(pitch_lines())
    stats = {'ours': 0, 'theirs': 0}
    for key, colour in (('theirs', RED), ('ours', BLUE)):
        tracks = {}
        for x in seconds:
            for i, u, v in data[x][key]:
                tracks.setdefault(i, []).append((x, u, v))
        for i, pts in tracks.items():
            if len(pts) < 3:
                continue
            pts = sorted(pts)
            faint = highlight is not None and key == 'ours' and i not in highlight or highlight is not None and key == 'theirs'
            coords = [px(u, v) for _, u, v in pts]
            dist = sum(math.hypot(b[1] - a[1], b[2] - a[2]) for a, b in zip(pts, pts[1:]) if b[0] - a[0] <= 2)
            speed = dist / max(1, pts[-1][0] - pts[0][0])
            wide = 3.2 if speed >= 3.5 else 2.0
            if highlight is not None and not faint:
                wide += 1.6
            stats[key] += speed >= 3.5
            if dist < 3.0:
                x0, y0 = coords[-1]
                parts.append(f'<circle cx="{x0:.1f}" cy="{y0:.1f}" r="{3.5 if faint else 6}" fill="{colour}" opacity="{0.25 if faint else 0.95}"/>')
                continue
            line = ' '.join(f'{x:.1f},{y:.1f}' for x, y in coords[:-1])
            parts.append(f'<polyline points="{line} {coords[-1][0]:.1f},{coords[-1][1]:.1f}" fill="none" stroke="{colour}" stroke-width="{wide}" opacity="{0.18 if faint else 0.7}" stroke-linejoin="round"/>')
            parts.append(arrow(pts[-2][1], pts[-2][2], pts[-1][1], pts[-1][2], colour, wide, 0.25 if faint else 0.98))
            parts.append(f'<circle cx="{coords[0][0]:.1f}" cy="{coords[0][1]:.1f}" r="2.5" fill="{colour}" opacity="0.6"/>')
        # the place of every player at the moment of the scene
        for i, u, v in data.get(t, {key: []})[key]:
            x0, y0 = px(u, v)
            parts.append(f'<circle cx="{x0:.1f}" cy="{y0:.1f}" r="5" fill="none" stroke="#fff" stroke-width="1.5" opacity="0.8"/>')
    if ball and len(ball) >= 2:
        for a, b in zip(ball, ball[1:]):
            if math.hypot(b[1] - a[1], b[2] - a[2]) <= 40 and b[0] - a[0] <= 1.0:
                x0, y0 = px(a[1], a[2])
                x1, y1 = px(b[1], b[2])
                parts.append(f'<line x1="{x0:.1f}" y1="{y0:.1f}" x2="{x1:.1f}" y2="{y1:.1f}" stroke="#ffe14a" stroke-width="3.5" opacity="0.95"/>')
        x, y = px(ball[-1][1], ball[-1][2])
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="7" fill="none" stroke="#ffe14a" stroke-width="3"/>')
    parts.append(f'<text x="{PAD + 6}" y="{PAD + 22}" fill="#fff" font-size="15" opacity="0.9">장면 {before}초 전부터 {after}초 뒤까지의 이동</text>')
    parts.append('</svg>')
    return ''.join(parts), stats


def route_map(events_ours, events_theirs):
    """Mean entry vector per lane (ours blue, theirs red); thickness follows the number of entries."""
    parts = pitch_svg_start()
    parts.append(pitch_lines())
    for events, colour in ((events_theirs, RED), (events_ours, BLUE)):
        for k in range(5):
            ev = [e for e in events if e[2] == k]
            if not ev:
                continue
            u0 = statistics.mean(e[3][0] for e in ev)
            v0 = statistics.mean(e[3][1] for e in ev)
            u1 = statistics.mean(e[4][0] for e in ev)
            v1 = statistics.mean(e[4][1] for e in ev)
            parts.append(arrow(u0, v0, u1, v1, colour, min(9.0, 1.5 + len(ev) * 0.5), 0.75))
            x, y = px(u1, v1)
            parts.append(f'<text x="{x:.1f}" y="{y - 8:.1f}" fill="#fff" font-size="13" text-anchor="middle">{len(ev)}</text>')
    parts.append('</svg>')
    return ''.join(parts)


def contested_svg(grid):
    parts = pitch_svg_start()
    mx = grid.max() or 1
    for i in range(grid.shape[0]):
        for j in range(grid.shape[1]):
            if grid[i, j] <= 0:
                continue
            u0, v0 = -L / 2 + i * 8, -W / 2 + j * 8
            x, y = px(u0, v0)
            parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{8 * S:.1f}" height="{8 * S:.1f}" fill="#ffd54a" opacity="{0.08 + 0.75 * grid[i, j] / mx:.2f}"/>')
    parts.append(pitch_lines())
    parts.append('</svg>')
    return ''.join(parts)


# ---- words -------------------------------------------------------------------------------------------------------------------------
def words_gap(v):
    return '매우 벌어짐' if v >= 22 else '벌어짐' if v >= 16 else '적당함' if v >= 9 else '촘촘함'


def words_length(v):
    return '길게 늘어짐' if v >= 55 else '약간 긴 편' if v >= 45 else '적당함' if v >= 30 else '짧게 모여 있음'


def words_width(v):
    return '넓게 섬' if v >= 45 else '보통' if v >= 34 else '좁게 섬'


def words_def(v):
    return '아주 높음' if v >= 38 else '높음' if v >= 30 else '중간' if v >= 22 else '낮음'


def by_lane(k):
    """'<길>으로' or '<길>로' with the right particle."""
    name = LANES[k]
    code = ord(name[-1]) - 0xAC00
    return name + ('로' if code % 28 in (0, 8) else '으로')


def esc(s):
    return html.escape(str(s))


def pct(n, d):
    return 0 if d == 0 else round(100 * n / d)


def bar_table(title, rows):
    """rows: [(label, [five counts])]"""
    out = [f'<table><tr><th>{esc(title)}</th>' + ''.join(f'<th>{n}</th>' for n in LANES) + '<th>합계</th></tr>']
    for label, counts in rows:
        total = sum(counts) or 1
        cells = ''.join(f'<td><div class="bar" style="width:{max(2, 100 * c // total)}%"></div>{c}회 ({pct(c, total)}%)</td>' for c in counts)
        out.append(f'<tr><td>{esc(label)}</td>{cells}<td>{sum(counts)}회</td></tr>')
    out.append('</table>')
    return ''.join(out)


CSS = """
body{font-family:'Malgun Gothic',system-ui,sans-serif;margin:0;background:#0f1a14;color:#e8f1ea;line-height:1.55}
main{max-width:1020px;margin:0 auto;padding:24px 18px 60px}
h1{font-size:1.7rem;margin:.2em 0}h2{font-size:1.3rem;margin:1.8em 0 .4em;border-bottom:1px solid #2f4a39;padding-bottom:.2em}h3{font-size:1.05rem;margin:1.2em 0 .3em;color:#bfe3c8}
.card{background:#16261c;border:1px solid #2f4a39;border-radius:10px;padding:12px 14px;margin:10px 0}
table{border-collapse:collapse;width:100%;font-size:.9rem}td,th{border-bottom:1px solid #2f4a39;padding:5px 7px;text-align:center}th{color:#bfe3c8;font-weight:600}
td{position:relative}.bar{position:absolute;left:0;bottom:0;height:4px;background:#4aa3ff;opacity:.8}
.bad{color:#ffb4a0}.good{color:#9ee6b0}.note{color:#9db8a4;font-size:.9rem}.grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}
@media(max-width:760px){.grid{grid-template-columns:1fr}}
svg{background:#1b4a2a;border-radius:8px}
.tag{display:inline-block;background:#244f33;border-radius:999px;padding:1px 9px;font-size:.8rem;margin-right:6px}
.legend span{display:inline-block;margin-right:14px}.sw{display:inline-block;width:12px;height:12px;border-radius:3px;margin-right:4px;vertical-align:-1px}
@media print{body{background:#fff;color:#111}.card{background:#fff;border-color:#bbb}h2{border-color:#bbb}th,h3{color:#234}td,th{border-color:#ccc}}
"""


def ball_paths(ball_dir, calibrations, camera, scenes, first_clip, directions):
    """Ball positions a person marked on the clips b55.. (scenes in order) as {scene name: [(seconds of the half video, u, v)]} in our view (the ball taken to lie on the ground)."""
    from app.pitch_map import apply, fit
    fitted = fit(json.loads(Path(calibrations).read_text(encoding='utf-8'))[camera])
    out = {}
    for n, sc in enumerate(scenes):
        cid = f'b{first_clip + n}'
        path = Path(ball_dir) / 'labels' / (cid + '.json')
        if not path.is_file():
            continue
        labels = json.loads(path.read_text(encoding='utf-8'))
        start = max(0, int(sc['at']) - 5)
        pts = []
        for f, l in sorted(labels.items()):
            if l.get('state') != 'ball' or l.get('verified') == 'rejected':
                continue
            k = int(f[2:5]) - 1
            m = apply(fitted['H'], l['x'] / 1920.0, l['y'] / 1080.0)
            if m:
                d = directions[sc['half']]
                pts.append((start + k / 5.0, m[0] * d, m[1] * d))
        out[sc['name']] = pts
    return out


KIND_TEXT = {'our_attack': '우리 공격(박스까지 이어진 장면)', 'their_attack': '상대의 공략(우리 수비 진영 깊이 들어온 장면)', 'space': '공간 싸움(보로노이 점유 장면)'}


def data_uri(path, mime):
    import base64
    return f'data:{mime};base64,' + base64.b64encode(Path(path).read_bytes()).decode('ascii')


def clip_section(info_cur, clips_dir, ball=None, ballpts=None, video=True):
    """Video of every scene next to its vector picture; the videos are embedded so that the one html file shows them anywhere."""
    folder = Path(clips_dir)
    scenes = json.loads((folder / 'scenes.json').read_text(encoding='utf-8'))
    out = ['<h2>8. 장면 영상과 이동 그림</h2><p class="note">왼쪽은 그 장면의 영상(장면 6초 전부터 8초 뒤까지), 오른쪽은 같은 순간의 선수 이동 그림입니다. 영상은 재생 버튼을 눌러 보세요.</p>'] if video else ['<h2>8. 장면 사진과 선수 이동 그림</h2><p class="note">왼쪽은 그 장면의 사진, 오른쪽은 장면 5초 전부터 3초 뒤까지 선수가 어떻게 움직였는지 화살표로 그린 그림입니다. 굵은 화살표는 빠르게 달린 선수입니다.</p>']
    for n, sc in enumerate(scenes, 1):
        data = info_cur[sc['half']]['data']
        bp = (ballpts or {}).get(sc['name']) or []
        svg, stats = scene_svg(data, sc['at'], shade=(sc['kind'] == 'space'), ball=bp)
        clip = folder / sc['clip']
        video_html = f'<video controls preload="metadata" playsinline style="width:100%;border-radius:8px" src="{data_uri(clip, "video/mp4")}" poster="{data_uri(folder / sc["still"], "image/jpeg")}"></video>' if clip.is_file() else ''
        if not video:
            still = folder / sc['still']
            video_html = f'<img alt="장면 사진" style="width:100%;border-radius:8px" src="{data_uri(still, "image/jpeg")}">' if still.is_file() else ''
            svg2, _ = path_svg(data, sc['at'], ball=bp)
            svg = svg2 or svg
        fast = sum(1 for v in stats.get('ours', []) if v >= 4.0)
        fast_o = sum(1 for v in stats.get('theirs', []) if v >= 4.0)
        lane_text = f'{LANES[sc["lane"]]} 쪽에서 {sc["players"]}명' if sc.get('players') else ''
        extra = ''
        if sc['kind'] == 'their_attack':
            extra = ' 박스까지 들어왔습니다.' if sc.get('reached') else ' 박스 밖에서 끊겼습니다.'
        t0 = min(data)
        ball_text = ''
        if len(bp) >= 2:
            dist = sum(math.hypot(b[1] - a[1], b[2] - a[2]) for a, b in zip(bp, bp[1:]) if b[0] - a[0] <= 1.0 and math.hypot(b[1] - a[1], b[2] - a[2]) <= 40)
            speeds = [math.hypot(b[1] - a[1], b[2] - a[2]) / (b[0] - a[0]) for a, b in zip(bp, bp[1:]) if 0 < b[0] - a[0] <= 0.4 and math.hypot(b[1] - a[1], b[2] - a[2]) <= 40]
            ball_text = f' 노란 선은 사용자님이 표시한 공의 경로입니다(공이 표시된 {len(bp)}프레임, 이동 거리 약 {dist:.0f}m' + (f', 가장 빠를 때 초속 약 {max(speeds):.0f}m)' if speeds else ')') + '. 공을 지면에 있는 것으로 계산해서 뜬 공은 위치가 어긋날 수 있습니다.'
        elif b := (ball or {}).get(sc['name']):
            ball_text = ''
        out.append(f'<div class="card"><span class="tag">{sc["half"]}</span><span class="tag">{esc(KIND_TEXT[sc["kind"]])}</span><b>{clock(sc["at"] - t0)}</b>'
                   f'<div class="grid"><div>{video_html}</div><div>{svg or ""}</div></div>'
                   f'<p class="note">{esc(lane_text)}{esc(extra)} 전속으로 달린 선수는 우리 {fast}명, 상대 {fast_o}명입니다.{esc(ball_text)}</p></div>')
    return ''.join(out)



RESULT_TEXT = {'goal': '골', 'saved': '유효슈팅(골키퍼가 막음)', 'blocked': '수비가 막음', 'post': '골대를 맞힘', 'off': '빗나감'}


def attack_waves(data, side):
    """Waves of box entries of one team with how fast the team's front moved before them: the front (mean of the two most advanced outfield players) rose by `advance` metres in the 12 s before."""
    out = []
    flip = (lambda pts: pts) if side == 'ours' else (lambda pts: [(i, -u, -v) for i, u, v in pts])
    for w in waves(entries(data, side, 'box')):
        t = w[0][0]
        now, before = data.get(t), data.get(t - 12)
        if not now or not before:
            continue
        a, b = shape(flip(now[side])), shape(flip(before[side]))
        advance = (a['att'] - b['att']) if a and b else None
        out.append({'t': t, 'players': len({e[1] for e in w}), 'advance': advance})
    return out


def attack_section(matches, info):
    out = ['<h2>6. 유효한 공격과 슛, 기대 득점(xG)</h2>',
           '<h3>6-1. 유효한 공격(선수 위치로 본 근사)</h3><p class="note">공 정보 없이 선수 위치만으로 센 값입니다. 박스에 선수가 들어간 공격 가운데, 직전 12초 동안 가장 앞선 두 선수의 위치가 15m 이상 앞으로 나간 빠른 전개를 "직접 공격"(공격 데이터 업체의 직접 공격 정의를 위치로 옮긴 것, <a href="https://www.statsperform.com/page-block-preview/advanced-metrics-sequences-and-possessions/" style="color:#9ee6ff">Stats Perform</a>), 박스에 세 명 이상 들어간 공격을 "다수 침투"로 봅니다. 슛이 있었는지는 알 수 없습니다.</p>',
           '<div class="card"><table><tr><th>경기와 구간</th><th>우리: 박스 진입 공격</th><th>그중 직접 공격</th><th>그중 다수 침투</th><th>상대: 박스 진입 공격</th><th>그중 직접 공격</th></tr>']
    for mname, halves in matches:
        for h in halves:
            data = info[(mname, h)]['data']
            o, t = attack_waves(data, 'ours'), attack_waves(data, 'theirs')
            d = lambda ws: sum(1 for w in ws if w['advance'] is not None and w['advance'] >= 15)
            out.append(f'<tr><td>{esc(mname[:5])} {h}</td><td>{len(o)}번</td><td>{d(o)}번</td><td>{sum(1 for w in o if w["players"] >= 3)}번</td><td>{len(t)}번</td><td>{d(t)}번</td></tr>')
    out.append('</table></div>')
    return out


def shots_section(shots_dir, matches):
    out = ['<h3>6-2. 슛과 유효슈팅, xG(사용자님이 표시한 것)</h3>']
    folder = Path(shots_dir) if shots_dir else None
    cand = {}
    if folder and (folder / 'candidates.json').is_file():
        cand = {c['id']: c for c in json.loads((folder / 'candidates.json').read_text(encoding='utf-8'))['candidates']}
    tags = {}
    if folder and (folder / 'tags').is_dir():
        for f in sorted((folder / 'tags').glob('*.json')):
            try:
                tags[f.stem] = json.loads(f.read_text(encoding='utf-8'))
            except ValueError:
                continue
    done = sum(1 for k in cand if k in tags)
    out.append('<p class="note">슛 태깅 화면(/shots)에서 박스에 들어간 장면마다 "슛 아님, 빗나감, 유효슈팅, 수비가 막음, 골대를 맞힘, 골"과 슛 위치를 표시한 결과입니다. xG는 슛 위치(거리와 각도)만 쓴 대략적인 모델의 값이라 슛끼리 비교하는 용도이고 실제 확률은 아닙니다(아마추어에 맞게 검증되지 않음). 표시한 장면 '
               f'{done}/{len(cand)}개.</p>')
    if done == 0 and not any(k.startswith('x-') for k in tags):
        out.append('<div class="card"><p>아직 표시한 슛이 없어서 이 장은 비어 있습니다. 표시가 끝나면 다시 만들면 경기별 슛, 유효슈팅, 막힌 슛, 골, xG 합계와 슛 목록이 여기에 채워집니다.</p></div>')
        return out
    label = {m[0][:5]: m[0] for m in matches}
    key_of = {'prev': matches[0][0], 'cur': matches[1][0]}
    out.append('<div class="card"><table><tr><th>경기와 팀</th><th>슛</th><th>유효슈팅</th><th>수비가 막음</th><th>골대</th><th>빗나감</th><th>골</th><th>xG 합계</th></tr>')
    shots_list = []
    for mkey in ('prev', 'cur'):
        for side, side_text in (('ours', '우리'), ('theirs', '상대')):
            rows = []
            for tid, t in tags.items():
                if t.get('result') in (None, 'none'):
                    continue
                c = cand.get(tid)
                match = c['match'] if c else t.get('match')
                sd = t.get('side')
                if match == mkey and sd == side:
                    rows.append((tid, t, c))
            n = lambda r: sum(1 for _, t, _ in rows if t['result'] == r)
            xgs = sum(t.get('xg', 0) for _, t, _ in rows)
            out.append(f'<tr><td>{esc(key_of[mkey][:5])} {side_text}</td><td>{len(rows)}</td><td>{n("saved") + n("goal")}</td><td>{n("blocked")}</td><td>{n("post")}</td><td>{n("off")}</td><td>{n("goal")}</td><td>{xgs:.2f}</td></tr>')
            shots_list += [(mkey, side, tid, t, c) for tid, t, c in rows]
    out.append('</table><p class="note">유효슈팅은 골키퍼가 막은 슛과 골의 합입니다.</p></div>')
    if shots_list:
        out.append('<div class="card"><h3 style="margin-top:0">슛 목록</h3><table><tr><th>경기</th><th>구간과 시각</th><th>팀</th><th>결과</th><th>xG</th></tr>')
        for mkey, side, tid, t, c in sorted(shots_list, key=lambda x: (x[0], (x[4] or {}).get('half', x[3].get('half', '')), (x[4] or {}).get('minute', x[3].get('minute', 0)))):
            half = c['half'] if c else t.get('half')
            minute = c['minute'] if c else t.get('minute', 0)
            out.append(f'<tr><td>{esc(key_of[mkey][:5])}</td><td>{half} {int(minute)}분 {int((minute % 1) * 60):02d}초{" (직접 추가)" if t.get("manual") else ""}</td><td>{"우리" if side == "ours" else "상대"}</td><td>{esc(RESULT_TEXT.get(t["result"], t["result"]))}</td><td>{t.get("xg", 0):.2f}</td></tr>')
        out.append('</table></div>')
    return out


def clock(t):
    s = int(t)
    return f'{s // 60}분 {s % 60:02d}초'


def build(args):
    prev = {'전반': read(args.prev_h1), '후반': read(args.prev_h2)}
    cur = {'전반': read(args.cur_h1), '후반': read(args.cur_h2, end=args.cur_h2_end)}
    matches = [('지난 경기', prev), ('오늘 경기', cur)]
    info = {}
    for mname, halves in matches:
        for hname, data in halves.items():
            th, bx = entries(data, 'ours', 'third'), entries(data, 'ours', 'box')
            oth, obx = entries(data, 'theirs', 'third'), entries(data, 'theirs', 'box')
            ow = [wave_info(w, data, 'ours', [e[0] for e in bx]) for w in waves(th)]
            tw = [wave_info(w, data, 'theirs', [e[0] for e in obx]) for w in waves(oth)]
            for w in tw:
                w['response'] = response(data, w['t'])
            info[(mname, hname)] = {'data': data, 'shape': half_shape(data), 'th': th, 'bx': bx, 'oth': oth, 'obx': obx, 'ow': ow, 'tw': tw, 'space': space_shares(data)}
    out = [f'<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>경기 상세 보고서</title><style>{CSS}</style></head><body><main>']
    out.append('<h1>두 경기 상세 보고서: 공격 루트, 상대의 공략과 우리의 대처, 공간 싸움</h1><p class="note">같은 우리 팀(어두운 옷)의 두 경기입니다. 오늘 경기와 지난 경기를 비교합니다. 정규 시간 전반과 후반만 봤습니다. 모든 그림은 우리 골대가 왼쪽, 우리가 공격하는 방향이 오른쪽이며, "왼쪽"과 "오른쪽"은 우리 팀 기준입니다.</p>')

    # ---- 1 summary
    out.append('<h2>1. 한눈에 보는 요약</h2><div class="card">')
    for mname, halves in matches:
        for hname in halves:
            r = info[(mname, hname)]
            t_lane = lane_counts(r['th'])
            o_lane = lane_counts(r['oth'])
            top = lambda c: LANES[c.index(max(c))] if sum(c) else '-'
            ow, tw = r['ow'], r['tw']
            out.append(f'<p><b>{esc(mname)} {hname}</b>: 우리는 {sum(t_lane)}번 공격 진영으로 들어갔고 그중 {pct(sum(1 for w in ow if w["reached"]), len(ow))}%가 박스까지 이어졌습니다. 가장 많이 들어간 길은 {top(t_lane)}입니다. '
                       f'상대는 우리 진영으로 {sum(o_lane)}번 들어왔고 가장 많이 들어온 길은 {top(o_lane)}입니다.</p>')
    out.append('</div>')

    # ---- 2 team shape
    out.append('<h2>2. 팀 모양: 줄 높이와 간격</h2><p class="note">줄 높이는 우리 골대에서의 거리입니다. 줄 사이가 16m를 넘으면 벌어졌다고 봅니다.</p><div class="card"><table><tr><th>경기와 구간</th><th>수비 줄 높이</th><th>수비~중원 간격</th><th>중원~공격 간격</th><th>팀 전체 길이</th><th>옆 폭</th></tr>')
    for mname, halves in matches:
        for hname in halves:
            s = info[(mname, hname)]['shape']
            if not s:
                continue
            out.append(f'<tr><td>{esc(mname[:5])} {hname}</td><td>{fmt(s["def"])}m ({words_def(s["def"])})</td><td class="{"bad" if s["gap_dm"] >= 16 else ""}">{fmt(s["gap_dm"])}m ({words_gap(s["gap_dm"])})</td>'
                       f'<td class="{"bad" if s["gap_ma"] >= 16 else ""}">{fmt(s["gap_ma"])}m ({words_gap(s["gap_ma"])})</td><td>{fmt(s["length"])}m ({words_length(s["length"])})</td><td>{fmt(s["width"])}m ({words_width(s["width"])})</td></tr>')
    out.append('</table></div>')
    out.append('<h3>오늘 경기 5분 단위 변화</h3><div class="card"><table><tr><th>구간</th><th>수비 줄 높이</th><th>수비~중원</th><th>중원~공격</th><th>팀 길이</th><th>옆 폭</th></tr>')
    for hname, data in cur.items():
        for r in bin_rows(data):
            out.append(f'<tr><td>{hname} {r["label"]}</td><td>{fmt(r["def"])}m</td><td class="{"bad" if r["gap_dm"] >= 16 else ""}">{fmt(r["gap_dm"])}m</td><td class="{"bad" if r["gap_ma"] >= 16 else ""}">{fmt(r["gap_ma"])}m</td><td>{fmt(r["length"])}m</td><td>{fmt(r["width"])}m</td></tr>')
    out.append('</table></div>')

    # ---- 3 attack routes
    out.append('<h2>3. 공격 루트: 어느 길로 공격 진영과 박스에 들어갔나</h2>'
               '<p class="note">"들어간 횟수"는 우리 선수가 공격 진영 3분의 1 지점(우리 골대에서 약 59m)을 넘어 들어간 횟수이고, 박스는 상대 박스 안으로 들어간 횟수입니다. 공을 보지 않으므로 공이 그 길로 갔는지는 알 수 없고 선수들이 그 길로 달려 들어갔다는 뜻입니다.</p>')
    rows = [(f'{mname[:5]} {h}', lane_counts(info[(mname, h)]['th'])) for mname, halves in matches for h in halves]
    out.append('<div class="card"><h3 style="margin-top:0">공격 진영에 들어간 길</h3>' + bar_table('경기와 구간', rows) + '</div>')
    rows = [(f'{mname[:5]} {h}', lane_counts(info[(mname, h)]['bx'])) for mname, halves in matches for h in halves]
    out.append('<div class="card"><h3 style="margin-top:0">상대 박스에 들어간 길</h3>' + bar_table('경기와 구간', rows) + '</div>')
    out.append('<div class="legend note"><span><i class="sw" style="background:#6db8ff"></i>우리 팀 이동</span><span><i class="sw" style="background:#ff8a6b"></i>상대 팀 이동</span> 화살표 굵기는 들어간 횟수, 숫자는 횟수입니다.</div><div class="grid">')
    for mname, halves in matches:
        for h in halves:
            r = info[(mname, h)]
            out.append(f'<div class="card"><span class="tag">{esc(mname[:5])}</span><span class="tag">{h}</span><b>공격 진영 진입 평균 이동</b>{route_map(r["th"], r["oth"])}</div>')
    out.append('</div>')
    out.append('<h3>오늘 경기에서 박스까지 이어진 공격의 선수 이동</h3><div class="grid">')
    shown = 0
    for h in ('전반', '후반'):
        r = info[(matches[1][0], h)]
        reached = sorted([w for w in r['ow'] if w['reached']], key=lambda w: -w['players'])[:2]
        for w in sorted(reached, key=lambda w: w['t']):
            svg, stats = scene_svg(r['data'], w['t'] + 4)
            if svg:
                fast = sum(1 for s in stats.get('ours', []) if s >= 4.0)
                out.append(f'<div class="card"><span class="tag">{h}</span><span class="tag">{by_lane(w["lane"])} 진입</span><b>{clock(w["t"] - min(r["data"]))}</b>{svg}<p class="note">이 길로 우리 선수 {w["players"]}명이 공격 진영에 들어갔고 4초 뒤 장면입니다. 전속으로 달린 우리 선수는 {fast}명입니다.</p></div>')
                shown += 1
    out.append('</div>')

    # ---- 4 opponent attack and our answer
    out.append('<h2>4. 상대의 공략과 우리의 대처</h2><p class="note">상대가 우리 공격 진영이 아닌 우리 수비 진영(우리 골대에서 약 30m 안)으로 들어온 움직임을 "공략"으로 봅니다. 우리의 대처는 그 뒤 5초 동안 우리 수비 줄이 어떻게 움직였는지로 봅니다. 먼 쪽 상대 선수 일부는 잡히지 않아서 상대의 공략 횟수는 실제보다 적게 보일 수 있습니다.</p>')
    rows = [(f'{mname[:5]} {h}', lane_counts(info[(mname, h)]['oth'])) for mname, halves in matches for h in halves]
    out.append('<div class="card"><h3 style="margin-top:0">상대가 우리 수비 진영에 들어온 길</h3>' + bar_table('경기와 구간', rows) + '</div>')
    out.append('<div class="card"><h3 style="margin-top:0">공략이 있을 때 우리 수비 줄의 반응</h3><table><tr><th>경기와 구간</th><th>상대의 공략 횟수</th><th>우리 박스까지 들어옴</th><th>우리가 줄을 내려 막음</th><th>줄 유지</th><th>줄을 올려 맞섬</th><th>공략 뒤 수비~중원 간격</th></tr>')
    for mname, halves in matches:
        for h in halves:
            tw = info[(mname, h)]['tw']
            resp = [w['response'] for w in tw if w.get('response')]
            down = sum(1 for d, g in resp if d <= -4)
            up = sum(1 for d, g in resp if d >= 4)
            hold = len(resp) - down - up
            gap = mean([g for d, g in resp])
            out.append(f'<tr><td>{esc(mname[:5])} {h}</td><td>{len(tw)}번</td><td>{sum(1 for w in tw if w["reached"])}번 ({pct(sum(1 for w in tw if w["reached"]), len(tw))}%)</td><td>{down}번</td><td>{hold}번</td><td>{up}번</td><td>{fmt(gap)}m</td></tr>')
    out.append('</table></div>')
    out.append('<h3>오늘 경기에서 상대가 우리 수비 진영에 깊게 들어온 장면의 선수 이동</h3><div class="grid">')
    for h in ('전반', '후반'):
        r = info[(matches[1][0], h)]
        deep = sorted([w for w in r['tw'] if w['reached']] or r['tw'], key=lambda w: -w['max_speed'])[:2]
        for w in sorted(deep, key=lambda w: w['t']):
            svg, stats = scene_svg(r['data'], w['t'] + 2)
            if svg:
                resp = w.get('response')
                text = ''
                if resp:
                    d, g = resp
                    text = f' 이 장면 뒤 우리 수비 줄은 {"내려서서 막았고" if d <= -4 else "높이를 유지했고" if d < 4 else "올라가서 맞섰고"}, 수비~중원 간격은 {g:.0f}m였습니다.'
                out.append(f'<div class="card"><span class="tag">{h}</span><span class="tag">상대 {LANES[w["lane"]]} 진입</span><span class="tag">{"박스까지 들어옴" if w["reached"] else "박스 밖에서 끊김"}</span><b>{clock(w["t"] - min(r["data"]))}</b>{svg}<p class="note">상대 선수 {w["players"]}명이 이 길로 들어왔고 가장 빠른 선수는 3초에 약 {w["max_speed"]:.0f}m를 움직였습니다.{esc(text)}</p></div>')
    out.append('</div>')

    # ---- 5 second balls and space
    out.append('<h2>5. 세컨드 볼과 공간 싸움</h2><p class="note">공이 뜬 뒤 떨어지는 경합 공의 주인(세컨드 볼)은 공 정보가 없어서 직접 셀 수 없습니다. 대신 두 팀이 8~12명씩 잡힌 순간만 골라서 (1) 가장 가까운 선수에게 땅을 나누는 보로노이 점유와 (2) 양 팀 선수가 4m 안에서 맞붙은 경합 구역을 봅니다. 공이 아니라 선수 위치만 본 근사입니다.</p>')
    out.append('<div class="card"><table><tr><th>경기와 구간</th><th>쓴 순간</th><th>우리 수비 3분의 1 점유</th><th>중원 3분의 1 점유</th><th>공격 3분의 1 점유</th></tr>')
    for mname, halves in matches:
        for h in halves:
            sp = info[(mname, h)]['space']
            n = len(info[(mname, h)]['data'])
            if sp['thirds']:
                a, b, c = sp['thirds']
                out.append(f'<tr><td>{esc(mname[:5])} {h}</td><td>{sp["seconds"]}초 ({pct(sp["seconds"], n)}%)</td><td>{pct(a * 100, 100)}%</td><td>{pct(b * 100, 100)}%</td><td>{pct(c * 100, 100)}%</td></tr>')
    out.append('</table><p class="note">점유는 그 구역 땅 가운데 우리 선수가 더 가까운 땅의 비율입니다. 50%보다 크면 그 구역에서 우리가 공간 우위입니다.</p></div>')
    out.append('<div class="grid">')
    for mname, halves in matches:
        for h in halves:
            sp = info[(mname, h)]['space']
            out.append(f'<div class="card"><span class="tag">{esc(mname[:5])}</span><span class="tag">{h}</span><b>양 팀이 맞붙은 구역</b>{contested_svg(sp["contested"])}<p class="note">노란색이 진할수록 두 팀 선수가 4m 안에서 자주 맞붙은 곳입니다. 세컨드 볼이 떨어질 가능성이 큰 곳으로 볼 수 있습니다.</p></div>')
    out.append('</div>')
    out.append('<h3>오늘 경기 보로노이 점유 장면 (파랑 우리 땅, 붉은색 상대 땅)</h3><div class="grid">')
    for h in ('전반', '후반'):
        r = info[(matches[1][0], h)]
        cands = [w for w in r['ow'] + r['tw'] if balanced(r['data'].get(w['t'] + 2, {'ours': [], 'theirs': []}))]
        for w in sorted(cands, key=lambda w: -w['players'])[:1]:
            svg, stats = scene_svg(r['data'], w['t'] + 2, shade=True)
            if svg:
                out.append(f'<div class="card"><span class="tag">{h}</span><b>{clock(w["t"] - min(r["data"]))}</b>{svg}<p class="note">이 순간 두 팀이 8~12명씩 잡혔습니다. 화살표는 3초 전부터의 이동입니다.</p></div>')
    out.append('</div>')

    # ---- 6 comparison and tasks
    out.extend(attack_section(matches, info))
    out.extend(shots_section(args.shots_dir, matches))
    out.append('<h2>7. 두 경기 비교와 다음 경기 과제</h2><div class="card">')
    pa, ca = info[(matches[0][0], '후반')]['shape'], info[(matches[1][0], '후반')]['shape']
    if pa and ca:
        out.append(f'<p>수비~중원 간격: 지난 경기 후반 {pa["gap_dm"]:.0f}m, 오늘 후반 {ca["gap_dm"]:.0f}m. 중원~공격 간격: 지난 경기 후반 {pa["gap_ma"]:.0f}m, 오늘 후반 {ca["gap_ma"]:.0f}m. 팀 길이: 지난 경기 후반 {pa["length"]:.0f}m, 오늘 후반 {ca["length"]:.0f}m.</p>')
    tasks = []
    for h in ('전반', '후반'):
        r = info[(matches[1][0], h)]
        s = r['shape']
        if s and s['gap_dm'] >= 16:
            tasks.append(f'오늘 {h}에 수비~중원 간격이 평균 {s["gap_dm"]:.0f}m로 벌어졌습니다. 수비 줄을 올릴 때 중원이 같이 올라와 간격을 15m 안팎으로 맞추는 연습이 필요합니다.')
        o = lane_counts(r['oth'])
        if sum(o) >= 5:
            k = o.index(max(o))
            tasks.append(f'오늘 {h}에 상대는 {LANES[k]} 쪽({o[k]}번, {pct(o[k], sum(o))}%)으로 가장 많이 들어왔습니다. 그쪽 윙백과 수비수의 간격과 커버를 점검해 주세요.')
    for h in ('전반', '후반'):
        r = info[(matches[1][0], h)]
        t = lane_counts(r['th'])
        if sum(t) >= 5:
            k = t.index(max(t))
            tasks.append(f'오늘 {h} 우리는 {by_lane(k)} 가장 많이 들어갔습니다({t[k]}번, {pct(t[k], sum(t))}%). 반대편으로 전환하는 움직임이 부족하지 않았는지 영상으로 확인해 주세요.')
    for t in tasks:
        out.append(f'<p>• {esc(t)}</p>')
    out.append('</div>')

    if args.clips_dir:
        ball = None
        bp = Path(args.clips_dir) / 'ball.json'
        if bp.is_file():
            ball = json.loads(bp.read_text(encoding='utf-8'))
        ballpts = None
        if args.ball_dir and args.calibrations:
            scenes = json.loads((Path(args.clips_dir) / 'scenes.json').read_text(encoding='utf-8'))
            def direction_of(path):
                return int(json.loads(Path(path).read_text(encoding='utf-8').splitlines()[0])['direction'])
            ballpts = ball_paths(args.ball_dir, args.calibrations, 'cam4', scenes, args.first_ball_clip, {'전반': direction_of(args.cur_h1), '후반': direction_of(args.cur_h2)})
        out.append(clip_section({h: info[(matches[1][0], h)] for h in ('전반', '후반')}, args.clips_dir, ball, ballpts, video=not args.no_video))
    out.append('<h2>9. 이 분석을 읽을 때</h2><div class="card"><p class="note">공을 보지 않고 선수 위치와 이동만 쓴 분석입니다. 먼 쪽 선수 일부는 영상에서 잡히지 않아 특히 상대 팀의 움직임이 실제보다 적게 나옵니다. 지난 경기 전반은 인식이 적은 구간이 많았고, 오늘 경기는 우리 팀이 11명을 넘게 잡힌 구간이 있습니다. 횟수와 비율은 두 경기를 비교하는 방향을 볼 때 쓰고, 한 번 한 번의 장면은 영상으로 다시 확인해 주세요.</p></div>')
    out.append('</main></body></html>')
    Path(args.out).write_text(''.join(out), encoding='utf-8')
    for k, v in info.items():
        print(k, 'third', len(v['th']), 'box', len(v['bx']), 'opp third', len(v['oth']), 'opp box', len(v['obx']), 'balanced s', v['space']['seconds'])


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    for name in ('prev-h1', 'prev-h2', 'prev-alerts-h1', 'prev-alerts-h2', 'cur-h1', 'cur-h2', 'cur-alerts-h1', 'cur-alerts-h2', 'out'):
        p.add_argument('--' + name, required=name != 'prev-alerts-h1' and name != 'prev-alerts-h2' and name != 'cur-alerts-h1' and name != 'cur-alerts-h2')
    p.add_argument('--cur-h2-end', type=float)
    p.add_argument('--no-video', action='store_true', help='print version: a picture of the scene and the movement arrows instead of the video')
    p.add_argument('--ball-dir', help='<store>/ball with the labels of the ball clips b55.. (scenes in order)')
    p.add_argument('--first-ball-clip', type=int, default=55)
    p.add_argument('--calibrations', help='calibrations.json of the camera (for the ball path in metres)')
    p.add_argument('--shots-dir', help='<store>/shots with candidates.json and tags/ of the /shots page')
    p.add_argument('--clips-dir', help='scenes.json and clips of scripts/make_scene_clips.py (and ball.json of track_ball_scenes.py); they are embedded in the html')
    build(p.parse_args())
