"""Pages about the shape and the habits of the two teams, made from the positions only (no ball, no names): see app/team_tactics.py for what the numbers mean.

`add_pages(halves, team, Page, save, clock)` is called by build_match_report.py after the team structure pages. Every page has charts drawn here and a few sentences that are
written from the numbers of this match (best and worst stretches, differences between the halves and between the teams), not from general rules.
"""
import statistics
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import team_tactics as tt  # noqa: E402
from review_shots import font  # noqa: E402

FONT = 'C:/Windows/Fonts/malgun.ttf'
FONT_BOLD = 'C:/Windows/Fonts/malgunbd.ttf'
OURS, THEIRS = (74, 201, 190), (255, 159, 60)
GRID, TEXT, MUTE, BG = (60, 74, 90), (232, 238, 244), (150, 160, 172), (20, 29, 39)
SCALE = 2


def _font(size, bold=False):
    return ImageFont.truetype(FONT_BOLD if bold else FONT, int(size * SCALE))


def _to_bgr(image):
    return cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)


def line_chart(series, width, height, title, unit, y_range=None, x_label='경기 시작 후 분'):
    """series: [(name, colour, [(minute, value)])] -> BGR image."""
    img = Image.new('RGB', (width * SCALE, height * SCALE), BG)
    d = ImageDraw.Draw(img)
    d.text((10 * SCALE, 6 * SCALE), title, font=_font(15, True), fill=TEXT)
    left, right, top, bottom = 52 * SCALE, (width - 40) * SCALE, 34 * SCALE, (height - 42) * SCALE
    values = [v for _, _, pts in series for _, v in pts]
    if not values:
        return _to_bgr(img)
    lo, hi = y_range if y_range else (min(values) * 0.9, max(values) * 1.1)
    if hi <= lo:
        hi = lo + 1
    xs = [m for _, _, pts in series for m, _ in pts]
    x0, x1 = min(xs), max(xs) if max(xs) > min(xs) else min(xs) + 1
    for k in range(5):
        y = bottom - (bottom - top) * k / 4
        d.line([left, y, right, y], fill=GRID, width=SCALE)
        d.text((4 * SCALE, y - 8 * SCALE), f'{lo + (hi - lo) * k / 4:.{0 if hi - lo >= 8 else 1}f}', font=_font(12), fill=MUTE)
    for name, colour, pts in series:
        xy = [(left + (right - left) * (m - x0) / (x1 - x0), bottom - (bottom - top) * (v - lo) / (hi - lo)) for m, v in pts]
        if len(xy) > 1:
            d.line(xy, fill=colour, width=3 * SCALE)
        for x, y in xy:
            d.ellipse([x - 4 * SCALE, y - 4 * SCALE, x + 4 * SCALE, y + 4 * SCALE], fill=colour)
    for m in sorted(set(xs)):
        x = left + (right - left) * (m - x0) / (x1 - x0)
        d.text((x - 14 * SCALE, bottom + 4 * SCALE), f'{m - 2.5:.0f}~{m + 2.5:.0f}', font=_font(11), fill=MUTE)
    lx = right - sum(int((len(n) * 11 + 34) * SCALE) for n, _, _ in series)
    for name, colour, _ in series:
        d.rectangle([lx, 10 * SCALE, lx + 12 * SCALE, 20 * SCALE], fill=colour)
        d.text((lx + 16 * SCALE, 6 * SCALE), name, font=_font(12), fill=TEXT)
        lx += int((len(name) * 11 + 34) * SCALE)
    d.text((left, (height - 20) * SCALE), f'가로: 경기 시작 후 분(5분 단위), 세로 단위: {unit}', font=_font(11), fill=MUTE)
    return _to_bgr(img)


def grid_image(grid, width, height, title, colour):
    """3 x 3 shares (rows: own third, middle, opponent third; columns: left, centre, right) -> BGR image."""
    img = Image.new('RGB', (width * SCALE, height * SCALE), BG)
    d = ImageDraw.Draw(img)
    d.text((10 * SCALE, 6 * SCALE), title, font=_font(15, True), fill=TEXT)
    top, left = 34 * SCALE, 10 * SCALE
    cw, ch = (width - 20) * SCALE / 3, (height - 44) * SCALE / 3
    peak = max(max(r) for r in grid) or 1
    for r in range(3):
        for c in range(3):
            x, y = left + c * cw, top + (2 - r) * ch                                # the opponent third at the top
            a = 0.12 + 0.88 * grid[r][c] / peak
            fill = tuple(int(BG[i] * (1 - a) + colour[i] * a) for i in range(3))
            d.rectangle([x + 2, y + 2, x + cw - 2, y + ch - 2], fill=fill)
            d.text((x + cw / 2 - 18 * SCALE, y + ch / 2 - 10 * SCALE), f'{grid[r][c]:.0f}%', font=_font(17, True), fill=(10, 14, 20) if a > 0.55 else TEXT)
    return _to_bgr(img)


def bar_chart(groups, width, height, title, colours):
    """groups: [(label, [(name, value)])] percentages -> BGR image."""
    img = Image.new('RGB', (width * SCALE, height * SCALE), BG)
    d = ImageDraw.Draw(img)
    d.text((10 * SCALE, 6 * SCALE), title, font=_font(15, True), fill=TEXT)
    left, right, top, bottom = 14 * SCALE, (width - 14) * SCALE, 40 * SCALE, (height - 40) * SCALE
    slot = (right - left) / max(1, len(groups))
    for i, (label, bars) in enumerate(groups):
        bw = slot / (len(bars) + 1)
        for j, (name, value) in enumerate(bars):
            x = left + i * slot + bw * (j + 0.5)
            h = (bottom - top) * min(100.0, value) / 100.0
            d.rectangle([x, bottom - h, x + bw * 0.9, bottom], fill=colours[j % len(colours)])
            d.text((x, bottom - h - 18 * SCALE), f'{value:.0f}%', font=_font(13, True), fill=TEXT)
            d.text((x + 4 * SCALE, bottom + 4 * SCALE), name, font=_font(12), fill=TEXT)
        d.text((left + i * slot + 6 * SCALE, bottom + 24 * SCALE), label, font=_font(13, True), fill=MUTE)
    return _to_bgr(img)


def _stretch(windows_list, label):
    """Best and worst stretch of a list [(second, value, count)]: text pieces in minutes."""
    usable = [w for w in windows_list if w[2] >= 120]
    if len(usable) < 2:
        return None
    hi, lo = max(usable, key=lambda w: w[1]), min(usable, key=lambda w: w[1])
    return {'hi': (int(hi[0] // 60), int(hi[0] // 60) + 5, hi[1]), 'lo': (int(lo[0] // 60), int(lo[0] // 60) + 5, lo[1])}


SIDE = {'left': '왼쪽', 'centre': '가운데', 'right': '오른쪽'}
MIRROR = {'left': 'right', 'centre': 'centre', 'right': 'left'}


def add_pages(halves, team, Page, save, clock):
    other = 'A' if team == 'B' else 'B'
    data = []
    for h in halves:
        s = tt.seconds_series(h['by_frame'], team, other, h['direction'], h['fps'], h['result']['frames'])
        data.append({'half': h, 'series': s, 'activity': tt.activity(h['by_frame'], team, h['fps'], h['result']['frames']),
                     'tight': tt.tightness(s), 'surges': tt.surges(s), 'open_ours': tt.open_side(s, 'ours_points'), 'open_theirs': tt.open_side(s, 'theirs_points')})

    def mins(w):
        return [(a / 60.0 + 2.5, b) for a, b, c in w if c >= 120]

    # ---- page 1: shape over time -------------------------------------------------------------------------------------------
    page = Page('팀 모양: 길이와 폭', '팀 전술', 'info')
    for k, x in enumerate(data):
        for r, (field, name, unit) in enumerate((('depth', '길이(가장 뒤와 가장 앞 선수의 거리)', 'm'), ('width', '폭(좌우로 퍼진 정도)', 'm'))):
            ours, theirs = mins(tt.windows(x['series'], 300, 'ours', field)), mins(tt.windows(x['series'], 300, 'theirs', field))
            image = line_chart([('우리', OURS, ours), ('상대', THEIRS, theirs)], 590, 190, f'{x["half"]["name"]} {name}', unit)
            page.paste(image, 56 + k * 600, 120 + r * 200, 590, 190)
    lines = []
    for x in data:
        n = x['half']['name']
        ds = [r['ours']['depth'] for r in x['series'].values() if r['ours']]
        ws = [r['ours']['width'] for r in x['series'].values() if r['ours']]
        dt = [r['theirs']['depth'] for r in x['series'].values() if r['theirs']]
        wt = [r['theirs']['width'] for r in x['series'].values() if r['theirs']]
        g1 = [r['ours']['gaps'][0] for r in x['series'].values() if r['ours']]
        g2 = [r['ours']['gaps'][1] for r in x['series'].values() if r['ours']]
        st = _stretch(tt.windows(x['series'], 300, 'ours', 'depth'), '길이')
        lines.append(f'{n}: 우리 팀은 평균 길이 {statistics.mean(ds):.0f}m, 폭 {statistics.mean(ws):.0f}m로 섰고 상대는 길이 {statistics.mean(dt):.0f}m, 폭 {statistics.mean(wt):.0f}m였습니다. '
                     f'수비 줄과 중원 사이는 평균 {statistics.mean(g1):.0f}m, 중원과 공격 사이는 {statistics.mean(g2):.0f}m 떨어져 있었습니다')
        if st:
            lines.append(f'{n} 우리 팀이 가장 길게 늘어난 구간은 {st["hi"][0]}~{st["hi"][1]}분({st["hi"][2]:.0f}m), 가장 촘촘했던 구간은 {st["lo"][0]}~{st["lo"][1]}분({st["lo"][2]:.0f}m)입니다. 늘어난 구간에서 줄 사이가 비는지 영상으로 확인할 만합니다')
    page.panel([56, 528, 1224, 676])
    page.bullets(74, 534, lines[:4], 1130, 14, None, 3)
    save(page, '팀 모양')

    # ---- page 2: where the teams stood ------------------------------------------------------------------------------------
    page = Page('어디에 머물렀나', '팀 전술', 'info')
    zone_lines = []
    for k, x in enumerate(data):
        ours, theirs = tt.zone_shares(x['series'], 'ours_points'), tt.zone_shares(x['series'], 'theirs_points')
        page.paste(grid_image(ours, 290, 200, f'{x["half"]["name"]} 우리 팀(위쪽이 상대 골문 쪽)', OURS), 56 + k * 600, 120, 290, 200)
        page.paste(grid_image(theirs, 290, 200, f'{x["half"]["name"]} 상대 팀(위쪽이 우리 골문 쪽)', THEIRS), 56 + k * 600 + 300, 120, 290, 200)
        third = sum(ours[2])
        cols = [sum(ours[r][c] for r in range(3)) for c in range(3)]
        theirs_third = sum(theirs[2])
        zone_lines.append(f'{x["half"]["name"]}: 우리 선수가 상대 진영 3분의 1에 있던 시간은 {third:.0f}%, 상대 선수가 우리 진영 3분의 1에 있던 시간은 {theirs_third:.0f}%였습니다. '
                          f'좌우로는 왼쪽 {cols[0]:.0f}%, 가운데 {cols[1]:.0f}%, 오른쪽 {cols[2]:.0f}%였습니다(우리 팀 기준)')
        theirs_cols = [sum(theirs[r][c] for r in range(3)) for c in range(3)]
        zone_lines.append(f'{x["half"]["name"]}: 가운데 길목에 선 시간은 우리 {cols[1]:.0f}%, 상대 {theirs_cols[1]:.0f}%입니다. 상대 진영 3분의 1 안에서는 가운데 {ours[2][1]:.0f}%, 양쪽 측면 {ours[2][0] + ours[2][2]:.0f}%였습니다')
        zone_lines.append(f'{x["half"]["name"]} 팀의 중심이 상대 진영에 있던 시간은 {tt.territory(x["series"])}%입니다. 공 위치를 쓰지 않아서 점유율이 아니라 팀이 선 위치의 비율입니다')
    page.panel([56, 340, 1224, 676])
    page.bullets(74, 352, zone_lines[:6], 1130, 14, None, 4)
    page.draw.text((74, 600), '각 칸의 숫자는 그 구역에서 선수가 확인된 시간의 비율이고, 모두 더하면 100%입니다. 잡힌 선수만 센 값입니다.', font=font(13), fill=(150, 160, 172))
    save(page, '머문 구역')

    # ---- page 3: open sides ----------------------------------------------------------------------------------------------
    page = Page('수비 줄이 비운 쪽', '팀 전술', 'info')
    groups_ours, groups_theirs, side_lines = [], [], []
    for x in data:
        o, t = x['open_ours'], x['open_theirs']
        if not o or not t:
            continue
        groups_ours.append((x['half']['name'], [(SIDE[k], v) for k, v in o.items()]))
        groups_theirs.append((x['half']['name'], [(SIDE[k], v) for k, v in t.items()]))
    colours3 = [(120, 170, 255), (180, 180, 190), (255, 210, 120)]
    if groups_ours:
        page.paste(bar_chart([(g[0], [(n, v) for n, v in g[1]]) for g in groups_ours], 580, 230, '우리 수비 줄이 비운 쪽(가장 깊은 4명 중 아무도 없던 시간 비율)', colours3), 56, 120, 580, 230)
        page.paste(bar_chart([(g[0], [(n, v) for n, v in g[1]]) for g in groups_theirs], 580, 230, '상대 수비 줄이 비운 쪽(상대 기준 왼쪽, 가운데, 오른쪽)', colours3), 644, 120, 580, 230)
    for x in data:
        o, t = x['open_ours'], x['open_theirs']
        if not o or not t:
            continue
        side_t = max(('left', 'right'), key=lambda k: t[k])
        side_o = max(('left', 'right'), key=lambda k: o[k])
        side_lines.append(f'{x["half"]["name"]}: 상대 수비 줄은 상대 기준 {SIDE[side_t]}을 {t[side_t]:.0f}% 비웠습니다. 우리 기준으로는 {SIDE[MIRROR[side_t]]} 측면이 더 열려 있었다는 뜻이라, 그쪽으로 공을 돌리는 연습이 효과적입니다')
        side_lines.append(f'{x["half"]["name"]}: 우리 수비 줄은 {SIDE[side_o]}을 {o[side_o]:.0f}% 비웠습니다. 상대가 그쪽으로 공을 돌리면 뒤에서 막을 사람이 늦는 구조입니다')
    page.panel([56, 370, 1224, 676])
    page.bullets(74, 384, side_lines[:4] or ['선수가 충분히 잡히지 않아 계산하지 못했습니다'], 1130, 15, None, 6)
    page.draw.text((74, 640), '수비 줄은 골키퍼를 뺀 가장 깊은 선수 4명입니다. 한 측면을 비운다고 해서 곧바로 실점으로 이어지는 것은 아닙니다.', font=font(13), fill=(150, 160, 172))
    save(page, '수비 줄이 비운 쪽')

    # ---- page 4: activity and closeness ----------------------------------------------------------------------------------
    page = Page('활동량과 상대와의 거리', '팀 전술', 'info')
    act_lines = []
    for k, x in enumerate(data):
        chunks = {}
        for sec, v in x['activity'].items():
            chunks.setdefault(sec // 300, []).append(v)
        act = [(w * 5 + 2.5, statistics.mean(v)) for w, v in sorted(chunks.items()) if len(v) >= 120]
        tchunks = {}
        for sec, v in x['tight'].items():
            tchunks.setdefault(sec // 300, []).append(v)
        tight = [(w * 5 + 2.5, statistics.mean(v)) for w, v in sorted(tchunks.items()) if len(v) >= 120]
        page.paste(line_chart([('우리 평균 속도', OURS, act)], 590, 190, f'{x["half"]["name"]} 잡힌 선수의 평균 속도', 'm/초'), 56 + k * 600, 120, 590, 190)
        page.paste(line_chart([('상대 선수에게서 가장 가까운 우리 선수까지', THEIRS, tight)], 590, 190, f'{x["half"]["name"]} 상대와의 평균 거리', 'm'), 56 + k * 600, 320, 590, 190)
        if len(act) >= 2:
            act_lines.append(f'{x["half"]["name"]}: 평균 속도는 {act[0][1]:.2f}m/초(처음 5분)에서 {act[-1][1]:.2f}m/초(마지막 구간)로 바뀌었고, 가장 활발했던 구간은 {max(act, key=lambda a: a[1])[0] - 2.5:.0f}분대, 가장 조용했던 구간은 {min(act, key=lambda a: a[1])[0] - 2.5:.0f}분대입니다')
        if tight:
            act_lines.append(f'{x["half"]["name"]}: 상대 선수 한 명에게서 가장 가까운 우리 선수까지는 평균 {statistics.mean(v for _, v in tight):.1f}m였고, 가장 멀어진 구간은 {max(tight, key=lambda a: a[1])[0] - 2.5:.0f}분대({max(a for _, a in tight):.1f}m)입니다. 거리가 멀수록 압박이 느슨했다는 뜻입니다')
    page.panel([56, 528, 1224, 676])
    page.bullets(74, 534, act_lines[:4], 1130, 14, None, 3)
    save(page, '활동량과 거리')

    # ---- page 5: surges --------------------------------------------------------------------------------------------------
    page = Page('팀 전체가 밀고 올라가거나 물러난 순간', '팀 전술', 'info')
    page.draw.text((56, 118), '팀의 중심이 6초 안에 12m 이상 움직인 순간 중 큰 것부터 8번씩입니다. 시각은 영상 시각이고, 장면을 확인할 때 사용하세요.', font=font(14), fill=(150, 160, 172))
    for k, x in enumerate(data):
        top8 = sorted(sorted(x['surges'], key=lambda v: -abs(v[2]))[:8])
        forward = sum(1 for v in x['surges'] if v[1] == 'forward')
        back = sum(1 for v in x['surges'] if v[1] == 'back')
        x0 = 56 + k * 600
        page.draw.text((x0, 150), f'{x["half"]["name"]}: 밀고 올라간 순간 {forward}번, 물러난 순간 {back}번', font=font(16, True), fill=(232, 238, 244))
        y = 186
        for second, direction, metres in top8:
            colour = (74, 201, 190) if direction == 'forward' else (255, 159, 60)
            page.draw.rectangle([x0, y + 3, x0 + 6, y + 24], fill=colour)
            page.draw.text((x0 + 18, y), f'{clock(x["half"]["offset"] + second)}', font=font(16, True), fill=(232, 238, 244))
            page.draw.text((x0 + 110, y), ('밀고 올라감 ' if direction == 'forward' else '물러남 ') + f'{abs(metres):.0f}m', font=font(16), fill=(232, 238, 244))
            y += 34
    page.panel([56, 480, 1224, 676])
    notes = ['위 시각은 팀 전체가 한꺼번에 위치를 옮긴 순간입니다. 영상에서 그 시각 앞뒤 10초를 보면 압박에 나선 것인지, 공을 잃고 물러난 것인지 확인할 수 있습니다',
             '물러난 순간(주황)이 연달아 나오면 수비 라인을 함께 내리는 약속이 있었는지, 밀고 올라간 순간(청록) 뒤에 팀의 길이가 늘어났는지를 함께 봐 주세요']
    page.bullets(74, 494, notes, 1130, 15, None, 8)
    save(page, '밀고 올라가기와 물러나기')
    add_goal_page(data, Page, save, clock)
    return data


def _mean_shape(series, first, last):
    """Mean of the team shape fields over the seconds first..last (inclusive) of a half, or None."""
    rows = [series[s] for s in range(int(first), int(last) + 1) if s in series and series[s]['ours'] and series[s]['theirs']]
    if len(rows) < 4:
        return None
    ours = [r['ours'] for r in rows]
    theirs = [r['theirs'] for r in rows]
    return {'depth': statistics.mean(o['depth'] for o in ours), 'width': statistics.mean(o['width'] for o in ours), 'front': statistics.mean(o['front'] for o in ours),
            'centre': statistics.mean(o['centre_u'] for o in ours), 'in_third': statistics.mean(sum(1 for u, _ in r['ours_points'] if u > PITCH_THIRD) for r in rows),
            'their_back': statistics.mean(t['back'] for t in theirs), 'their_depth': statistics.mean(t['depth'] for t in theirs)}


PITCH_THIRD = 14.8                              # beyond this u a player stands in the last third (the pitch is 89 m long)


def add_goal_page(data, Page, save, clock):
    """The team shape in the 12 seconds before each goal and before the attacks into the box that did not end in a goal, against the whole match."""
    rows, plain, missed, overall = [], [], [], []
    for x in data:
        h, series = x['half'], x['series']
        everything = _mean_shape(series, 0, max(series))
        if everything:
            overall.append(everything)
        for g in h['goals']:
            m = _mean_shape(series, g - h['offset'] - 12, g - h['offset'] - 1)
            if m:
                rows.append((h['name'], g, m))
        for e in h['events']:
            if e['kind'] == 'box_attack' and not e.get('goal_follow') and all(abs(e['time'] - g) > 40 for g in h['goals']):
                m = _mean_shape(series, e['time'] - h['offset'] - 12, e['time'] - h['offset'] - 1)
                if m:
                    missed.append(m)
    page = Page('득점 직전의 팀 모양', '팀 전술', 'good')
    page.draw.text((56, 118), '골이 나오기 직전 12초 동안의 평균입니다. 확인된 득점은 두 번째 카메라 구간을 빼고 이 영상에서 잡힌 것만 셌습니다.', font=font(14), fill=(150, 160, 172))
    heads = [('시각', 56), ('팀 길이', 360), ('팀 폭', 450), ('가장 앞 선수와 상대 골문 사이', 540), ('마지막 3분의 1에 선 선수', 800), ('상대 수비선과 상대 골문 사이', 1000)]
    for name, x0 in heads:
        page.draw.text((x0, 150), name, font=font(14, True), fill=(150, 160, 172))
    y = 180

    def row(label, m, colour, bold=False):
        nonlocal y
        page.draw.rectangle([56, y + 3, 62, y + 22], fill=colour)
        page.draw.text((74, y), label, font=font(15, True if bold else False), fill=(232, 238, 244))
        for value, x0 in ((f'{m["depth"]:.0f}m', 360), (f'{m["width"]:.0f}m', 450), (f'{44.5 - m["front"]:.0f}m', 540), (f'{m["in_third"]:.1f}명', 800), (f'{44.5 + m["their_back"]:.0f}m', 1000)):
            page.draw.text((x0, y), value, font=font(15), fill=(232, 238, 244))
        y += 30
    for name, g, m in rows[:9]:
        row(f'{name} {clock(g)} 득점', m, (255, 205, 86))
    y += 6
    if missed:
        mean_missed = {k: statistics.mean(m[k] for m in missed) for k in missed[0]}
        row(f'나오지 못한 박스 공격 {len(missed)}번', mean_missed, (255, 159, 60), True)
    if overall:
        mean_all = {k: statistics.mean(m[k] for m in overall) for k in overall[0]}
        row('경기 전체 평균', mean_all, (150, 160, 172), True)
    lines = []
    if rows and overall:
        goal_mean = {k: statistics.mean(m[k] for _, _, m in rows) for k in rows[0][2]}
        lines.append(f'득점 직전 {len(rows)}번의 평균을 경기 전체와 비교하면 팀 길이는 {goal_mean["depth"]:.0f}m 대 {mean_all["depth"]:.0f}m, 폭은 {goal_mean["width"]:.0f}m 대 {mean_all["width"]:.0f}m, '
                     f'마지막 3분의 1에 선 선수는 {goal_mean["in_third"]:.1f}명 대 {mean_all["in_third"]:.1f}명이었습니다')
        if missed:
            lines.append(f'골이 나오지 못한 박스 공격에서는 마지막 3분의 1에 선 선수가 평균 {mean_missed["in_third"]:.1f}명, 상대 수비선은 상대 골문에서 {44.5 + mean_missed["their_back"]:.0f}m였습니다. 득점 쪽은 {goal_mean["in_third"]:.1f}명, {44.5 + goal_mean["their_back"]:.0f}m입니다')
    lines.append('표본이 적어서 차이가 작으면 우연일 수 있습니다. 영상으로 장면을 보면서 인원이 정말 앞에 모였는지 함께 확인해 주세요')
    page.panel([56, 500, 1224, 676])
    page.bullets(74, 512, lines, 1130, 14, None, 6)
    save(page, '득점 직전 팀 모양')
