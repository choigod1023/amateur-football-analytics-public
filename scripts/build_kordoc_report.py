"""Tactical report in the Korean official report style (개조식) as HWPX with kordoc, with figures in the colours of that style.

python scripts/build_kordoc_report.py --cur-h1 positions_h1.jsonl --cur-h2 positions_h2.jsonl --cur-h2-end 1405 --prev-h1 ... --prev-h2 ... --clips-dir clips --width-dir width \
    --shots-dir <store>/shots --kordoc-dir <folder with node_modules/kordoc> --edge <msedge.exe> --out-dir out

Writes <out-dir>/report.md, figures <out-dir>/figs/*.png, report.hwpx (kordoc generate --preset 개조식), report_render.html (kordoc render), report.pdf (the html printed by Edge) and lint.txt.
The colours follow the 개조식 preset of kordoc (navy 193AAA for headings, light blue E0E5FA / A0B4E6 for boxes, grey tables): our team navy, the opponent orange, a mark yellow, the pitch very light blue.
"""
import argparse
import json
import re
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_detailed_report as R  # noqa: E402
import build_player_brief as P  # noqa: E402
import build_slot_cards as C  # noqa: E402
import build_position_brief as B  # noqa: E402
import space_transition_metrics as M  # noqa: E402

NAVY, LIGHT, MID, ORANGE, YELLOW, INK, PITCH = '#193AAA', '#E0E5FA', '#A0B4E6', '#D9480F', '#F2B705', '#22303C', '#F5F7FD'
SWAP = {'#2d6a3e': PITCH, '#cfe8d4': MID, '#6db8ff': NAVY, '#ff8a6b': ORANGE, '#ffe14a': YELLOW, '#fff': INK, '#1b4a2a': PITCH}
NL = chr(10)


def recolour(svg):
    for a, b in SWAP.items():
        svg = svg.replace(a, b)
    return svg


def to_png(edge, svg, path, width=1140):
    h = int(width * 408 / 570)
    sized = svg.replace('width="100%"', 'width="%d"' % width, 1)
    html = '<!doctype html><meta charset="utf-8"><body style="margin:0;background:#fff">' + sized + '</body>'
    path = Path(path)
    if path.exists():
        path.unlink()
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        f = Path(tmp) / 'f.html'
        f.write_text(html, encoding='utf-8')
        # a separate browser profile per call: with a running Edge the command would be handed to it and write nothing
        proc = subprocess.Popen([edge, '--headless=new', '--disable-gpu', '--user-data-dir=' + str(Path(tmp) / 'prof'), '--hide-scrollbars', '--window-size=%d,%d' % (width, h), '--screenshot=%s' % path, f.as_uri()], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(60):
            if path.is_file() and path.stat().st_size > 0:
                break
            time.sleep(0.5)
        time.sleep(0.5)
        proc.kill()
    if not path.is_file():
        raise RuntimeError('Edge wrote no picture: %s' % path)


def bar_svg(rows):
    """Horizontal bars: share of our players per lane in the opponent's half for each match half."""
    w, h = 570, 408
    parts = ['<svg viewBox="0 0 %d %d" width="100%%" xmlns="http://www.w3.org/2000/svg"><rect width="%d" height="%d" fill="#fff"/>' % (w, h, w, h)]
    parts.append('<text x="285" y="26" text-anchor="middle" font-size="18" font-weight="700" fill="%s">상대 진영에서 공격할 때 우리 선수가 선 길(%%)</text>' % NAVY)
    colours = ['#C9CFE6', '#9AA7D6', '#6F81C8', NAVY]
    x0, y0, bw = 150, 54, 380
    for k, lane in enumerate(R.LANES):
        y = y0 + k * 66
        parts.append('<text x="8" y="%d" font-size="14" fill="%s">%s</text>' % (y + 30, INK, lane))
        for j, (name, shares) in enumerate(rows):
            v = shares[k]
            parts.append('<rect x="%d" y="%d" width="%.1f" height="11" fill="%s"/><text x="%.1f" y="%d" font-size="11" fill="%s">%.0f</text>' % (x0, y + j * 14, bw * v / 60, colours[j], x0 + bw * v / 60 + 4, y + j * 14 + 10, INK, v))
    for j, (name, _) in enumerate(rows):
        parts.append('<rect x="%d" y="%d" width="10" height="10" fill="%s"/><text x="%d" y="%d" font-size="11" fill="%s">%s</text>' % (150 + j * 100, h - 22, colours[j], 164 + j * 100, h - 13, INK, name))
    parts.append('</svg>')
    return ''.join(parts)


def formation_svg(stats):
    """Average place of the ten slots in the attack phase (left) and in the defence phase (right)."""
    w, h = 570, 408
    parts = ['<svg viewBox="0 0 %d %d" width="100%%" xmlns="http://www.w3.org/2000/svg"><rect width="%d" height="%d" fill="#fff"/>' % (w, h, w, h)]
    for k, (ph, title) in enumerate((('attack', '공격할 때(팀 중심이 상대 진영)'), ('defend', '수비할 때(팀 중심이 우리 진영)'))):
        ox, oy, sx = 10 + k * 280, 60, 2.9
        parts.append('<text x="%d" y="22" text-anchor="middle" font-size="13" font-weight="700" fill="%s">%s</text>' % (ox + 130, NAVY, title))
        parts.append('<rect x="%d" y="%d" width="%.0f" height="%.0f" fill="%s" stroke="%s" stroke-width="2"/>' % (ox, oy, R.L * sx, R.W * sx, PITCH, MID))
        parts.append('<line x1="%.0f" y1="%d" x2="%.0f" y2="%.0f" stroke="%s" stroke-width="1.5"/>' % (ox + R.L * sx / 2, oy, ox + R.L * sx / 2, oy + R.W * sx, MID))
        for s in C.SLOTS:
            pos = stats[ph][s]
            if not pos:
                continue
            x = ox + (pos[0] + R.L / 2) * sx
            y = oy + (pos[1] + R.W / 2) * sx
            parts.append('<circle cx="%.1f" cy="%.1f" r="9" fill="%s"/><text x="%.1f" y="%.1f" text-anchor="middle" font-size="9" fill="#fff">%s</text>' % (x, y, NAVY, x, y + 4, s))
        parts.append('<text x="%d" y="%.0f" text-anchor="middle" font-size="11" fill="%s">우리 골대 왼쪽, 공격 방향 오른쪽</text>' % (ox + 130, oy + R.W * sx + 20, INK))
    parts.append('</svg>')
    return ''.join(parts)


def centre_svg(data, t0, seconds=600):
    """The team centre (distance from our goal) over `seconds`, with the moments of the transitions marked."""
    w, h = 570, 408
    cs = M.smooth(M.centre_series(data))
    ts = [t for t in sorted(cs) if t0 <= t < t0 + seconds]
    parts = ['<svg viewBox="0 0 %d %d" width="100%%" xmlns="http://www.w3.org/2000/svg"><rect width="%d" height="%d" fill="#fff"/>' % (w, h, w, h)]
    parts.append('<text x="285" y="26" text-anchor="middle" font-size="16" font-weight="700" fill="%s">팀 중심의 위치(우리 골대에서의 거리)와 전환</text>' % NAVY)
    x0, x1, y0, y1 = 50, 550, 50, 360

    def X(t):
        return x0 + (t - t0) / seconds * (x1 - x0)

    def Y(u):
        return y1 - (u + 44.5) / 89 * (y1 - y0)
    parts.append('<rect x="%d" y="%d" width="%d" height="%d" fill="%s" stroke="%s"/>' % (x0, y0, x1 - x0, y1 - y0, PITCH, MID))
    parts.append('<line x1="%d" y1="%.0f" x2="%d" y2="%.0f" stroke="%s" stroke-dasharray="5 4"/><text x="%d" y="%.0f" font-size="10" fill="%s">중앙선</text>' % (x0, Y(0), x1, Y(0), MID, x0 + 4, Y(0) - 4, INK))
    for e in M.transitions(data):
        if t0 <= e['start'] < t0 + seconds:
            colour = ORANGE if e['kind'] == 'retreat' else NAVY
            parts.append('<rect x="%.1f" y="%d" width="%.1f" height="%d" fill="%s" opacity="0.15"/>' % (X(e['start']), y0, max(3, X(e['start'] + e['seconds']) - X(e['start'])), y1 - y0, colour))
    pts = ' '.join('%.1f,%.1f' % (X(t), Y(cs[t])) for t in ts)
    parts.append('<polyline points="%s" fill="none" stroke="%s" stroke-width="2.5"/>' % (pts, NAVY))
    parts.append('<text x="285" y="%d" text-anchor="middle" font-size="12" fill="%s">경과 시간(초) 0~%d, 주황 칸은 우리 진영으로 후퇴, 파랑 칸은 상대 진영으로 전진한 구간</text>' % (h - 14, INK, seconds))
    parts.append('</svg>')
    return ''.join(parts)


def gaejosik(lines):
    """Written with the visible marks (### 1. title, □, ○, -, ※); kordoc's 개조식 preset wants chapters as ##, □ items as ###, list items for ○ and the next levels, ※ as a paragraph."""
    out = []
    for ln in lines:
        m = re.match(r'^### \d+\. (.*)$', ln)
        if m:
            out.append('## ' + m.group(1))
        elif ln.startswith('□ '):
            out.append('### ' + ln[2:])
        elif ln.startswith('  ○ '):
            out.append('- ' + ln[4:])
        elif ln.startswith('    - '):
            out.append('  - ' + ln[6:])
        elif ln.startswith('  ※ '):
            out.append('※ ' + ln[4:])
        else:
            out.append(ln)
    return out


def main():
    p = argparse.ArgumentParser()
    for name in ('cur-h1', 'cur-h2', 'prev-h1', 'prev-h2', 'clips-dir', 'width-dir', 'kordoc-dir', 'edge', 'out-dir'):
        p.add_argument('--' + name, required=True)
    p.add_argument('--cur-h2-end', type=float)
    p.add_argument('--shots-dir')
    p.add_argument('--ball-dir')
    p.add_argument('--calibrations')
    args = p.parse_args()
    out = Path(args.out_dir)
    figs = out / 'figs'
    figs.mkdir(parents=True, exist_ok=True)
    c1, c2 = R.read(args.cur_h1), R.read(args.cur_h2, end=args.cur_h2_end)
    p1, p2 = R.read(args.prev_h1), R.read(args.prev_h2)
    sets = [('지난 경기 전반', p1), ('지난 경기 후반', p2), ('오늘 경기 전반', c1), ('오늘 경기 후반', c2)]
    met = {n: M.metrics(d) for n, d in sets}
    sh = {n: R.half_shape(d) for n, d in sets}
    ls = {n: B.attack_lane_share([d]) for n, d in sets}
    lane_share = {n: v[0] for n, v in ls.items()}
    lane_width = {n: v[1] for n, v in ls.items()}
    cards = C.stats([c1, c2])

    # ---- figures
    to_png(args.edge, bar_svg([(n.replace('지난 경기', '지난').replace('오늘 경기', '오늘'), lane_share[n]) for n, _ in sets]), out / 'fig_f1_lanes.png')
    to_png(args.edge, formation_svg(cards), out / 'fig_f2_shape.png')
    to_png(args.edge, centre_svg(c2, min(c2) + 120), out / 'fig_f3_centre.png')
    t2 = P.pick_gap_second(c2)
    to_png(args.edge, recolour(P.gap_svg(c2, t2)), out / 'fig_f4_gap.png')
    scenes = json.loads((Path(args.clips_dir) / 'scenes.json').read_text(encoding='utf-8'))
    s_by = lambda half, kind, k=0: [s for s in scenes if s['half'] == half and s['kind'] == kind][k]
    ballpts = None
    if args.ball_dir and args.calibrations:
        direction_of = lambda path: int(json.loads(Path(path).read_text(encoding='utf-8').splitlines()[0])['direction'])
        ballpts = R.ball_paths(args.ball_dir, args.calibrations, 'cam4', scenes, 55, {'전반': direction_of(args.cur_h1), '후반': direction_of(args.cur_h2)})
    sc = s_by('후반', 'their_attack', 0)
    svg, _ = R.path_svg(c2, sc['at'], ball=(ballpts or {}).get(sc['name']))
    to_png(args.edge, recolour(svg), out / 'fig_f5_their_attack.png')
    sc2 = s_by('전반', 'our_attack', 0)
    svg, _ = R.path_svg(c1, sc2['at'], ball=(ballpts or {}).get(sc2['name']))
    to_png(args.edge, recolour(svg), out / 'fig_f6_our_attack.png')
    wphotos = json.loads((Path(args.width_dir) / 'width_photos.json').read_text(encoding='utf-8'))
    (out / 'fig_f7_width_photo.jpg').write_bytes((Path(args.width_dir) / wphotos[-1]['file']).read_bytes())

    # ---- numbers for the text
    own_box = len(R.waves(R.entries(c1, 'ours', 'box'))) + len(R.waves(R.entries(c2, 'ours', 'box')))
    their_box = len(R.waves(R.entries(c1, 'theirs', 'box'))) + len(R.waves(R.entries(c2, 'theirs', 'box')))
    direct = sum(1 for d in (c1, c2) for w in R.attack_waves(d, 'ours') if w['advance'] is not None and w['advance'] >= 15)
    wide_cur = [lane_share[n][0] + lane_share[n][4] for n in ('오늘 경기 전반', '오늘 경기 후반')]
    wide_prev = [lane_share[n][0] + lane_share[n][4] for n in ('지난 경기 전반', '지난 경기 후반')]
    lm, rm = cards['attack']['LM'], cards['attack']['RM']
    shots = {'ours': 0, 'ours_on': 0}
    if args.shots_dir and (Path(args.shots_dir) / 'tags').is_dir():
        cand = {c['id']: c for c in json.loads((Path(args.shots_dir) / 'candidates.json').read_text(encoding='utf-8'))['candidates']}
        for f in (Path(args.shots_dir) / 'tags').glob('*.json'):
            t = json.loads(f.read_text(encoding='utf-8'))
            c = cand.get(f.stem)
            if c and c['match'] == 'cur' and t.get('side') == 'ours' and t.get('result') not in (None, 'none'):
                shots['ours'] += 1
                shots['ours_on'] += t['result'] in ('saved', 'goal')
    g = lambda v, d=0: '-' if v is None else '%.*f' % (d, v)
    gap_avg = statistics.mean([sh['오늘 경기 전반']['gap_dm'], sh['오늘 경기 후반']['gap_dm']])
    width_avg = statistics.mean([lane_width['오늘 경기 전반'], lane_width['오늘 경기 후반']])
    cur_sw = met['오늘 경기 전반']['switches'] + met['오늘 경기 후반']['switches']
    T, H = '오늘 경기 전반', '오늘 경기 후반'
    PT, PH = '지난 경기 전반', '지난 경기 후반'

    L = []
    L.append('# 경기 전술 분석 보고서(예시)' + NL)
    L.append('> 경기의 선수 위치를 분석하고 지난 경기와 비교하여 보완점을 도출함' + NL)
    L.append('### 1. 경기 개요 및 핵심 진단' + NL)
    L += ['□ 경기 개요', '  ○ 분석 대상: 지난 경기', '  ○ 분석 범위: 정규 시간 전반·후반', '  ○ 비교 대상: 지난 경기(동일 팀)', '  ※ 공을 따라가지 못하여 선수 위치와 이동만으로 분석함', '']
    L += ['□ 핵심 진단',
          '  ○ 공격 시 폭 협소: 상대 진영에서 양쪽 측면에 선 비율 %.0f%%·%.0f%%(지난 경기 %.0f%%·%.0f%%)' % (wide_cur[0], wide_cur[1], wide_prev[0], wide_prev[1]),
          '  ○ 수비~중원 간격 평균 %.0fm로 목표(15m 안팎) 초과' % gap_avg,
          '  ○ 측면 전환 부재: 전·후반 사이드 체인지로 볼 만한 이동 %d회' % cur_sw,
          '  ○ 마무리 부족: 박스 진입 공격 %d회 대비 직접 공격 %d회, 표시된 우리 슛 %d회(유효슈팅 %d회)' % (own_box, direct, shots['ours'], shots['ours_on']), '']

    L.append('### 2. 공간 사용' + NL)
    L += ['□ 폭과 길 점유',
          '  ○ 상대 진영 공격 시 팀 옆 폭 평균 %.0fm(경기장 폭 62m의 약 %.0f%%)' % (width_avg, 100 * width_avg / 62),
          '  ○ 왼쪽·오른쪽 미드필더 평균 폭 %.0fm·%.0fm로 계획(23m)보다 약 %.0fm 안쪽' % (abs(lm[1]), abs(rm[1]), 23 - (abs(lm[1]) + abs(rm[1])) / 2),
          '    - 가운데와 안쪽 길에 선수가 집중되어 상대 수비가 가운데에 모여 막기 쉬운 구조',
          '  ※ 선수 이름이 없는 추적이라 라인업 자리 기준으로 계산함', '']
    L.append('< 표 1. 상대 진영 공격 시 길별 우리 선수 위치 비율(%) >' + NL)
    L += ['| 구분 | 왼쪽 측면 | 왼쪽 하프스페이스 | 가운데 | 오른쪽 하프스페이스 | 오른쪽 측면 |', '|---|---|---|---|---|---|']
    for n, _ in sets:
        L.append('| ' + n + ' | ' + ' | '.join('%.0f' % v for v in lane_share[n]) + ' |')
    L += ['', '자료: 영상 추적 위치 기록(필드 7명 이상 확인, 팀 중심이 상대 진영인 순간)', '']
    L += ['![길별 위치 비율](fig_f1_lanes.png)', '', '![공격 시 좁게 선 장면: 노란 칸이 양쪽 측면 길, 파랑이 우리, 주황이 상대](fig_f7_width_photo.jpg)', '', '※ 사진은 공격 시 가장 좁게 선 순간 중 고른 극단 사례임. 평균 폭은 24m 수준임', '']
    L += ['□ 연구 근거',
          '  ○ 포지셔널 플레이는 경기장을 길(레인)로 나누어 점유함',
          '    - 출처: [Filipe Teles](https://hub-soccer.com/wp-content/uploads/2020/10/Positional-Play-by-Filipe-Teles.pdf), [FIGC 논문](https://www.figc.it/media/256232/thesis-occupying-spaces-and-positional-fluidity-ridotta.pdf)',
          '  ○ 한쪽에 몰아 끌어낸 뒤 반대편으로 돌려 고립시킴(사이드 체인지)',
          '    - 출처: [Analytics FC](https://analyticsfc.co.uk/blog/2021/05/24/developing-new-metrics-switching-the-play/)',
          '  ○ 측면 폭 유지는 상대 수비 줄을 벌려 중앙 공간을 확보하는 수단임', '']
    L += ['□ 공간 점유 보조 지표(참고)',
          '  ○ 마지막 3분의 1에서 4개 이상 길을 동시에 점유한 비율(%%): 지난 경기 %s·%s, 오늘 %s·%s' % (g(met[PT]['lanes4_share']), g(met[PH]['lanes4_share']), g(met[T]['lanes4_share']), g(met[H]['lanes4_share'])),
          '  ※ 오늘 경기는 추적 인원이 많아 높게 나올 수 있어 방향만 참고함', '']

    L.append('### 3. 유연한 전환' + NL)
    L += ['□ 국면별 형태 변화',
          '  ○ 공격 시 마지막 3분의 1 필드 선수 평균: 지난 경기 %s·%s명, 오늘 %s·%s명' % (g(met[PT]['final_third_mean'], 1), g(met[PH]['final_third_mean'], 1), g(met[T]['final_third_mean'], 1), g(met[H]['final_third_mean'], 1)),
          '  ○ 수비 시 우리 골대 25m 안 필드 선수 평균: 지난 경기 %s·%s명, 오늘 %s·%s명' % (g(met[PT]['own25_mean'], 1), g(met[PH]['own25_mean'], 1), g(met[T]['own25_mean'], 1), g(met[H]['own25_mean'], 1)),
          '    - 오늘은 수비 시 여러 명이 내려서고 공격 시 5명 이상이 올라가 국면별 형태 차이가 지난 경기보다 큼',
          '  ※ 선수 위치 순서로 나눈 평균이며 실제 포메이션과 다를 수 있음', '']
    L += ['![국면별 평균 대형](fig_f2_shape.png)', '']
    L += ['□ 전환 속도와 도착 대형',
          '  ○ 우리 진영으로 후퇴하는 데 걸린 시간 평균 %s초(전반)·%s초(후반)' % (g(met[T]['retreat_seconds']), g(met[H]['retreat_seconds'])),
          '  ○ 후퇴 도착 시 팀 길이 지난 경기 %s·%sm, 오늘 %s·%sm' % (g(met[PT]['retreat_length']), g(met[PH]['retreat_length']), g(met[T]['retreat_length']), g(met[H]['retreat_length'])),
          '  ○ 후퇴 도착 시 수비~중원 간격 지난 경기 %s·%sm, 오늘 %s·%sm' % (g(met[PT]['retreat_gap']), g(met[PH]['retreat_gap']), g(met[T]['retreat_gap']), g(met[H]['retreat_gap'])),
          '    - 수비로 전환한 뒤에도 팀이 길게 늘어져 압축이 늦음', '']
    L.append('< 표 2. 공격·수비 전환 횟수와 소요 시간 >' + NL)
    L += ['| 구분 | 후퇴 횟수 | 후퇴 소요(초) | 전진 횟수 | 전진 소요(초) | 후퇴 도착 시 팀 길이(m) |', '|---|---|---|---|---|---|']
    for n, _ in sets:
        m = met[n]
        L.append('| %s | %d | %s | %d | %s | %s |' % (n, m['retreats'], g(m['retreat_seconds']), m['advances'], g(m['advance_seconds']), g(m['retreat_length'])))
    L += ['', '자료: 영상 추적 위치 기록(팀 중심이 +5m 밖에서 -5m 안쪽으로, 또는 반대로 25초 안에 이동한 횟수)', '']
    L += ['![팀 중심의 위치와 전환(오늘 후반)](fig_f3_centre.png)', '']
    L += ['□ 연구 근거',
          '  ○ 공을 잃은 직후 5초가 가장 강한 압박 구간으로 통용됨',
          '    - 출처: [StatsBomb 분석](https://thexgfootballclub.substack.com/p/harnessing-statsbomb-data-to-evaluate-counter-pressing-ebc3ff06e818)',
          '  ○ 팀 전체 압축의 수축이 수비 전환에서 결정적이었음',
          '    - 출처: [KIT 박사논문](https://publikationen.bibliothek.kit.edu/1000173445/154142318)',
          '  ○ 공격 시 형태는 수비 시 형태와 달라질 수 있음',
          '    - 출처: [Shape Shifts](https://the-footballanalyst.com/?p=9557)',
          '  ※ 공 정보가 없어 5초 안 소유 회복 여부는 측정하지 못함', '']

    L.append('### 4. 공격과 수비 장면' + NL)
    L += ['□ 공격: 박스 진입은 많았으나 마무리로 이어지지 못함',
          '  ○ 박스 진입 공격 %d회, 그중 빠른 전개의 직접 공격 %d회' % (own_box, direct),
          '  ○ 아래 그림은 전반 박스 진입 장면(장면 5초 전~3초 뒤, 굵은 화살표는 빠르게 달린 선수, 노란 선은 표시한 공 경로)', '']
    L += ['![전반 공격 장면 이동](fig_f6_our_attack.png)', '']
    L += ['□ 수비: 상대 박스 진입 허용은 적었으나 수비~중원 간격이 벌어짐',
          '  ○ 상대 박스 진입 %d회' % their_box,
          '  ○ 수비~중원 간격 전반 %.0fm, 후반 %.0fm(목표 15m 안팎)' % (sh[T]['gap_dm'], sh[H]['gap_dm']), '']
    L += ['![수비 줄과 중원 줄 사이](fig_f4_gap.png)', '', '![후반 상대의 공략 장면 이동](fig_f5_their_attack.png)', '']

    L.append('### 5. 보완 과제 및 훈련 제안' + NL)
    L += ['□ 보완 과제', '  ○ 공격 시 측면 미드필더가 터치라인 가까이에서 폭을 유지함', '  ○ 수비 줄이 올라갈 때 중원이 같이 올라와 간격을 15m 안팎으로 유지함', '  ○ 공이 한쪽에 몰린 뒤 반대편으로 돌리는 사이드 체인지를 의도적으로 시도함', '  ○ 공을 잃은 직후 5초 동안 가까운 선수가 압박하고 나머지는 압축함', '']
    L += ['□ 훈련 제안(일반적인 코칭 방법이며 이번 분석의 결과가 아님)', '  ○ 터치라인 구역에 반드시 한 명이 서야 공격이 시작되는 6:6 미니 게임', '  ○ 콘으로 15m 간격의 두 줄을 만들고 수비·중원이 두 줄 안에서만 움직이는 8:8 미니 게임', '  ○ 한쪽 과부하 후 반대편 선수에게 전환하면 득점을 두 배로 인정하는 게임', '  ○ 공을 잃으면 5초 안에 되찾거나 지정 위치로 후퇴하는 전환 게임', '']

    L.append('### 6. 향후 계획' + NL)
    L.append('< 표 3. 과제별 훈련 및 점검 계획(제안) >' + NL)
    L += ['| 과제 | 훈련 | 담당 | 시기 |', '|---|---|---|---|', '| 측면 폭 유지 | 터치라인 구역 6:6 미니 게임 | 코치진 | 다음 경기 전 주간 훈련 |', '| 줄 간격 15m | 두 줄 8:8 미니 게임 | 코치진 | 다음 경기 전 주간 훈련 |', '| 사이드 체인지 | 과부하 후 전환 게임 | 코치진 | 다음 경기 전 주간 훈련 |', '| 전환 압축 | 5초 전환 게임 | 코치진 | 다음 경기 전 주간 훈련 |', '']
    L += ['자료: 본 보고서의 보완 과제(담당과 시기는 제안)', '']
    L += ['□ 점검 방법', '  ○ 다음 경기에서 공격 시 측면 비율, 수비~중원 간격, 전환 도착 대형을 같은 방법으로 비교함', '']

    L.append('### 7. 분석의 한계' + NL)
    L += ['※ 선수 위치만으로 분석하였고 공을 따라가지 못하여 슛·소유 회복·패스는 반영되지 않음',
          '※ 먼 쪽 선수 일부가 추적되지 않고 상대 인원이 적게 잡힘. 오늘 경기는 심판 등 비선수 인원이 섞여 팀 길이가 길게 나올 수 있어 두 경기 수치는 방향만 비교함',
          '※ 라인업 자리 이름은 예시 라인업(4-4-2)의 것을 사용함(교체 미반영)',
          '※ 횟수가 구간당 한 자릿수에서 수십 회로 적어 비율의 작은 차이는 의미가 없음', '']
    L = gaejosik(L)
    (out / 'report.md').write_text(NL.join(L), encoding='utf-8')
    print('markdown written', len(L), 'lines')

    kd = Path(args.kordoc_dir)

    cli = str((kd / 'node_modules' / '.bin' / 'kordoc.cmd').resolve())

    def run(*cmd):
        # run inside the output folder: kordoc finds the images (...) relative to the folder it runs in
        return subprocess.run([cli, *cmd], cwd=out, capture_output=True, text=True, encoding='utf-8', shell=False)
    gen = run('generate', str((out / 'report.md').resolve()), '-o', str((out / 'report.hwpx').resolve()), '--preset', '개조식', '--image-dir', str(out.resolve()))
    print('GENERATE', gen.returncode, (gen.stdout + gen.stderr)[-1800:])
    lint = run('lint', str((out / 'report.md').resolve()), '--munche', '--numbers', '--logic')
    (out / 'lint.txt').write_text(lint.stdout + lint.stderr, encoding='utf-8')
    print('LINT', lint.returncode, (lint.stdout + lint.stderr)[-2200:])
    rend = run('render', str((out / 'report.hwpx').resolve()), '--format', 'html', '-o', str((out / 'report_render.html').resolve()))
    run('render', str((out / 'report.hwpx').resolve()), '--format', 'png', '-d', str((out / 'pages').resolve()), '--max-width', '1100')
    print('RENDER html', rend.returncode, (rend.stdout + rend.stderr)[-300:])
    if (out / 'report_render.html').is_file():
        pdf = (out / 'report.pdf').resolve()
        if pdf.exists():
            pdf.unlink()
        subprocess.run([args.edge, '--headless=new', '--disable-gpu', '--user-data-dir=' + str(out.resolve() / 'edgeprof'), '--no-pdf-header-footer', '--print-to-pdf=%s' % pdf, (out / 'report_render.html').resolve().as_uri()], capture_output=True)
        print('PDF', pdf.is_file())


if __name__ == '__main__':
    main()
