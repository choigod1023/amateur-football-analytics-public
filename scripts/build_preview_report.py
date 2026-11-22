"""Match preview report (HTML, prints to PDF): a past-match analysis with mini maps, plans for the next match drawn on mini maps, one card per place of the line-up.

python scripts/build_preview_report.py --h1 <positions.jsonl> --h2 <positions.jsonl> [--alerts-h1 a.jsonl --alerts-h2 b.jsonl] --out preview.html

The line-up below (LINEUP) is a generic 4-4-2 EXAMPLE with slot names only, and every sentence of the page is an "example sentence" to be replaced by the coach's own text.
Sources, all of one match, one team, no names in the tracking:
  * positions.jsonl of scripts/run_live_feedback.py --positions (metres, one line per second, video seconds),
  * GOALS: goal times of the match in video seconds (empty in this example, so no goal drawings are made),
  * public professional data, not amateur (see wiki/validation-data-plan.md and wiki/set-pieces.md).
Measured drawings (heat maps, goal moments) come from those files; plan drawings are schematic and say so. Tracks have no names, so nothing here says which person did what.
"""
import argparse
import html
import json
import math
import statistics
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import preview_shapes as shapes  # noqa: E402

L, W = 89.0, 62.0
S = 5.0                                            # pixels per metre in the maps
GOALS = {'h1': [], 'h2': []}                  # goal times in video seconds of the match (example: none)
BOX_DEPTH, BOX_HALF = 16.5, 20.15
LINEUP = {'GK': ('골키퍼', 6, 0), 'LB': ('왼쪽 풀백', 24, -24), 'LCB': ('왼쪽 센터백', 20, -8), 'RCB': ('오른쪽 센터백', 20, 8), 'RB': ('오른쪽 풀백', 24, 24),
          'LM': ('왼쪽 미드필더', 48, -22), 'LCM': ('왼쪽 중앙 미드필더', 42, -8), 'RCM': ('오른쪽 중앙 미드필더', 42, 8), 'RM': ('오른쪽 미드필더', 48, 22), 'LS': ('왼쪽 공격수', 66, -7), 'RS': ('오른쪽 공격수', 66, 7)}
GROUP = {'GK': '#c9a400', 'LB': '#1d5fd6', 'LCB': '#1d5fd6', 'RCB': '#1d5fd6', 'RB': '#1d5fd6', 'LM': '#2f8f4e', 'LCM': '#2f8f4e', 'RCM': '#2f8f4e', 'RM': '#2f8f4e', 'LS': '#c23b32', 'RS': '#c23b32'}


def read(path):
    header, seconds = None, {}
    for line in Path(path).read_text(encoding='utf-8').splitlines():
        if line.strip():
            r = json.loads(line)
            if r['type'] == 'header':
                header = r
            else:
                seconds[int(r['time'])] = r
    return header, seconds


def pitch(inner, width=L, height=W, caption=''):
    """A pitch as SVG, team attacking to the right, the team's right hand at the bottom. <inner> is drawn in metre coordinates (x 0..89 from the own goal, y -31..31)."""
    w, h = width * S, height * S
    lines = (f'<rect x="0" y="0" width="{w}" height="{h}" fill="#5f8f5a" rx="6"/><g stroke="#fff" stroke-width="1.5" fill="none"><rect x="2" y="2" width="{w - 4}" height="{h - 4}"/>'
             f'<line x1="{w / 2}" y1="2" x2="{w / 2}" y2="{h - 2}"/><circle cx="{w / 2}" cy="{h / 2}" r="{9.15 * S}"/>'
             f'<rect x="2" y="{h / 2 - BOX_HALF * S}" width="{BOX_DEPTH * S}" height="{2 * BOX_HALF * S}"/><rect x="{w - 2 - BOX_DEPTH * S}" y="{h / 2 - BOX_HALF * S}" width="{BOX_DEPTH * S}" height="{2 * BOX_HALF * S}"/></g>')
    return f'<figure><svg viewBox="0 0 {w} {h}" role="img">{lines}<g transform="translate(0,{h / 2})">{inner}</g></svg><figcaption>{html.escape(caption)}</figcaption></figure>'


def px(x, y):
    return x * S, y * S


def dot(x, y, colour, label='', r=9, opacity=1.0):
    cx, cy = px(x, y)
    text = f'<text x="{cx}" y="{cy + 4}" text-anchor="middle" font-size="11" font-weight="700" fill="#fff">{html.escape(label)}</text>' if label else ''
    return f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{colour}" stroke="#fff" stroke-width="1.5" opacity="{opacity}"/>{text}'


def arrow(x1, y1, x2, y2, colour='#fff', dash=False):
    a, b = px(x1, y1), px(x2, y2)
    ang = math.atan2(b[1] - a[1], b[0] - a[0])
    head = ' '.join(f'{b[0] - 9 * math.cos(ang + d):.1f},{b[1] - 9 * math.sin(ang + d):.1f}' for d in (-0.45, 0.45))
    return (f'<line x1="{a[0]}" y1="{a[1]}" x2="{b[0]}" y2="{b[1]}" stroke="{colour}" stroke-width="2.5" {"stroke-dasharray=\"6 4\"" if dash else ""}/>'
            f'<polygon points="{b[0]},{b[1]} {head}" fill="{colour}"/>')


def to_team_frame(x, y, direction):
    """Metres of the file (x along the pitch, y toward the camera) -> from the own goal, the team's right hand positive, attacking right."""
    return x * direction + L / 2, y * direction


def shape_map(shape, title, colour='#1d5fd6'):
    """An 11-player shape (average of blocks) on a pitch: each place with its label, the goalkeeper first."""
    inner = ''
    gk = shape['gk']
    inner += dot(gk[0], gk[1], '#c9a400', 'GK', r=10)
    for label, (x, y) in shape['pos'].items():
        inner += dot(x, y, colour, label, r=10)
    return pitch(inner, caption=title)


def goal_map(seconds, direction, goal, caption):
    mine = shapes.eleven_at(seconds, goal - 3, 'team', direction)
    theirs = shapes.eleven_at(seconds, goal - 3, 'other', -direction)
    if not mine:
        return f'<figure><figcaption>{html.escape(caption)}: 이 장면은 영상에서 우리 팀 모양을 읽지 못해 그리지 못했습니다.</figcaption></figure>', None
    inner, box = '', 0
    if theirs:
        for x, y, _f in theirs[0]:
            inner += dot(x, y, '#c23b32', '', r=8)
    for x, y, _f in mine[0]:                    # all 11 are drawn the same way: the coach reads a team shape, not a detection list
        box += x > L - BOX_DEPTH and abs(y) < BOX_HALF
        inner += dot(x, y, '#1d5fd6', '', r=8)
    cap = f'{caption} 직전'
    return pitch(inner, caption=cap), box


def phase_blocks(all_blocks):
    """Blocks of both halves -> (attack blocks, defence blocks): the upper and lower third of the team depth."""
    depths = sorted(b['depth'] for b in all_blocks)
    if not depths:
        return [], []
    low, high = depths[len(depths) // 3], depths[2 * len(depths) // 3]
    return [b for b in all_blocks if b['depth'] >= high], [b for b in all_blocks if b['depth'] <= low]


def plan_maps():
    base = {k: (x, y) for k, (_n, x, y) in LINEUP.items()}
    Y = '#ffe28a'

    def players(positions):
        return ''.join(dot(x, y, GROUP[k], k, r=11) for k, (x, y) in positions.items())
    # 1 attack
    attack = players(base) + arrow(*base['LS'], 82, -6, Y) + arrow(*base['RS'], 60, 10, Y, True) + arrow(*base['RM'], 74, 15, Y) + arrow(*base['LM'], 66, -28, Y, True)
    # 2 defence
    d = {'GK': (6, 0), 'LB': (22, -22), 'LCB': (20, -8), 'RCB': (20, 8), 'RB': (22, 22), 'LM': (34, -22), 'LCM': (32, -8), 'RCM': (32, 8), 'RM': (34, 22), 'LS': (48, -7), 'RS': (48, 7)}
    defence = players(d) + arrow(*base['LM'], 34, -22, Y) + arrow(*base['RM'], 34, 22, Y) + arrow(*base['LS'], 48, -7, Y, True)
    # 3 transition
    t = dict(base)
    t.update({'RCM': (50, 6), 'LCM': (36, -8)})
    trans = players(t) + arrow(*base['RCM'], 50, 6, Y) + f'<text x="{34 * S}" y="{-14 * S}" font-size="12" fill="#fff" font-weight="700">LCM은 남아서 지킴</text>'
    # 4 set piece (attacking corner from the team's right side)
    s = {'GK': (6, 0), 'LB': (50, -16), 'RB': (50, 16), 'LCM': (60, -4), 'RCM': (60, 6), 'LCB': (80, -2), 'RCB': (80, 4), 'LS': (84, -6), 'RS': (80, -9), 'LM': (84, 10), 'RM': (85, 28)}
    setp = players(s) + arrow(85, 28, 83, 8, Y) + f'<text x="{6 * S}" y="{-27 * S}" font-size="12" fill="#fff" font-weight="700">예시 문장</text>'
    return [pitch(attack, caption='그림 4-1 공격 (예시 문장, 개략도)'), pitch(defence, caption='그림 4-2 수비 (예시 문장, 개략도)'),
            pitch(trans, caption='그림 4-3 공을 잃은 직후 (예시 문장, 개략도)'), pitch(setp, caption='그림 4-4 코너킥 배치 (예시 문장, 개략도)')]


CARDS = [(k, n, ['예시 문장: 이 자리의 역할을 코치가 적습니다.', '예시 문장: 공격할 때와 수비할 때의 움직임을 적습니다.'], '예시 문장: 근거를 적습니다.') for k, (n, _x, _y) in LINEUP.items()]

LINE_WORD = {'D': '수비 줄', 'M': '중원 줄', 'A': '공격형 줄', 'F': '공격 줄'}


def avg_pack(blocks):
    result = shapes.average_shape(blocks)
    if not result:
        return None
    text, share, n, pos, gk = result
    return {'text': text, 'share': share, 'n': n, 'pos': pos, 'gk': gk}


def line_depths(pack):
    xs = {}
    for lab, (x, _y) in pack['pos'].items():
        xs.setdefault(lab[0], []).append(x)
    return [(k, statistics.mean(v)) for k, v in sorted(xs.items(), key=lambda kv: statistics.mean(kv[1]))]


def gap_sentences(pack, phase):
    """Plain words about the distances between the lines of an average shape (numbers are not shown)."""
    lines = line_depths(pack)
    out = []
    for (a, xa), (b, xb) in zip(lines, lines[1:]):
        gap = xb - xa
        word = '많이 벌어져 있었습니다' if gap >= 22 else ('다소 벌어져 있었습니다' if gap >= 15 else '비교적 촘촘했습니다')
        out.append(f'{LINE_WORD[a]}과 {LINE_WORD[b]} 사이가 {word}.')
    if phase == 'attack' and lines:
        front = lines[-1]
        if len(lines) > 1 and front[1] - lines[-2][1] >= 18:
            out.append('공격 줄이 혼자 앞에 떨어져 있어서 받아 줄 선수가 가까이에 없었습니다.')
    if phase == 'defence' and lines and lines[0][1] < 30:
        out.append('수비 줄이 골문 가까이에 내려앉아 있었습니다.')
    return out


def page(h1, h2):
    head = [(h1, 'h1'), (h2, 'h2')]
    all_blocks = []
    for (header, seconds), key in head:
        all_blocks += shapes.blocks_of(seconds, 'team', header['direction'])
    attack, defence = phase_blocks(all_blocks)
    maps, notes = '', ''
    for number, blocks, label, phase in ((1, attack, '상대 진영에서 공격하던 때의 우리 팀 모양', 'attack'), (2, defence, '우리 진영에서 수비하던 때의 우리 팀 모양', 'defence')):
        pack = avg_pack(blocks)
        if not pack:
            continue
        maps += '<div>' + shape_map(pack, f'그림 3-{number} {label} (11명 평균)') + '</div>'
        notes += f'<div class="box"><b>{label}</b><ul>' + ''.join(f'<li>{t}</li>' for t in gap_sentences(pack, phase)) + '</ul></div>'
    goals = ''
    for (header, seconds), key in head:
        for g in GOALS[key]:
            figure, _box = goal_map(seconds, header['direction'], g, f'그림 골 {g // 60}:{g % 60:02d}')
            goals += figure
    plan = ''.join(f'<div>{m}</div>' for m in plan_maps())
    lineup_inner = ''.join(dot(x, y, GROUP[k], k, r=12) + f'<text x="{x * S}" y="{y * S + 25}" text-anchor="middle" font-size="12" font-weight="700" fill="#fff">{n}</text>' for k, (n, x, y) in LINEUP.items())
    cards = ''.join(f'<article class="card"><h3>{k} {n}</h3><ul>{"".join(f"<li>{html.escape(t)}</li>" for t in tasks)}</ul><p class="evidence">{html.escape(ev)}</p></article>' for k, n, tasks, ev in CARDS)
    return (TEMPLATE.replace('@@lineup@@', pitch(lineup_inner, caption='그림 2 예시 라인업 4-4-2 (팀이 오른쪽으로 공격, 화면 아래쪽이 팀의 오른쪽)')).replace('@@maps@@', maps)
            .replace('@@notes@@', notes).replace('@@goals@@', goals).replace('@@plan@@', plan).replace('@@cards@@', cards))


TEMPLATE = """<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>경기 프리뷰 (예시)</title>
<style>
 body { margin:0; background:#fff; color:#1b2430; font-family:"Malgun Gothic","Apple SD Gothic Neo",sans-serif; line-height:1.65; }
 main { max-width:900px; margin:0 auto; padding:24px 18px 48px; }
 h1 { font-size:28px; margin:0 0 4px; } h2 { font-size:20px; margin:30px 0 8px; border-bottom:2px solid #1d5fd6; padding-bottom:4px; } h3 { font-size:15px; margin:10px 0 4px; }
 .sub { color:#5b6675; } .grid { display:grid; grid-template-columns:1fr 1fr; gap:14px; } @media (max-width:700px) { .grid { grid-template-columns:1fr; } }
 table { width:100%; border-collapse:collapse; font-size:14px; margin:8px 0; } th,td { text-align:left; padding:7px 8px; border-bottom:1px solid #dfe3e9; vertical-align:top; } th { color:#5b6675; }
 figure { margin:8px 0; } svg { width:100%; height:auto; display:block; } figcaption { font-size:12.5px; color:#5b6675; margin-top:3px; }
 .card { border:1px solid #dfe3e9; border-radius:10px; padding:8px 12px; break-inside:avoid; } .evidence { font-size:12.5px; color:#5b6675; margin:4px 0 0; }
 .box { background:#f4f7fc; border:1px solid #cfd9ee; border-radius:10px; padding:10px 14px; margin:10px 0; break-inside:avoid; }
 ul { margin:4px 0 0; padding-left:20px; } li { margin:3px 0; }
 @media print { h2 { break-after:avoid; } figure { break-inside:avoid; } }
</style></head><body><main>
<h1>경기 프리뷰 (예시)</h1>
<div class="sub">예시 문장 · 날짜 · 지난 경기 영상 분석과 공개 프로 경기 자료에 근거한 제안</div>

<h2>1. 핵심 요약</h2>
<div class="box"><ul>
 <li>예시 문장: 이번 경기의 시작 모양(예: 4-4-2)과 수비할 때의 약속을 적습니다.</li>
 <li>예시 문장: 지난 경기에서 반복된 문제를 적습니다.</li>
 <li>예시 문장: 이번 경기 과제 세 가지를 적습니다.</li>
</ul></div>

<h2>2. 라인업</h2>
@@lineup@@

<h2>3. 지난 경기에서 본 우리 팀</h2>
<p class="sub">지난 경기 영상에서 우리 팀의 평균적인 모양을 11명으로 그렸습니다. 선수 개인이 아니라 팀의 모양이고, D는 수비 줄, M은 중원 줄, A는 공격형 줄, F는 공격 줄이며 왼쪽에서 오른쪽 순서입니다.</p>
<div class="grid">@@maps@@</div>
@@notes@@
<h3>골 장면 직전의 모습</h3>
<p class="sub">파랑이 우리 팀 11명, 빨강이 상대 11명입니다. 골이 나기 3초 전의 위치입니다(GOALS에 골 시각을 넣었을 때만 그려집니다).</p>
<div class="grid">@@goals@@</div>

<h2>4. 이번 경기 움직임 계획</h2>
<p class="sub">아래 그림은 제안을 그린 것입니다. 노란 화살표가 움직임이고, 점선은 선택입니다.</p>
<div class="grid">@@plan@@</div>
<table><tr><th>상황</th><th>제안</th><th>근거</th></tr>
<tr><td>예시 문장</td><td>예시 문장</td><td>예시 문장</td></tr></table>

<h2>5. 포지션별 카드</h2>
<div class="grid">@@cards@@</div>

<h2>6. 경기 중 체크리스트</h2>
<ul><li>예시 문장: 경기 중 확인할 것을 적습니다.</li></ul>

<h2>7. 참고</h2>
<p class="sub">예시 문장. 이 문서의 움직임은 제안이며, 우리 경기에서 확인된 규칙이 아닙니다.</p>
</main></body></html>
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--h1', required=True)
    parser.add_argument('--h2', required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    Path(args.out).write_text(page(read(args.h1), read(args.h2)), encoding='utf-8')
    print('written', args.out)


if __name__ == '__main__':
    main()
