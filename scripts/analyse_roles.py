"""How did each place of the team (left back, central midfielder, ...) really play in a stretch of the match? Slot level, not person level (research, read only).

python scripts/analyse_roles.py <positions.jsonl> [<positions.jsonl> ...] [--window 300] [--out result.json] [--markdown result.md]

Input: the positions files of scripts/run_live_feedback.py --positions (team B, metres, no names). For every second with at least 9 outfield players the position slots of app/position_slots.py are assigned.
Then, per window of --window seconds and per slot: how many seconds the slot was filled, how far ahead of (+) or behind (-) the average outfield player it stood (depth), how wide it stood
(lateral, the team's left negative), how much it moved (spread of depth and lateral) and the share of the time spent in the opponent half. Also the most common formation text of the window and
how often it was the answer (the formation of a single second is noisy, see app/team_formation.py: a low share means the shape changed, not that the number is wrong).
A short Dutch-style verdict per slot ("walked high like a wing back", "stayed close to the centre") is written only when the slot was observed for at least 60 seconds in the window.
This describes what the places did; it does NOT say which person stood there (track numbers break when a player is hidden or the camera moves, identity research is paused), and it is not a plan or a forecast.
"""
import argparse
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.position_slots import POSITION_TEXT, assign_slots  # noqa: E402

MIN_SECONDS = 60
MIN_OUTFIELD = 9


def read(path):
    header, seconds = None, []
    for line in Path(path).read_text(encoding='utf-8').splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r['type'] == 'header':
            header = r
        elif r['type'] == 'second':
            seconds.append(r)
    return header, seconds


def verdict(slot, rel_depth, lateral, half_share):
    """Plain words for what the numbers say, only for the places where the numbers can say something."""
    width = abs(lateral)
    if slot == 'defence':
        return '수비 줄이 팀 평균보다 ' + f'{abs(rel_depth):.0f}미터 뒤에 있었고 상대 진영에는 거의 가지 않았습니다' if half_share < 0.1 else '수비 줄이 상대 진영까지 올라온 시간이 있었습니다'
    if slot == 'midfield':
        return '중원이 상대 진영에서 ' + f'{half_share:.0%}를 보내며 팀의 중심 근처를 지켰습니다' if abs(rel_depth) < 5 else ('중원이 앞으로 치우쳐 있었습니다' if rel_depth > 0 else '중원이 뒤로 내려와 있었습니다')
    if slot == 'attack':
        return '공격 줄이 팀 평균보다 ' + f'{rel_depth:.0f}미터 앞, 상대 진영에서 {half_share:.0%}를 보냈습니다'
    if slot in ('LB', 'RB', 'LWB', 'RWB'):
        if rel_depth > 6 and half_share > 0.3:
            return '측면 수비가 상대 진영까지 자주 올라가 윙백처럼 뛰었습니다'
        if rel_depth < -3:
            return '측면 수비가 팀 평균보다 뒤에서 수비 라인을 지켰습니다'
        return '측면 수비가 팀 평균 가까이에서 균형을 잡았습니다'
    if slot in ('LCB', 'CB', 'RCB'):
        return '중앙 수비가 팀 평균보다 뒤에서 라인을 지켰습니다' if rel_depth < -6 else '중앙 수비가 평균보다 앞으로 나와 라인을 올린 편입니다'
    if slot in ('LM', 'RM', 'LW', 'RW'):
        return '측면에 넓게 서서 폭을 만들었습니다' if width > 18 else '측면 선수가 중앙 쪽으로 좁혀 들어와 있었습니다'
    if slot in ('LCM', 'CM', 'RCM'):
        return '중원이 팀 평균보다 앞에서 뛰었습니다' if rel_depth > 4 else ('중원이 팀 평균보다 뒤로 내려와 수비를 도왔습니다' if rel_depth < -4 else '중원이 팀의 중심 근처에서 연결 역할을 했습니다')
    if slot in ('ST', 'LS', 'RS'):
        return '공격수가 상대 진영 깊이 머물렀습니다' if half_share > 0.6 else '공격수가 내려와 중원 근처까지 뛰었습니다'
    return ''


def analyse(files, window):
    rows = []
    for path in files:
        header, seconds = read(path)
        direction = header['direction']
        for r in seconds:
            players = [(t, x, y) for t, x, y in r['team']]
            if len(players) < MIN_OUTFIELD:
                continue
            result = assign_slots(players, direction)
            outfield = [(t, x * direction, y * direction) for t, x, y in players if t != result['goalkeeper']]
            if len(outfield) < MIN_OUTFIELD:
                continue
            mean_depth = statistics.mean(d for _t, d, _l in outfield)
            rows.append({'time': r['time'], 'formation': result['formation'], 'depth': {t: d - mean_depth for t, d, _l in outfield}, 'abs_depth': {t: d for t, d, _l in outfield},
                         'lateral': {t: l for t, _d, l in outfield}, 'slots': result['slots']})
    rows.sort(key=lambda r: r['time'])
    windows = defaultdict(list)
    for r in rows:
        windows[int(r['time'] // window)].append(r)
    out = []
    for index in sorted(windows):
        block = windows[index]
        slots = defaultdict(lambda: {'rel': [], 'lat': [], 'abs': []})
        for r in block:
            for t, slot in r['slots'].items():
                if slot == 'GK' or t not in r['depth']:
                    continue
                slots[slot]['rel'].append(r['depth'][t])
                slots[slot]['lat'].append(r['lateral'][t])
                slots[slot]['abs'].append(r['abs_depth'][t])
        formations = Counter(r['formation'] for r in block if r['formation'])
        top = formations.most_common(1)[0] if formations else (None, 0)
        table = {}
        for slot, v in slots.items():
            n = len(v['rel'])
            if n < MIN_SECONDS:
                continue
            half = sum(1 for a in v['abs'] if a > 0) / n
            rel, lat = statistics.mean(v['rel']), statistics.mean(v['lat'])
            table[slot] = {'seconds': n, 'rel_depth': round(rel, 1), 'depth_spread': round(statistics.pstdev(v['rel']), 1), 'lateral': round(lat, 1),
                           'lateral_spread': round(statistics.pstdev(v['lat']), 1), 'opponent_half_share': round(half, 2), 'verdict': verdict(slot, rel, lat, half)}
        out.append({'from': round(index * window), 'to': round((index + 1) * window), 'seconds_used': len(block), 'formation': top[0], 'formation_share': round(top[1] / len(block), 2) if block else 0,
                    'slots': table})
    return out


def minutes(s):
    return f'{int(s // 60)}:{int(s % 60):02d}'


def markdown(result):
    lines = []
    for w in result:
        lines.append(f'### 영상 {minutes(w["from"])}~{minutes(w["to"])} (분석에 쓴 초 {w["seconds_used"]}, 가장 흔한 배치 {w["formation"] or "없음"} {w["formation_share"]:.0%})')
        if not w['slots']:
            lines.append('- 60초 이상 관찰된 자리가 없습니다.\n')
            continue
        lines += ['| 자리 | 관찰 초 | 팀 평균 대비 깊이(m) | 폭(m, 팀 왼쪽이 -) | 상대 진영 비율 | 설명 |', '|---|---|---|---|---|---|']
        for slot, s in sorted(w['slots'].items(), key=lambda kv: kv[1]['rel_depth']):
            lines.append(f'| {POSITION_TEXT.get(slot, slot)}({slot}) | {s["seconds"]} | {s["rel_depth"]:+.1f} | {s["lateral"]:+.1f} | {s["opponent_half_share"]:.0%} | {s["verdict"]} |')
        lines.append('')
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('files', nargs='+')
    parser.add_argument('--window', type=int, default=300)
    parser.add_argument('--out')
    parser.add_argument('--markdown')
    args = parser.parse_args()
    result = analyse(args.files, args.window)
    text = markdown(result)
    print(text)
    if args.out:
        Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding='utf-8')
    if args.markdown:
        Path(args.markdown).write_text(text, encoding='utf-8')


if __name__ == '__main__':
    main()
