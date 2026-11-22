"""Space control report of team B as a PDF: python scripts/space_control_report.py <calibrations.json> <output folder> --half "<spec>" ... [--team B]

Pages: summary and how to read it, the five-minute windows of both halves, where on the pitch the team held space (average grid of each half), and the 12 seconds before
every goal against the match average. The numbers come from app/team_formation.py (positions only, no ball): a cell belongs to the team whose nearest player would get there first.
"""
import argparse
import json
import statistics
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from app import team_formation as tf, team_tactics as tt  # noqa: E402
import team_profile_cli  # noqa: E402
from app.team_style import short_name  # noqa: E402
from build_match_report import load_half  # noqa: E402

W, H = 1654, 1169                       # A4 landscape at 200 dpi
BG, PANEL, TEXT, MUTE, GRID = (255, 255, 255), (243, 246, 249), (28, 36, 46), (110, 122, 136), (214, 221, 229)
TEAL, ORANGE, GOLD = (20, 150, 140), (230, 130, 30), (214, 160, 20)
FONT, BOLD = 'C:/Windows/Fonts/malgun.ttf', 'C:/Windows/Fonts/malgunbd.ttf'


def font(size, bold=False):
    return ImageFont.truetype(BOLD if bold else FONT, size)


def clock(second):
    return f'{int(second // 60)}:{int(second % 60):02d}'


def new_page(title, subtitle=None):
    img = Image.new('RGB', (W, H), BG)
    d = ImageDraw.Draw(img)
    d.text((80, 60), title, font=font(46, True), fill=TEXT)
    if subtitle:
        d.text((80, 125), subtitle, font=font(24), fill=MUTE)
    return img, d


def wrap(d, text, x, y, width, size, fill=TEXT, gap=10):
    f = font(size)
    line = ''
    for word in text.split(' '):
        trial = (line + ' ' + word).strip()
        if d.textlength(trial, font=f) > width and line:
            d.text((x, y), line, font=f, fill=fill)
            y += size + gap
            line = word
        else:
            line = trial
    if line:
        d.text((x, y), line, font=f, fill=fill)
        y += size + gap
    return y


def colour_of(share):
    """0 = the opponent's space (orange) ... 1 = ours (teal), 0.5 = contested (light grey)."""
    a, b, mid = ORANGE, TEAL, (236, 238, 240)
    if share >= 0.5:
        t = (share - 0.5) * 2
        return tuple(int(mid[i] + (b[i] - mid[i]) * t) for i in range(3))
    t = (0.5 - share) * 2
    return tuple(int(mid[i] + (a[i] - mid[i]) * t) for i in range(3))


def heatmap(d, box, grid, label):
    x0, y0, x1, y1 = box
    rows, columns = len(grid), len(grid[0])
    cw, ch = (x1 - x0) / rows, (y1 - y0) / columns
    for r in range(rows):                                                  # u: own goal on the left, the attacked goal on the right
        for c in range(columns):                                           # v: own left at the top
            d.rectangle([x0 + r * cw, y0 + c * ch, x0 + (r + 1) * cw, y0 + (c + 1) * ch], fill=colour_of(grid[r][c]))
    d.rectangle([x0, y0, x1, y1], outline=TEXT, width=3)
    d.line([(x0 + x1) / 2, y0, (x0 + x1) / 2, y1], fill=TEXT, width=2)
    d.text((x0, y0 - 38), label, font=font(26, True), fill=TEXT)
    d.text((x0, y1 + 8), '우리 골문', font=font(20), fill=MUTE)
    d.text((x1 - 140, y1 + 8), '상대 골문', font=font(20), fill=MUTE)


def window_chart(d, box, series_list, title):
    x0, y0, x1, y1 = box
    d.text((x0, y0 - 40), title, font=font(26, True), fill=TEXT)
    d.rectangle([x0, y0, x1, y1], fill=PANEL)
    for k in range(5):
        y = y1 - (y1 - y0) * k / 4
        d.line([x0, y, x1, y], fill=GRID, width=2)
        d.text((x0 - 62, y - 14), f'{k * 25}%', font=font(20), fill=MUTE)
    count = max(len(pts) for _n, _c, pts in series_list)
    slot = (x1 - x0) / max(1, count)
    for j, (name, colour, pts) in enumerate(series_list):
        xy = [(x0 + slot * (i + 0.5), y1 - (y1 - y0) * v) for i, (_label, v) in enumerate(pts)]
        if len(xy) > 1:
            d.line(xy, fill=colour, width=7)
        for (x, y), (_label, v) in zip(xy, pts):
            d.ellipse([x - 9, y - 9, x + 9, y + 9], fill=colour)
            d.text((x - 24, y - 40 if j == 0 else y + 12), f'{v * 100:.0f}%', font=font(20, True), fill=colour)
        lx = x0 + 160 + j * 330
        d.rectangle([lx, y0 - 90 + 50, lx + 24, y0 - 90 + 70], fill=colour)
        d.text((lx + 34, y0 - 90 + 44), name, font=font(21), fill=TEXT)
    for i, (label, _v) in enumerate(series_list[0][2]):
        d.text((x0 + slot * (i + 0.5) - 40, y1 + 10), label, font=font(20), fill=MUTE)


def mean_grid(grids):
    rows, columns = len(grids[0]), len(grids[0][0])
    return [[sum(g[r][c] for g in grids) / len(grids) for c in range(columns)] for r in range(rows)]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('calibrations')
    parser.add_argument('output')
    parser.add_argument('--half', action='append', required=True)
    parser.add_argument('--team', default='B')
    team_profile_cli.add_argument(parser)
    args = parser.parse_args()
    team_profile_cli.setup(args)
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    calibrations = json.loads(Path(args.calibrations).read_text(encoding='utf-8'))
    other = 'A' if args.team == 'B' else 'B'
    halves = []
    for spec in args.half:
        half = load_half(spec, calibrations, args.team)
        series = tt.seconds_series(half['by_frame'], args.team, other, half['direction'], half['fps'], half['result']['frames'])
        grids = {}
        for second, row in series.items():
            grid = tf.control_grid(row['ours_points'], [(-u, -v) for u, v in row['theirs_points']])
            if grid is not None:
                grids[second] = grid
        summaries = {s: tf.control_summary(g) for s, g in grids.items()}
        halves.append({'half': half, 'series': series, 'grids': grids, 'summaries': summaries})
    everything = [c for x in halves for c in x['summaries'].values()]
    overall = {k: statistics.mean(c[k] for c in everything) for k in ('total', 'own_third', 'middle_third', 'opponent_third')}
    pages = []

    # ---- page 1 ---------------------------------------------------------------------------------------------------------------
    img, d = new_page('공간 지배 보고서', f'{short_name(args.team)}  /  선수 위치만으로 계산한 값입니다(공과 선수 이름은 쓰지 않았습니다)')
    y = 190
    for text in (
        f'경기 전체에서 {short_name(args.team)}가 차지한 공간은 평균 {overall["total"] * 100:.1f}%였습니다. 우리 진영 3분의 1에서는 {overall["own_third"] * 100:.0f}%, 중간 3분의 1에서는 {overall["middle_third"] * 100:.0f}%, 상대 진영 3분의 1에서는 {overall["opponent_third"] * 100:.0f}%를 차지했습니다.',
        '공간 지배는 "경기장의 한 지점에 어느 팀 선수가 먼저 도달할 수 있는가"를 계산한 값입니다. 선수가 달리는 속도는 모두 초속 5m로 같다고 보았고, 두 팀이 거의 같은 시간에 닿는 지점은 반반으로 나눴습니다.',
        '이 값은 공을 누가 가졌는지와는 다릅니다. 공 없이 위치만 본 값이므로 "점유율"이나 "경기 내용의 우열"로 읽으면 안 됩니다. 상대 진영 3분의 1의 비율이 높다는 것은 그 구역에 우리 선수가 상대 선수보다 가까이 서 있었다는 뜻입니다.'):
        y = wrap(d, text, 80, y, W - 160, 28, gap=12) + 20
    d.rectangle([80, y + 10, W - 80, y + 330], fill=PANEL)
    d.text((110, y + 30), '읽을 때 알아 둘 점', font=font(28, True), fill=TEXT)
    ny = y + 80
    for text in ('추적된 선수만 계산에 들어갑니다. 한 팀에서 보이는 선수는 보통 10명 안팎이고, 5명 미만이면 그 순간은 계산하지 않았습니다.',
                 '경기장 크기는 보정 값으로 추정한 길이 89m, 폭 62m를 썼습니다. 값이 달라지면 비율이 조금 달라질 수 있습니다.',
                 '두 번째 카메라 구간(카메라가 바뀐 구간의 골 2개)은 보정이 없어 이 보고서에 들어 있지 않습니다.'):
        ny = wrap(d, '· ' + text, 110, ny, W - 220, 24, gap=8) + 8
    pages.append(img)

    # ---- page 2: windows ----------------------------------------------------------------------------------------------------
    img, d = new_page('5분 단위 공간 지배', '청록 선은 경기장 전체, 주황 선은 상대 진영 3분의 1 구역에서 우리 팀이 차지한 비율')
    for k, x in enumerate(halves):
        windows = tf.control_by_window(x['summaries'], 300)
        usable = [w for w in windows if w[3] >= 60]
        pts_total = [(f'{int(w[0] // 60)}~{int(w[0] // 60) + 5}분', w[1]) for w in usable]
        pts_third = [(f'{int(w[0] // 60)}~{int(w[0] // 60) + 5}분', w[2]) for w in usable]
        window_chart(d, (150, 300 + k * 430, W - 120, 500 + k * 430), [('경기장 전체', TEAL, pts_total), ('상대 진영 3분의 1', ORANGE, pts_third)], f'{x["half"]["name"]}')
        x['windows'] = usable
    notes = []
    for x in halves:
        if x['windows']:
            hi, lo = max(x['windows'], key=lambda w: w[1]), min(x['windows'], key=lambda w: w[1])
            notes.append(f'{x["half"]["name"]}: 가장 높은 구간은 {int(hi[0] // 60)}~{int(hi[0] // 60) + 5}분({hi[1] * 100:.0f}%), 가장 낮은 구간은 {int(lo[0] // 60)}~{int(lo[0] // 60) + 5}분({lo[1] * 100:.0f}%)입니다.')
    wrap(d, '  '.join(notes), 80, 1075, W - 160, 22, MUTE)
    pages.append(img)

    # ---- page 3: heat maps --------------------------------------------------------------------------------------------------
    img, d = new_page('우리 팀이 공간을 잡은 위치', '반별 평균입니다. 청록색은 우리 팀이, 주황색은 상대 팀이 먼저 닿는 지점이고, 회색은 비슷한 지점입니다. 우리 팀은 오른쪽으로 공격합니다')
    for k, x in enumerate(halves):
        heatmap(d, (120, 330 + k * 400, 120 + 1400, 330 + k * 400 + 280), mean_grid(list(x['grids'].values())), f'{x["half"]["name"]} 평균')
    pages.append(img)

    # ---- page 4: goals ------------------------------------------------------------------------------------------------------
    img, d = new_page('득점 직전 12초의 공간 지배', '확인된 득점 중 보정이 있는 장면입니다. 경기 평균과 비교합니다')
    d.text((100, 200), '시각', font=font(24, True), fill=MUTE)
    for label, x0 in (('경기장 전체', 420), ('우리 진영', 760), ('중간', 1000), ('상대 진영', 1240)):
        d.text((x0, 200), label, font=font(24, True), fill=MUTE)
    y = 250
    goal_rows = []
    for x in halves:
        h = x['half']
        for g in h['goals']:
            rows = [x['summaries'][s] for s in range(int(g - h['offset'] - 12), int(g - h['offset']) - 1) if s in x['summaries']]
            if len(rows) < 4:
                continue
            m = {k: statistics.mean(r[k] for r in rows) for k in ('total', 'own_third', 'middle_third', 'opponent_third')}
            goal_rows.append(m)
            d.rectangle([90, y + 6, 100, y + 38], fill=GOLD)
            d.text((115, y), f'{h["name"]} {clock(g)} 득점', font=font(26), fill=TEXT)
            for key, x0 in (('total', 420), ('own_third', 760), ('middle_third', 1000), ('opponent_third', 1240)):
                d.text((x0, y), f'{m[key] * 100:.0f}%', font=font(26), fill=TEXT)
            y += 52
    y += 12
    d.line([90, y, W - 90, y], fill=GRID, width=3)
    y += 18
    d.text((115, y), '경기 평균', font=font(26, True), fill=MUTE)
    for key, x0 in (('total', 420), ('own_third', 760), ('middle_third', 1000), ('opponent_third', 1240)):
        d.text((x0, y), f'{overall[key] * 100:.0f}%', font=font(26, True), fill=MUTE)
    y += 70
    if goal_rows:
        mean_goal = {k: statistics.mean(r[k] for r in goal_rows) for k in goal_rows[0]}
        text = (f'득점 직전 {len(goal_rows)}골의 평균은 경기장 전체 {mean_goal["total"] * 100:.0f}%, 상대 진영 3분의 1 {mean_goal["opponent_third"] * 100:.0f}%로, '
                f'경기 평균({overall["total"] * 100:.0f}%, {overall["opponent_third"] * 100:.0f}%)과 비교됩니다. 득점 장면이 적어서 차이가 작으면 우연일 수 있으니, 장면 영상으로 함께 확인해 주세요.')
        wrap(d, text, 100, y, W - 200, 25)
    pages.append(img)

    for number, img in enumerate(pages, 1):
        img.save(out / f'page_{number:02d}.png')
    pages[0].save(out / 'space_control_report.pdf', save_all=True, append_images=pages[1:], resolution=200)
    print('wrote', out / 'space_control_report.pdf', len(pages), 'pages')


if __name__ == '__main__':
    main()
