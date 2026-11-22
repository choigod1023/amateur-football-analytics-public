"""Players' brief by position group (HTML; --no-video gives the print version for the PDF): defenders, midfielders, forwards, goalkeeper.

python scripts/build_position_brief.py --cur-h1 positions_h1.jsonl --cur-h2 positions_h2.jsonl --cur-h2-end 1405 --clips-dir clips --shots-dir <store>/shots --ball-dir <store>/ball \
    --calibrations calibrations.json [--no-video] --out brief.html

The tracks have no names, so a position group is the group by rank at the moment of the scene: the three deepest outfield players are the defenders (example grouping 3-4-3 by rank; edit GROUPS for another formation),
the next four the midfielders and the three most advanced the forwards. The group is drawn with strong arrows and the rest of the players faded, so that every
player sees his own group's movement. One message per card, the good things first, a question before the answer, a drill at the end (general coaching practice, not a result of the data).
"""
import argparse
import html
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_detailed_report as R  # noqa: E402
import build_player_brief as P  # noqa: E402

GROUPS = {'def': ('수비수', '가장 뒤 세 명', (0, 3)), 'mid': ('미드필더', '그다음 네 명', (3, 7)),
          'att': ('공격수', '가장 앞 세 명', (7, 10))}


def group_ids(data, t, which):
    pts = sorted(R.outfield(data[int(round(t))]['ours']), key=lambda p: p[1])
    lo, hi = GROUPS[which][2]
    if which == 'att':
        return {p[0] for p in pts[-3:]}
    return {p[0] for p in pts[lo:hi]}


def attack_lane_share(datas):
    """Share of our outfield players (in the opponent's half, while the team centre is there) per lane, and the mean team width at those moments."""
    lanes, widths = [0] * 5, []
    for d in datas:
        for t, row in d.items():
            pts = R.outfield(row['ours'])
            if len(pts) < 7:
                continue
            if statistics.mean(q[1] for q in pts) <= 0:
                continue
            att = [q for q in pts if q[1] > 0]
            if len(att) < 4:
                continue
            ys = sorted(q[2] for q in pts)
            k = len(ys)
            widths.append(ys[int(0.9 * (k - 1))] - ys[int(0.1 * (k - 1))])
            for q in att:
                lanes[R.lane(q[2])] += 1
    total = sum(lanes) or 1
    return [100.0 * x / total for x in lanes], (statistics.mean(widths) if widths else None)


def lane_share_svg(shares, width_m):
    parts = R.pitch_svg_start()
    parts.append(R.pitch_lines())
    edges = [-R.W / 2, *R.LANE_EDGES, R.W / 2]
    for k in range(5):
        x0, y0 = R.px(0, edges[k])
        x1, y1 = R.px(R.L / 2, edges[k + 1])
        wide = k in (0, 4)
        parts.append(f'<rect x="{x0:.1f}" y="{y0:.1f}" width="{x1 - x0:.1f}" height="{y1 - y0:.1f}" fill="{"#ffe14a" if wide else "#6db8ff"}" opacity="{0.12 + 0.012 * shares[k]:.2f}"/>')
        parts.append(f'<text x="{(x0 + x1) / 2:.1f}" y="{(y0 + y1) / 2 + 8:.1f}" fill="#fff" font-size="26" font-weight="700" text-anchor="middle">{shares[k]:.0f}%</text>')
        parts.append(f'<text x="{x0 + 8:.1f}" y="{y0 + 16:.1f}" fill="#fff" font-size="12" opacity="0.85">{R.LANES[k]}</text>')
    parts.append('</svg>')
    return ''.join(parts)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--cur-h1', required=True)
    p.add_argument('--cur-h2', required=True)
    p.add_argument('--cur-h2-end', type=float)
    p.add_argument('--clips-dir', required=True)
    p.add_argument('--shots-dir')
    p.add_argument('--ball-dir')
    p.add_argument('--calibrations')
    p.add_argument('--width-dir', help='photos of narrow attacks of scripts/width_photos.py')
    p.add_argument('--prev-h1')
    p.add_argument('--prev-h2')
    p.add_argument('--first-ball-clip', type=int, default=55)
    p.add_argument('--no-video', action='store_true')
    p.add_argument('--out', required=True)
    args = p.parse_args()
    d1, d2 = R.read(args.cur_h1), R.read(args.cur_h2, end=args.cur_h2_end)
    scenes = json.loads((Path(args.clips_dir) / 'scenes.json').read_text(encoding='utf-8'))
    s_by = lambda half, kind, k=0: [s for s in scenes if s['half'] == half and s['kind'] == kind][k]
    folder = args.clips_dir
    sh1, sh2 = R.half_shape(d1), R.half_shape(d2)
    own_box = len(R.waves(R.entries(d1, 'ours', 'box'))) + len(R.waves(R.entries(d2, 'ours', 'box')))
    their_box = len(R.waves(R.entries(d1, 'theirs', 'box'))) + len(R.waves(R.entries(d2, 'theirs', 'box')))
    direct = sum(1 for d in (d1, d2) for w in R.attack_waves(d, 'ours') if w['advance'] is not None and w['advance'] >= 15)
    lanes_o = [a + b for a, b in zip(R.lane_counts(R.entries(d1, 'ours', 'third')), R.lane_counts(R.entries(d2, 'ours', 'third')))]      # the final third is wide enough for the wings; the box (40 m) is not
    lanes_t2 = R.lane_counts(R.entries(d2, 'theirs', 'third'))
    top_o = lanes_o.index(max(lanes_o)) if sum(lanes_o) else None
    top_t = lanes_t2.index(max(lanes_t2)) if sum(lanes_t2) else None
    shots = {'ours': 0, 'ours_on': 0, 'saved_by_us': 0}
    if args.shots_dir and (Path(args.shots_dir) / 'tags').is_dir():
        cand = {c['id']: c for c in json.loads((Path(args.shots_dir) / 'candidates.json').read_text(encoding='utf-8'))['candidates']}
        for f in (Path(args.shots_dir) / 'tags').glob('*.json'):
            t = json.loads(f.read_text(encoding='utf-8'))
            c = cand.get(f.stem)
            match = c['match'] if c else t.get('match')
            if match == 'cur' and t.get('result') not in (None, 'none'):
                if t.get('side') == 'ours':
                    shots['ours'] += 1
                    shots['ours_on'] += t['result'] in ('saved', 'goal')
                elif t['result'] == 'saved':
                    shots['saved_by_us'] += 1
    ballpts = None
    if args.ball_dir and args.calibrations:
        def direction_of(path):
            return int(json.loads(Path(path).read_text(encoding='utf-8').splitlines()[0])['direction'])
        ballpts = R.ball_paths(args.ball_dir, args.calibrations, 'cam4', scenes, args.first_ball_clip, {'전반': direction_of(args.cur_h1), '후반': direction_of(args.cur_h2)})

    def media(sc):
        if not args.no_video:
            return P.clip_html(folder, sc)
        still = Path(folder) / sc['still']
        return f'<img alt="장면 사진" style="width:100%;border-radius:8px" src="{P.uri(still, "image/jpeg")}">' if still.is_file() else ''

    def scene_card(kind, tag, title, sc, data, group, body, question, nxt, drill, answer):
        ids = group_ids(data, sc['at'], group)
        svg, _ = R.path_svg(data, sc['at'], ball=(ballpts or {}).get(sc['name']), highlight=ids)
        answers.append((title, answer))
        return (f'<div class="card {kind}"><span class="tag">{tag}</span><h2>{html.escape(title)}</h2><div class="grid"><div>{media(sc)}</div><div>{svg}</div></div>{body}'
                f'<div class="q"><b>질문</b> {question}</div><div class="do"><b>{"그대로 계속" if kind == "good" else "다음엔 이렇게"}</b> {nxt}</div>' + (f'<div class="drill"><b>연습 제안</b> {drill}</div>' if drill else '') + '</div>')

    def gap_card(kind, tag, title, data, lines, names, second, body, question, nxt, drill, answer):
        answers.append((title, answer))
        return (f'<div class="card {kind}"><span class="tag">{tag}</span><h2>{html.escape(title)}</h2><div class="grid"><div>{body}</div><div>{P.gap_svg(data, second, lines, names)}</div></div>'
                f'<div class="q"><b>질문</b> {question}</div><div class="do"><b>{"그대로 계속" if kind == "good" else "다음엔 이렇게"}</b> {nxt}</div>' + (f'<div class="drill"><b>연습 제안</b> {drill}</div>' if drill else '') + '</div>')

    answers = []
    css = P.CSS + ".pos{font-size:1.8rem;margin:1.6em 0 .2em;color:#bfe3c8}.who{color:#9db8a4;margin:0 0 .6em}.ans li{margin:.3em 0}"
    out = [f'<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>포지션별 선수용 리뷰</title><style>{css}</style></head><body><main>']
    out.append('<h1>포지션별 선수용 리뷰</h1><p class="note">지난 경기. 자기 포지션 쪽만 먼저 보고, 카드마다 질문에 먼저 답해 본 뒤 맞춰 봅니다. 그림은 우리가 오른쪽으로 공격하는 모양이고, 화살표는 장면 5초 전부터 3초 뒤까지 움직인 길입니다. 진하고 굵은 화살표가 그 포지션 선수들, 흐린 것은 나머지입니다(굵을수록 빨리 달림).</p>')
    out.append('<div class="legend note"><span><i class="sw" style="background:#6db8ff"></i>우리 선수</span><span><i class="sw" style="background:#ff8a6b"></i>상대 선수</span><span><i class="sw" style="background:#ffe14a"></i>노란 선: 공 경로 또는 오늘 볼 곳</span></div>')
    out.append(f'<div class="card next"><h2>오늘 팀이 기억할 두 가지</h2><p class="big">1) 기회는 많이 만들었다. 2) 세 줄(수비, 중원, 공격) 사이를 15m 안팎으로 줄이자.</p>'
               f'<p>우리 박스 진입 공격 {own_box}번, 상대 박스 진입 {their_box}번. 수비~중원 간격 평균 {statistics.mean([sh1["gap_dm"], sh2["gap_dm"]]):.0f}m, 중원~공격 간격 전반 {sh1["gap_ma"]:.0f}m에서 후반 {sh2["gap_ma"]:.0f}m로 좁아졌습니다.</p></div>')

    # ---- defenders
    out.append(f'<h2 class="pos">수비수 편</h2><p class="who">{GROUPS["def"][1]}</p>')
    sc = s_by('후반', 'their_attack', 1)
    out.append(scene_card('good', '잘한 점', '수비 줄을 높게 유지해서 상대 공격을 일찍 끊었다', sc, d2, 'def',
                          f'<p>수비 줄은 우리 골대에서 전반 평균 {sh1["def"]:.0f}m, 후반 {sh2["def"]:.0f}m로 후반에 더 높았습니다. 상대가 우리 박스에 들어온 공격은 모두 {their_box}번이었습니다.</p>',
                          '그림에서 굵은 파랑 세 명은 상대가 들어올 때 서로 몇 걸음 간격으로 서 있었나요? 누가 먼저 압박에 나갔나요?',
                          '공이 상대 진영에 있을 때는 수비 줄을 중앙선 가까이 올려 상대가 우리 뒤 공간을 쓰지 못하게 합니다.', '',
                          '세 명이 한 줄로 나란히 올라가고 가장 가까운 선수가 먼저 나가며, 나머지 둘이 안쪽으로 좁힙니다.'))
    t2 = P.pick_gap_second(d2)
    out.append(gap_card('fix', '고칠 점', '수비 줄이 올라갈 때 중원이 같이 올라오지 못한다', d2, ('def', 'mid'), ('수비 줄', '중원 줄'), t2,
                        f'<p class="big">노란 선 두 줄 사이가 멀면, 상대가 그 사이에서 공을 받습니다.</p><p>수비 줄과 중원 사이가 전반 {sh1["gap_dm"]:.0f}m, 후반 {sh2["gap_dm"]:.0f}m였습니다. 목표는 15m 안팎입니다.</p>',
                        '그림에서 상대가 공을 받을 수 있는 자리는 어디인가요? 수비수는 올라갈지 버틸지 어떻게 정해야 할까요?',
                        '수비 줄이 올라갈 때는 먼저 중원에게 "올라와"라고 소리쳐 신호를 줍니다. 중원이 못 올라오면 수비는 올라가지 않고 버팁니다.',
                        '콘으로 15m 간격의 두 줄을 만들고 8대8 미니 경기에서 수비와 중원이 두 줄 안에서만 움직입니다(벗어나면 프리킥).',
                        '수비가 올릴 때 중원에게 신호를 주고, 간격이 15m를 넘으면 수비가 올리지 않는다.'))
    if top_t is not None:
        sc = s_by('후반', 'their_attack', 0)
        out.append(scene_card('fix', '고칠 점', f'상대는 {R.LANES[top_t]}으로 계속 들어온다' if R.by_lane(top_t).endswith('으로') else f'상대는 {R.by_lane(top_t)} 계속 들어온다', sc, d2, 'def',
                              f'<p>오늘 후반 상대가 우리 진영에 들어온 길은 {R.LANES[top_t]}이 가장 많았습니다({lanes_t2[top_t]}번/{sum(lanes_t2)}번).</p>',
                              '이 길을 가장 먼저 막아야 하는 선수는 누구인가요? 옆 선수는 어디에서 커버해야 하나요?',
                              '공이 그쪽으로 가면 가까운 수비수가 나가고, 옆 수비수는 안쪽으로 좁히고, 반대편 수비수는 가운데로 들어와 세 명이 한 덩어리로 막습니다.',
                              f'{R.LANES[top_t]} 3대3 구역 수비 연습(수비가 슬라이딩으로 간격을 맞춤).',
                              f'상대가 {R.LANES[top_t]}으로 오면 가까운 수비수가 나가고 나머지 둘이 좁힌다.' if R.by_lane(top_t).endswith('으로') else f'상대가 {R.LANES[top_t]}로 오면 가까운 수비수가 나가고 나머지 둘이 좁힌다.'))

    # ---- midfielders
    out.append(f'<h2 class="pos">미드필더 편</h2><p class="who">{GROUPS["mid"][1]}</p>')
    t3 = P.pick_gap_second(d2, ('mid', 'att'), sh2['gap_ma'])
    out.append(gap_card('good', '잘한 점', '후반에는 중원과 공격 사이가 좁아졌다', d2, ('mid', 'att'), ('중원 줄', '공격 줄'), t3,
                        f'<p class="big">전반 {sh1["gap_ma"]:.0f}m였던 중원~공격 간격이 후반에는 {sh2["gap_ma"]:.0f}m로 줄었습니다.</p><p>두 줄이 가까워지면 공격수가 공을 받을 때 도와줄 선수가 가까이에 있습니다.</p>',
                        '그림에서 공격수가 공을 받으면 가장 먼저 도와줄 선수는 누구인가요? 몇 걸음이면 닿나요?',
                        '후반처럼 중원이 공격수 뒤 15m 안에 서서 짧은 패스로 받아 줍니다.', '', '공격수 뒤 15m 안에 중원 한 명이 항상 서서 짧은 패스를 받아 준다.'))
    rows1 = R.bin_rows(d1)
    early = statistics.mean([r['gap_ma'] for r in rows1[:2]]) if rows1 else sh1['gap_ma']
    t4 = P.pick_gap_second({k: v for k, v in d1.items() if k - min(d1) <= 600}, ('mid', 'att'), early)
    if t4:
        out.append(gap_card('fix', '고칠 점', '전반 초반에는 중원이 공격수를 놓쳤다', d1, ('mid', 'att'), ('중원 줄', '공격 줄'), t4,
                            f'<p class="big">전반 처음 10분에는 중원과 공격 사이가 평균 {early:.0f}m까지 벌어졌습니다.</p>',
                            '이 거리에서 공격수가 공을 받으면 어떤 일이 생기나요? 중원은 언제 올라가야 했을까요?',
                            '경기 시작부터 중원이 공격수 쪽으로 먼저 올라가 거리를 맞춥니다. 공을 잡은 순간이 아니라 공이 중원에게 오기 전에 움직입니다.',
                            '공격수 2명, 중원 4명으로 4대4 구역 공격 연습(공격수 뒤 15m 안에서만 중원이 받음).',
                            '공이 수비수에게 있을 때부터 중원이 올라가 공격수와 15m를 유지한다.'))

    lanes_cur, width_cur = attack_lane_share([d1, d2])
    lanes_prev, width_prev = attack_lane_share([R.read(args.prev_h1), R.read(args.prev_h2)]) if args.prev_h1 and args.prev_h2 else (None, None)
    wide_cur = lanes_cur[0] + lanes_cur[4]
    prev_text = f' 지난 경기도 같은 모양이었습니다(양쪽 측면 {lanes_prev[0] + lanes_prev[4]:.0f}%, 팀 폭 평균 {width_prev:.0f}m).' if lanes_prev else ''
    answers.append(('공격할 때 너무 가운데로만 선다', f'우리가 공격할 때 선수 위치의 양쪽 측면 비율은 {wide_cur:.0f}%, 가운데와 안쪽 길이 {sum(lanes_cur[1:4]):.0f}%였다. 측면 미드필더가 공이 반대편에 있어도 터치라인 쪽에 서서 폭을 유지해야 상대 수비가 벌어진다.'))
    out.append('<div class="card fix"><span class="tag">고칠 점</span><h2>공격할 때 너무 가운데로만 선다</h2><div class="grid"><div>'
               f'<p class="big">우리가 상대 진영에서 공격할 때 선수들이 선 길입니다. 양쪽 측면에는 합쳐서 {wide_cur:.0f}%만 있었습니다.</p>'
               f'<p>상대 진영에서 공격할 때 팀의 옆 폭은 평균 {width_cur:.0f}m였고 경기장 폭의 약 {100 * width_cur / R.W:.0f}%입니다.{prev_text} 폭이 좁으면 상대 수비가 가운데에 모여 막기 쉽습니다.</p></div>'
               f'<div>{lane_share_svg(lanes_cur, width_cur)}</div></div>'
               '<div class="q"><b>질문</b> 그림에서 노랑 칸(양쪽 측면)에는 몇 명이 서 있어야 상대 수비가 벌어질까요? 반대편에서 공을 가진 동안 측면 미드필더는 어디에 서야 할까요?</div>'
               '<div class="do"><b>다음엔 이렇게</b> 공이 반대편에 있어도 측면 미드필더 한 명은 터치라인 가까이 서서 폭을 유지합니다. 공이 오면 바로 돌려 받아 상대 수비를 옆으로 끌어냅니다.</div>'
               '<div class="drill"><b>연습 제안</b> 터치라인 2m 안쪽 구역에 반드시 한 명이 서 있어야 공격이 시작되는 6대6 미니 경기(측면 선수가 공을 받을 때만 골 인정 2배).</div></div>')

    if args.width_dir and (Path(args.width_dir) / 'width_photos.json').is_file():
        info = json.loads((Path(args.width_dir) / 'width_photos.json').read_text(encoding='utf-8'))
        figs = ''.join(f'<div><img alt="공격할 때 좁게 선 순간" style="width:100%;border-radius:8px" src="{P.uri(Path(args.width_dir) / x["file"], "image/jpeg")}"><p class="note">{x["half"]} {int(x["minute"])}분 {int((x["minute"] % 1) * 60):02d}초, 우리 팀 옆 폭 {x["width"]:.0f}m</p></div>' for x in info)
        out.append('<div class="card fix"><span class="tag">영상으로 확인</span><h2>이렇게 좁게 서 있었다</h2><p class="big">우리가 공격하던 순간을 사진 위에 그렸습니다. 노란 칸이 양쪽 측면 길, 파랑이 우리, 주황이 상대입니다.</p>'
                   f'<div class="grid">{figs}</div><p class="note">이 사진들은 공격할 때 가장 좁게 섰던 순간 가운데 고른 것이라 가장 극단적인 예입니다. 평균은 24m였습니다. 노란 칸에 파랑이 거의 없다는 점이 핵심입니다.</p>'
                   '<div class="q"><b>질문</b> 사진에서 노란 칸에는 우리 선수가 몇 명 있나요? 공을 받을 수 있는 가장 가까운 옆 선수는 몇 걸음 거리에 있나요?</div></div>')

    # ---- forwards
    out.append(f'<h2 class="pos">공격수 편</h2><p class="who">{GROUPS["att"][1]}</p>')
    sc = s_by('전반', 'our_attack', 0)
    lane_text = R.LANES[top_o] if top_o is not None else '여러 길'
    out.append(scene_card('good', '잘한 점', '박스 안으로 들어가는 움직임이 많았다', sc, d1, 'att',
                          f'<p>오늘 우리 박스 진입은 {own_box}번이었습니다. 공격 진영에 가장 많이 들어간 길은 {lane_text}({lanes_o[top_o]}번/{sum(lanes_o)}번)이었고, 박스는 폭이 40m라 측면 길이 거의 나오지 않아서 박스 안 길은 비교하지 않았습니다.</p>',
                          '그림에서 박스에 가장 먼저 들어간 선수는 누구이고, 다른 선수는 어디를 비워 주었나요?',
                          '공이 측면에 있으면 가까운 포스트, 먼 포스트, 뒤쪽 자리를 나누어 서서 세 곳을 채웁니다.', '',
                          '박스에 먼저 들어간 선수가 앞 포스트, 다음이 먼 포스트, 마지막이 뒤쪽 자리를 맡는다.'))
    sc = s_by('후반', 'our_attack', 0)
    out.append(scene_card('fix', '고칠 점', '박스에는 들어갔는데 슛으로 끝내지 못했다', sc, d2, 'att',
                          f'<p>박스까지 간 공격 {own_box}번 가운데 표시된 우리 슛은 {shots["ours"]}번(유효슈팅 {shots["ours_on"]}번)이고, 빠르게 올라간 직접 공격은 {direct}번이었습니다.</p>',
                          '이 장면에서 슛을 찰 수 있었던 순간은 언제였나요? 한 번 더 패스한 이유는 무엇이었나요?',
                          '박스 앞에서 공을 받으면 돌아보지 않고 첫 터치로 슛 각도를 만듭니다. 박스 안에 둘 이상 있으면 먼저 슛하고, 나머지는 튄 공을 노립니다.',
                          '박스 앞에서 공을 받아 두 번 안에 슛하는 연습(수비 1명 붙임), 3명 침투 후 슛 5개 연속 시간제한 게임.',
                          '공을 받은 첫 터치에서 슛 각도를 만들고, 두 번째 선수는 튄 공 자리로 들어간다.'))

    # ---- goalkeeper
    out.append('<h2 class="pos">골키퍼 편</h2><p class="who">골키퍼</p>')
    out.append(f'<div class="card good"><span class="tag">잘한 점</span><h2>오늘 상대의 유효슈팅을 막았다</h2><p>표시된 기록으로 상대의 유효슈팅 {shots["saved_by_us"]}번을 막아 냈습니다. 골키퍼의 움직임은 영상에서 안정적으로 잡히지 않아서 따로 분석하지 않았습니다.</p>'
               '<div class="q"><b>질문</b> 상대가 우리 수비 줄 뒤로 들어올 때 골키퍼는 어디까지 나와서 공간을 지켰나요?</div>'
               '<div class="do"><b>그대로 계속</b> 수비 줄이 높을 때는 골키퍼도 박스 밖까지 나와서 수비 줄 뒤 공간을 같이 지킵니다.</div></div>')

    out.append('<div class="card next"><h2>이번 주 연습</h2><div class="do"><b>수비·중원</b> 두 줄 15m 간격 미니 경기</div><div class="do"><b>중원·공격</b> 공격수 뒤 15m 안에서 받아 주는 4대4</div><div class="do"><b>공격</b> 박스 앞 두 번 터치 슛</div><div class="do"><b>수비</b> 하프스페이스 3대3 구역 수비</div></div>')
    out.append('<div class="card"><h2>코치용 정답 메모</h2><ol class="ans">' + ''.join(f'<li><b>{html.escape(t)}</b>: {html.escape(a)}</li>' for t, a in answers) + '</ol></div>')
    out.append('<p class="note">참고: 선수 이름이 없는 추적이라 포지션은 장면 순간의 위치 순서로 나눈 것이고, 실제 포지션과 다를 수 있습니다. 먼 쪽 선수 일부가 빠지고, 공은 보지 않고 위치로 정리한 부분이 많습니다. 연습 제안은 일반적인 코칭 방법이며 이 자료의 결과가 아닙니다.</p></main></body></html>')
    Path(args.out).write_text(''.join(out), encoding='utf-8')
    print('wrote', args.out, Path(args.out).stat().st_size)


if __name__ == '__main__':
    main()
