"""Players' brief (HTML, one page per message): what the coach shows the team after the match, built from the same data as the detailed report.

python scripts/build_player_brief.py --cur-h1 positions_h1.jsonl --cur-h2 positions_h2.jsonl --cur-h2-end 1405 --clips-dir clips --shots-dir <store>/shots --ball-dir <store>/ball \
    --calibrations calibrations.json --out player_brief.html

Design (from the coaching-video guidance collected in wiki/detailed-report-research-1118.md): a session of 15 to 20 minutes with few clips, one message per card, the good things first,
a question for the players before the answer, a picture that marks the one thing to look at (telestration of the key point only), the clip next to it, and a link to the next training.
Numbers are kept to the few that carry the message; the detailed report keeps the rest. Training suggestions are general coaching practice, not results of this data.
"""
import argparse
import base64
import html
import json
import math
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_detailed_report as R  # noqa: E402

CSS = """
body{font-family:'Malgun Gothic',system-ui,sans-serif;margin:0;background:#0f1a14;color:#f1f7f2;line-height:1.6;font-size:18px}
main{max-width:1000px;margin:0 auto;padding:20px 16px 60px}
h1{font-size:2rem;margin:.2em 0}h2{font-size:1.5rem;margin:0 0 .3em}
.card{background:#16261c;border:1px solid #2f4a39;border-radius:14px;padding:16px 18px;margin:18px 0;page-break-inside:avoid}
.card.good{border-left:8px solid #4ade80}.card.fix{border-left:8px solid #fbbf24}.card.next{border-left:8px solid #6db8ff}
.big{font-size:1.35rem;font-weight:700;margin:.2em 0 .6em}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}@media(max-width:760px){.grid{grid-template-columns:1fr}}
.q{background:#1d3a2a;border-radius:10px;padding:10px 14px;margin:10px 0}.q b{color:#ffe14a}
.do{background:#14283a;border-radius:10px;padding:10px 14px;margin:10px 0}.do b{color:#6db8ff}
.drill{background:#2a2414;border-radius:10px;padding:10px 14px;margin:10px 0}.drill b{color:#fbbf24}
.tag{display:inline-block;border-radius:999px;padding:2px 12px;font-size:.85rem;margin-right:6px;background:#244f33}
.note{color:#9db8a4;font-size:.85rem}svg{background:#1b4a2a;border-radius:8px}video{width:100%;border-radius:8px}
.legend span{display:inline-block;margin-right:14px;font-size:.9rem}.sw{display:inline-block;width:12px;height:12px;border-radius:3px;margin-right:4px;vertical-align:-1px}
@media print{body{background:#fff;color:#111;font-size:15px}.card{background:#fff;border-color:#bbb}.q,.do,.drill{background:#f3f3f3}}
"""


def esc(s):
    return html.escape(str(s))


def uri(path, mime):
    return f'data:{mime};base64,' + base64.b64encode(Path(path).read_bytes()).decode('ascii')


def gap_svg(data, t, lines=('def', 'mid'), names=('수비 줄', '중원 줄')):
    """Our team at second t with the two lines that matter and the gap between them marked."""
    row = data[t]
    s = R.shape(row['ours'])
    parts = R.pitch_svg_start()
    parts.append(R.pitch_lines())
    for _, u, v in row['ours']:
        x, y = R.px(u, v)
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="6.5" fill="{R.BLUE}" opacity="0.95"/>')
    for _, u, v in row['theirs']:
        x, y = R.px(u, v)
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="6.5" fill="{R.RED}" opacity="0.9"/>')
    d, m = s[lines[0]], s[lines[1]]
    xd, y0 = R.px(d, -R.W / 2)
    xm, _ = R.px(m, -R.W / 2)
    parts.append(f'<line x1="{xd:.1f}" y1="{y0}" x2="{xd:.1f}" y2="{y0 + R.W * R.S}" stroke="#ffe14a" stroke-width="3" stroke-dasharray="7 5"/>')
    parts.append(f'<line x1="{xm:.1f}" y1="{y0}" x2="{xm:.1f}" y2="{y0 + R.W * R.S}" stroke="#ffe14a" stroke-width="3" stroke-dasharray="7 5"/>')
    ym = y0 + R.W * R.S / 2
    parts.append(f'<line x1="{xd + 3:.1f}" y1="{ym:.1f}" x2="{xm - 3:.1f}" y2="{ym:.1f}" stroke="#ffe14a" stroke-width="4"/>')
    parts.append(f'<polygon points="{xd + 3:.1f},{ym:.1f} {xd + 13:.1f},{ym - 6:.1f} {xd + 13:.1f},{ym + 6:.1f}" fill="#ffe14a"/>')
    parts.append(f'<polygon points="{xm - 3:.1f},{ym:.1f} {xm - 13:.1f},{ym - 6:.1f} {xm - 13:.1f},{ym + 6:.1f}" fill="#ffe14a"/>')
    parts.append(f'<text x="{(xd + xm) / 2:.1f}" y="{ym - 12:.1f}" fill="#ffe14a" font-size="22" font-weight="700" text-anchor="middle">{m - d:.0f}m 벌어짐</text>')
    parts.append(f'<text x="{xd:.1f}" y="{y0 + 16}" fill="#ffe14a" font-size="14" text-anchor="middle">{names[0]}</text><text x="{xm:.1f}" y="{y0 + 16}" fill="#ffe14a" font-size="14" text-anchor="middle">{names[1]}</text>')
    parts.append('</svg>')
    return ''.join(parts)


def pick_gap_second(data, lines=('def', 'mid'), target=22):
    """A second in which we defend (team centre in our half), enough players are seen and the gap between the defence and the midfield is clearly wide but not extreme."""
    best, best_t = None, None
    for t in sorted(data):
        row = data[t]
        s = R.shape(row['ours'])
        if not s or len(R.outfield(row['ours'])) < 8 or len(row['theirs']) < 5 or s['centre'] > 0:
            continue
        gap = s[lines[1]] - s[lines[0]]
        score = abs(gap - target)
        if best is None or score < best:
            best, best_t = score, t
    return best_t


def clip_html(folder, scene, poster=True):
    clip = Path(folder) / scene['clip']
    if not clip.is_file():
        return ''
    still = f' poster="{uri(Path(folder) / scene["still"], "image/jpeg")}"' if poster and (Path(folder) / scene['still']).is_file() else ''
    return f'<video controls preload="metadata" playsinline src="{uri(clip, "video/mp4")}"{still}></video>'


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--cur-h1', required=True)
    p.add_argument('--cur-h2', required=True)
    p.add_argument('--cur-h2-end', type=float)
    p.add_argument('--clips-dir', required=True)
    p.add_argument('--shots-dir')
    p.add_argument('--ball-dir')
    p.add_argument('--calibrations')
    p.add_argument('--first-ball-clip', type=int, default=55)
    p.add_argument('--no-video', action='store_true', help='print version: a photo of the scene instead of the video (for the PDF)')
    p.add_argument('--out', required=True)
    args = p.parse_args()
    d1, d2 = R.read(args.cur_h1), R.read(args.cur_h2, end=args.cur_h2_end)
    scenes = json.loads((Path(args.clips_dir) / 'scenes.json').read_text(encoding='utf-8'))
    byname = {s['name']: s for s in scenes}
    s_by = lambda half, kind, k=0: [s for s in scenes if s['half'] == half and s['kind'] == kind][k]

    own_box = len(R.waves(R.entries(d1, 'ours', 'box'))) + len(R.waves(R.entries(d2, 'ours', 'box')))
    their_box = len(R.waves(R.entries(d1, 'theirs', 'box'))) + len(R.waves(R.entries(d2, 'theirs', 'box')))
    direct = sum(1 for d in (d1, d2) for w in R.attack_waves(d, 'ours') if w['advance'] is not None and w['advance'] >= 15)
    sh1, sh2 = R.half_shape(d1), R.half_shape(d2)
    gap = statistics.mean([sh1['gap_dm'], sh2['gap_dm']])
    third2 = R.lane_counts(R.entries(d2, 'theirs', 'third'))
    lane2 = third2.index(max(third2)) if sum(third2) else None
    shots = {'ours': 0, 'ours_on': 0}
    if args.shots_dir and (Path(args.shots_dir) / 'tags').is_dir():
        cand = {c['id']: c for c in json.loads((Path(args.shots_dir) / 'candidates.json').read_text(encoding='utf-8'))['candidates']}
        for f in (Path(args.shots_dir) / 'tags').glob('*.json'):
            t = json.loads(f.read_text(encoding='utf-8'))
            c = cand.get(f.stem)
            if (c and c['match'] == 'cur' and t.get('side') == 'ours' and t['result'] != 'none') or (t.get('manual') and t.get('match') == 'cur' and t.get('side') == 'ours' and t['result'] != 'none'):
                shots['ours'] += 1
                shots['ours_on'] += t['result'] in ('saved', 'goal')
    ballpts = None
    if args.ball_dir and args.calibrations:
        def direction_of(path):
            return int(json.loads(Path(path).read_text(encoding='utf-8').splitlines()[0])['direction'])
        ballpts = R.ball_paths(args.ball_dir, args.calibrations, 'cam4', scenes, args.first_ball_clip, {'전반': direction_of(args.cur_h1), '후반': direction_of(args.cur_h2)})
    folder = args.clips_dir

    def media(sc):
        if not args.no_video:
            return clip_html(folder, sc)
        still = Path(folder) / sc['still']
        return f'<img alt="장면 사진" style="width:100%;border-radius:8px" src="{uri(still, "image/jpeg")}">' if still.is_file() else ''
    out = [f'<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>선수용 경기 리뷰</title><style>{CSS}</style></head><body><main>']
    out.append('<h1>선수용 경기 리뷰 (15분)</h1><p class="note">지난 경기. 장면 5개만 보고, 카드마다 먼저 질문을 던지고 답을 맞춰 봅니다. 그림의 화살표는 장면 5초 전부터 3초 뒤까지 선수가 움직인 길입니다(굵은 화살표는 빠르게 달린 선수). 파랑이 우리, 주황이 상대이고 우리는 오른쪽으로 공격합니다.</p>')
    out.append('<div class="legend note"><span><i class="sw" style="background:#6db8ff"></i>우리 선수</span><span><i class="sw" style="background:#ff8a6b"></i>상대 선수</span><span><i class="sw" style="background:#ffe14a"></i>오늘 볼 곳(노란 선, 노란 공 경로)</span></div>')
    out.append(f'<div class="card next"><h2>오늘 기억할 두 가지</h2><p class="big">1) 기회는 많이 만들었다. 2) 수비 줄과 중원 사이를 15m로 줄이자.</p>'
               f'<p>우리 선수가 상대 박스에 들어간 공격은 <b>{own_box}번</b>, 상대는 우리 박스에 <b>{their_box}번</b> 들어왔습니다. 득점이 없었던 이유는 두 가지로 봅니다: 줄 사이가 벌어져서 빠르게 올라가지 못했고(빠른 직접 공격 {direct}번), 박스 안에서 마무리까지 가지 못했습니다(표시된 우리 슛 {shots["ours"]}번).</p></div>')

    # card 1 good: chances
    sc = s_by('전반', 'our_attack', 0)
    svg, stats = R.path_svg(d1, sc['at'], ball=(ballpts or {}).get(sc['name']))
    out.append('<div class="card good"><span class="tag">잘한 점</span><h2>우리는 박스까지 가는 공격을 많이 만들었다</h2>'
               f'<div class="grid"><div>{media(sc)}</div><div>{svg}</div></div>'
               '<div class="q"><b>질문</b> 이 장면에서 공이 박스에 들어가기 전에 몇 명이 앞으로 달렸나요? 누가 먼저 움직였나요?</div>'
               f'<div class="do"><b>그대로 계속</b> 공이 있는 쪽 반대편 선수도 같이 박스로 들어가는 움직임을 유지합니다. 오늘 박스 진입 {own_box}번 가운데 대부분이 이런 모양이었습니다.</div></div>')

    # card 2 good: defence held
    sc = s_by('후반', 'their_attack', 1)
    svg, stats = R.path_svg(d2, sc['at'], ball=(ballpts or {}).get(sc['name']))
    out.append('<div class="card good"><span class="tag">잘한 점</span><h2>상대의 공격을 우리 박스 앞에서 많이 끊었다</h2>'
               f'<div class="grid"><div>{media(sc)}</div><div>{svg}</div></div>'
               f'<div class="q"><b>질문</b> 상대가 이 길로 들어올 때 우리 수비 줄은 어디까지 내려와 있었나요?</div>'
               f'<div class="do"><b>그대로 계속</b> 상대가 우리 진영에 들어오면 수비 줄을 먼저 내려서 박스 앞 공간을 닫습니다. 오늘 상대가 우리 박스에 들어온 것은 두 경기장 구간을 합쳐 {their_box}번뿐이었습니다.</div></div>')

    # card 3 fix: gap between lines
    t2 = pick_gap_second(d2)
    gsvg = gap_svg(d2, t2) if t2 else ''
    out.append('<div class="card fix"><span class="tag">고칠 점 1</span><h2>수비 줄과 중원 사이가 너무 벌어진다</h2>'
               f'<div class="grid"><div><p class="big">노란 선 두 줄 사이가 멀면, 그 사이로 상대가 공을 받습니다.</p><p>오늘 수비 줄과 중원 사이는 평균 <b>{gap:.0f}m</b>였습니다. 목표는 15m 안팎입니다.</p></div><div>{gsvg}</div></div>'
               '<div class="q"><b>질문</b> 그림에서 상대가 공을 받을 수 있는 자리는 어디일까요? 우리 중원은 몇 걸음 더 내려와야 할까요?</div>'
               '<div class="do"><b>다음엔 이렇게</b> 수비수가 올라가면 중원이 같이 올라오고, 중원이 내려오면 수비수는 그대로 버팁니다. 두 줄은 항상 한 덩어리로 움직입니다.</div>'
               '<div class="drill"><b>연습 제안</b> 콘으로 15m 간격의 두 줄을 만들고, 8대8 미니 경기에서 수비와 중원이 두 줄 안에서만 움직이게 합니다(줄을 벗어나면 프리킥을 줍니다).</div></div>')

    # card 4 fix: finishing / speed
    sc = s_by('후반', 'our_attack', 0)
    svg, stats = R.path_svg(d2, sc['at'], ball=(ballpts or {}).get(sc['name']))
    out.append('<div class="card fix"><span class="tag">고칠 점 2</span><h2>박스에는 들어갔는데 슛으로 끝내지 못한다</h2>'
               f'<div class="grid"><div>{media(sc)}</div><div>{svg}</div></div>'
               f'<p>오늘 박스까지 간 공격 {own_box}번 중 표시된 우리 슛은 {shots["ours"]}번(유효슈팅 {shots["ours_on"]}번)이었습니다. 빠르게 올라간 직접 공격은 {direct}번뿐입니다.</p>'
               '<div class="q"><b>질문</b> 이 장면에서 슛을 찰 수 있었던 순간은 언제였나요? 한 번 더 패스한 이유는 무엇이었나요?</div>'
               '<div class="do"><b>다음엔 이렇게</b> 박스 앞에서 공을 받으면 돌아보지 말고 첫 터치로 슛 각도를 만듭니다. 박스 안에 3명이 들어가 있으면 먼저 슛, 두 번째 선수는 튄 공을 노립니다.</div>'
               '<div class="drill"><b>연습 제안</b> 박스 앞에서 공을 받아 두 번 안에 슛하는 연습(수비 1명 붙임), 3명 침투 후 슛 5개 연속 시간제한 게임.</div></div>')

    # card 5 fix: opponent route
    lane_text = R.LANES[lane2] if lane2 is not None else '한쪽'
    sc = s_by('후반', 'their_attack', 0)
    svg, stats = R.path_svg(d2, sc['at'], ball=(ballpts or {}).get(sc['name']))
    out.append('<div class="card fix"><span class="tag">고칠 점 3</span><h2>상대는 같은 길로 계속 들어온다</h2>'
               f'<div class="grid"><div>{media(sc)}</div><div>{svg}</div></div>'
               f'<p>오늘 후반 상대가 우리 진영에 들어온 길은 <b>{lane_text}</b> 쪽이 가장 많았습니다({third2[lane2]}번/{sum(third2)}번).</p>' if lane2 is not None else '')
    out.append('<div class="q"><b>질문</b> 이 길을 가장 먼저 막아야 하는 선수는 누구인가요? 옆 선수는 어디에서 커버해야 하나요?</div>'
               '<div class="do"><b>다음엔 이렇게</b> 공이 그쪽으로 가면 가까운 수비수가 먼저 나가고, 옆 수비수는 안쪽으로 좁히고, 반대편 선수는 가운데로 들어와 세 명이 한 덩어리로 막습니다.</div>'
               '<div class="drill"><b>연습 제안</b> 한쪽 하프스페이스에서 공격 3 대 수비 3, 수비가 슬라이딩으로 간격을 맞추는 구역 수비 연습.</div></div>')

    # card 6 next
    out.append('<div class="card next"><h2>이번 주에 할 것</h2><div class="do"><b>연습 1</b> 두 줄 15m 간격 미니 경기(고칠 점 1)</div><div class="do"><b>연습 2</b> 박스 앞 두 번 터치 슛(고칠 점 2)</div><div class="do"><b>연습 3</b> 하프스페이스 3대3 구역 수비(고칠 점 3)</div>'
               '<p class="note">다음 경기 후에는 같은 방법으로 세 가지가 줄었는지 비교합니다.</p></div>')
    out.append('<p class="note">참고: 이 자료는 공을 보지 않고 선수 위치로 정리한 부분이 많고, 먼 쪽 선수가 일부 빠집니다. 숫자는 방향을 보는 용도입니다. 연습 제안은 일반적인 코칭 방법이고 이 자료에서 나온 결과가 아닙니다.</p></main></body></html>')
    Path(args.out).write_text(''.join(out), encoding='utf-8')
    print('wrote', args.out, 'size', Path(args.out).stat().st_size)


if __name__ == '__main__':
    main()
