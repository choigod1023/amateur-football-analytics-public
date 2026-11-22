"""One card per SLOT of the example line-up (generic 4-4-2 of build_preview_report.LINEUP): where the slot was supposed to stand and where it stood on average when our team attacked and when it defended.

python scripts/build_slot_cards.py --cur-h1 positions_h1.jsonl --cur-h2 positions_h2.jsonl --cur-h2-end 1405 --out cards.html

The tracks have no names. A player is a SLOT: at every second the outfield players are ordered by distance from our goal, the four deepest are the defenders (left to right: LB, LCB, RCB, RB), the next four are the
midfielders (left to right: LM, LCM, RCM, RM) and the two most advanced are the forwards (left to right LS and RS). So a card tells where the SLOT stood, not what a named
player did; if players swapped places or substitutes came on, the card says nothing true about the name. The goalkeeper is left out (the goalkeepers are not tracked reliably).
Our team's view: our goal on the left, we attack to the right; "left" and "right" are the team's own.
"""
import argparse
import html
import importlib.util
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_detailed_report as R  # noqa: E402
import build_player_brief as P  # noqa: E402

SLOTS = ['LB', 'LCB', 'RCB', 'RB', 'LM', 'LCM', 'RCM', 'RM', 'LS', 'RS']
ROLE = {'LB': '왼쪽 풀백', 'LCB': '왼쪽 센터백', 'RCB': '오른쪽 센터백', 'RB': '오른쪽 풀백', 'LM': '왼쪽 미드필더', 'LCM': '왼쪽 중앙 미드필더', 'RCM': '오른쪽 중앙 미드필더', 'RM': '오른쪽 미드필더',
        'LS': '왼쪽 공격수', 'RS': '오른쪽 공격수'}
CUE = {k: '예시 문장: 이 자리의 역할을 코치가 적습니다.' for k in SLOTS}


def planned():
    spec = importlib.util.spec_from_file_location('preview', str(Path(__file__).resolve().parent / 'build_preview_report.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return {k: (v[0], v[1] - R.L / 2, v[2]) for k, v in mod.LINEUP.items() if k in SLOTS}


def slots_of(row):
    pts = sorted(R.outfield(row['ours']), key=lambda q: q[1])
    if len(pts) < 10:
        return None
    d, m, f = pts[:4], pts[4:8], pts[-2:]          # the four deepest, the next four and the two most advanced (people beyond ten, such as officials, fall in between and are ignored)
    out = {}
    for names, grp in ((('LB', 'LCB', 'RCB', 'RB'), d), (('LM', 'LCM', 'RCM', 'RM'), m), (('LS', 'RS'), f)):
        for name, q in zip(names, sorted(grp, key=lambda q: q[2])):
            out[name] = q
    return out


def stats(datas):
    acc = {ph: {s: [] for s in SLOTS} for ph in ('attack', 'defend')}
    for d in datas:
        for t, row in d.items():
            sl = slots_of(row)
            if not sl:
                continue
            pts = R.outfield(row['ours'])
            centre = statistics.mean(q[1] for q in pts)
            ph = 'attack' if centre > 0 else 'defend'
            for s in SLOTS:
                acc[ph][s].append((sl[s][1], sl[s][2]))
    res = {}
    for ph in acc:
        res[ph] = {}
        for s in SLOTS:
            v = acc[ph][s]
            res[ph][s] = (statistics.mean(a for a, _ in v), statistics.mean(b for _, b in v), len(v)) if len(v) >= 30 else None
    return res


def card_svg(plan, att, dfn):
    parts = R.pitch_svg_start()
    parts.append(R.pitch_lines())
    px = R.px
    x, y = px(plan[1], plan[2])
    parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="10" fill="none" stroke="#fff" stroke-width="3" stroke-dasharray="4 3"/>')
    for pos, colour in ((dfn, '#ff8a6b'), (att, '#6db8ff')):
        if pos:
            xa, ya = px(pos[0], pos[1])
            parts.append(f'<circle cx="{xa:.1f}" cy="{ya:.1f}" r="8" fill="{colour}" opacity="0.95"/>')
    if att:
        parts.append(R.arrow(plan[1], plan[2], att[0], att[1], '#6db8ff', 2.4, 0.9))
    parts.append('</svg>')
    return ''.join(parts)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--cur-h1', required=True)
    p.add_argument('--cur-h2', required=True)
    p.add_argument('--cur-h2-end', type=float)
    p.add_argument('--out', required=True)
    args = p.parse_args()
    d1, d2 = R.read(args.cur_h1), R.read(args.cur_h2, end=args.cur_h2_end)
    plan = planned()
    st = stats([d1, d2])
    css = P.CSS + '.cards{display:grid;grid-template-columns:1fr 1fr;gap:14px}@media(max-width:760px){.cards{grid-template-columns:1fr}}.name{font-size:1.4rem;font-weight:700}.role{color:#9db8a4;margin-bottom:.4em}'
    out = [f'<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>선수별 카드</title><style>{css}</style></head><body><main>',
           '<h1>선수별 카드 (라인업 자리 기준)</h1><p class="note">그림에서 흰 점선 동그라미가 계획한 자리(예시 라인업), 파랑이 우리가 공격할 때(팀 중심이 상대 진영) 그 자리 선수가 평균으로 선 곳, 주황이 수비할 때 선 곳입니다. 파랑 화살표는 계획한 자리에서 공격 때의 자리로 이동한 방향입니다. 우리는 오른쪽으로 공격합니다.</p>',
           '<div class="card fix"><b>꼭 읽어 주세요</b><p>선수 이름은 예시 라인업(4-4-2)의 자리 이름을 붙인 것입니다. 영상 추적에는 이름이 없어서, 매 순간 우리 필드 선수를 골대에서 가까운 순서로 줄 세우고 가장 깊은 4명을 수비, 다음 4명을 중원, 가장 앞선 2명을 공격으로 나누어 "그 자리"의 평균을 냈습니다. 그래서 카드는 이름 붙은 선수가 실제로 한 일이 아니라 <b>그 자리가 어디에 서 있었는지</b>를 보여 줍니다. 선수들이 자리를 바꾸었거나 교체가 있었거나 실제 라인업이 달랐다면 이름은 맞지 않습니다. 골키퍼는 안정적으로 잡히지 않아 뺐습니다.</p></div>']
    out.append('<div class="cards">')
    for s in SLOTS:
        name, pu, pv = plan[s]
        a, dfn = st['attack'][s], st['defend'][s]
        lines = []
        if a:
            du, dv = a[0] - pu, abs(a[1]) - abs(pv)
            lines.append(f'공격할 때 계획한 자리보다 {abs(du):.0f}m {"앞" if du > 0 else "뒤"}에 섰습니다.')
            if s in ('LB', 'RB', 'LM', 'RM', 'LS', 'RS'):
                lines.append(f'옆으로는 중앙에서 평균 {abs(a[1]):.0f}m(계획 {abs(pv):.0f}m)에 서서 계획보다 {abs(dv):.0f}m {"바깥" if dv > 0 else "안쪽"}이었습니다.')
            else:
                lines.append(f'옆 위치는 중앙에서 평균 {abs(a[1]):.0f}m였습니다(계획 {abs(pv):.0f}m).')
        if dfn:
            lines.append(f'수비할 때는 계획한 자리보다 {abs(dfn[0] - pu):.0f}m {"앞" if dfn[0] > pu else "뒤"}에 섰습니다.')
        out.append(f'<div class="card"><div class="name">{html.escape(name)}</div><div class="role">{ROLE[s]} ({s})</div><div class="grid"><div>{card_svg((name, pu, pv), (a[0], a[1]) if a else None, (dfn[0], dfn[1]) if dfn else None)}</div>'
                   f'<div>{"".join(f"<p>{html.escape(x)}</p>" for x in lines)}<div class="do"><b>역할</b> {CUE[s]}</div></div></div></div>')
    out.append('</div><p class="note">참고: 선수 위치 순서로 나눈 자리의 평균이라 오차가 있습니다. 먼 쪽 선수가 일부 빠지고 터치라인에 붙은 선수가 일부 빠졌을 수 있습니다. 역할 설명은 일반적인 코칭 설명이며 이 자료의 결과가 아닙니다.</p></main></body></html>')
    Path(args.out).write_text(''.join(out), encoding='utf-8')
    for s in SLOTS:
        a = st['attack'][s]
        print(s, plan[s][0], 'plan', (round(plan[s][1]), plan[s][2]), 'attack', (round(a[0]), round(a[1])) if a else None, 'n', a[2] if a else 0)


if __name__ == '__main__':
    main()
