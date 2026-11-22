"""Player cards from the tracks that a person (or the number on the shirt) has tied to a player.

Usage: python scripts/build_player_cards.py <store> <calibrations.json> <out folder> --half "<spec>" [--half "<spec>" ...] [--team B]
(<spec> is the same text as for build_match_report.py / prepare_player_review.py; the half key is the key of the player store, so write it as `h1=<spec>`.)

For every player of the roster that has tracks, one card (PNG) with: the clearest picture, the number and the name, the time the cameras could follow him, the distance run,
the speed in the fastest 2 % of the seconds, the number of sprints, the longest run, a heat map in attack direction and the mean position.

What the numbers mean (they are printed on the card, too):
  * They count only the seconds in which a track tied to the player exists. A player followed for 12 of 25 minutes shows the distance of those 12 minutes, not of the match.
  * Speed is the straight distance covered in one second (5 samples) from the metre coordinates of the pitch calibration; steps above 9 m/s (32 km/h) are treated as tracking jumps and dropped.
  * A sprint is a run above 5 m/s that lasts at least one second.
"""
import argparse
import json
import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from app.player_identity import PlayerIdentity  # noqa: E402
from build_match_report import load_half  # noqa: E402

FONT = 'C:/Windows/Fonts/malgun.ttf'
FONT_BOLD = 'C:/Windows/Fonts/malgunbd.ttf'
MAX_STEP_SPEED, SPRINT_SPEED, SPRINT_SECONDS = 9.0, 5.0, 1.0
MAX_PLAUSIBLE = 9.0                                                         # m/s: a faster 'run' is a tracking jump (the best youth sprinters reach about 8)
LENGTH, WIDTH = 89.0, 62.0


def font(size, bold=False):
    return ImageFont.truetype(FONT_BOLD if bold else FONT, size)


def run_stats(samples, fps):
    """samples: [(frame, u, y)] sorted by frame. Returns distance, top speed, sprints, longest run (m), seconds covered and the (frame, speed) series."""
    distance, series, covered = 0.0, [], 0.0
    for (f0, u0, y0), (f1, u1, y1) in zip(samples, samples[1:]):
        gap = (f1 - f0) / fps
        if gap <= 0 or gap > 1.0:                                           # a hole in the track: neither distance nor time
            continue
        step = math.hypot(u1 - u0, y1 - y0)
        if step / gap > MAX_STEP_SPEED:
            continue
        distance += step
        covered += gap
        series.append((f1, step / gap))
    window = max(1, int(round(fps)))
    by_frame = {f: (u, y) for f, u, y in samples}
    smooth = []                                                              # speed over one second: the straight distance between two positions one second apart (jitter cancels out)
    for f in sorted(by_frame):
        if f + window in by_frame:
            (u0, y0), (u1, y1) = by_frame[f], by_frame[f + window]
            if math.hypot(u1 - u0, y1 - y0) <= MAX_PLAUSIBLE * window / fps:
                smooth.append((f + window, math.hypot(u1 - u0, y1 - y0) * fps / window))
    speeds = sorted(s for _, s in smooth)
    top = speeds[int(0.98 * (len(speeds) - 1))] if speeds else 0.0           # the 98th percentile: the single fastest second is too often a measuring jump
    sprints, longest, start, last = 0, 0.0, None, None
    for frame, speed in smooth:
        if speed >= SPRINT_SPEED:
            if start is None or last is None or frame - last > 2:
                if start is not None and (last - start) / fps + 1 >= SPRINT_SECONDS:
                    sprints += 1
                start = frame
            last = frame
    if start is not None and last is not None and (last - start) / fps + 1 >= SPRINT_SECONDS:
        sprints += 1
    return {'distance': distance, 'top': top, 'sprints': sprints, 'covered': covered, 'series': smooth}


def heat_image(points, size=(440, 292)):
    w, h = size
    image = Image.new('RGB', size, (30, 58, 42))
    cells = {}
    for u, y in points:
        key = (int((u + LENGTH / 2) / LENGTH * 22), int((y + WIDTH / 2) / WIDTH * 15))
        cells[key] = cells.get(key, 0) + 1
    top = max(cells.values(), default=1)
    draw = ImageDraw.Draw(image, 'RGBA')
    for (cx, cy), count in cells.items():
        a = int(40 + 190 * (count / top) ** 0.6)
        draw.rectangle([cx * w / 22, cy * h / 15, (cx + 1) * w / 22, (cy + 1) * h / 15], fill=(255, 150, 40, a))
    line = (235, 245, 238, 200)
    draw.rectangle([1, 1, w - 2, h - 2], outline=line, width=2)
    draw.line([w / 2, 0, w / 2, h], fill=line, width=2)
    r = 9.15 / LENGTH * w
    draw.ellipse([w / 2 - r, h / 2 - r * (w / h) * (h / w), w / 2 + r, h / 2 + r], outline=line, width=2)
    for x0 in (0, w - 16.5 / LENGTH * w):
        draw.rectangle([x0, h / 2 - 20.15 / WIDTH * h, x0 + 16.5 / LENGTH * w, h / 2 + 20.15 / WIDTH * h], outline=line, width=2)
    draw.text((w - 120, h - 26), '공격 방향 →', font=font(16), fill=(255, 255, 255, 200))
    return image


def total_covered(per_half):
    return sum(v['covered'] for v in per_half.values())


def clock(seconds):
    return f'{int(seconds // 60)}:{int(seconds % 60):02d}'


def card(player, per_half, heat, photo, minutes_text):
    image = Image.new('RGB', (1260, 640), (17, 21, 27))
    draw = ImageDraw.Draw(image)
    draw.text((30, 20), f'{"#" + str(player["number"]) if player["number"] is not None else ""}  {player["name"]}', font=font(46, True), fill=(255, 255, 255))
    draw.text((30, 82), f'{player.get("position") or ""} · 팀 {player["team"]}', font=font(22), fill=(150, 160, 172))
    if photo is not None:
        photo = photo.copy()
        photo.thumbnail((200, 330))
        image.paste(photo, (30, 130))
    total = {'distance': sum(s['distance'] for s in per_half.values()), 'covered': sum(s['covered'] for s in per_half.values()), 'sprints': sum(s['sprints'] for s in per_half.values()),
             'top': max(s['top'] for s in per_half.values())}
    rows = [('추적된 시간(끊기지 않고 따라간 시간)', minutes_text), ('달린 거리', f'{total["distance"]:.0f} m'), ('빠를 때의 속도(상위 2%)', f'{total["top"] * 3.6:.1f} km/h ({total["top"]:.1f} m/s)'), ('스프린트(5 m/s 이상, 1초 넘게)', f'{total["sprints"]}회')]
    y = 135
    for label, value in rows:
        draw.text((260, y), label, font=font(20), fill=(150, 160, 172))
        draw.text((260, y + 26), value, font=font(34, True), fill=(255, 255, 255))
        y += 82
    if total['covered'] > 0:
        draw.text((260, y), '1분당 달린 거리', font=font(20), fill=(150, 160, 172))
        draw.text((260, y + 26), f'{total["distance"] / total["covered"] * 60:.0f} m', font=font(34, True), fill=(255, 255, 255))
    image.paste(heat_image(heat), (780, 130))
    draw.text((780, 100), '머문 자리(진할수록 오래 머묾)', font=font(20), fill=(150, 160, 172))
    if heat:
        mean_u = sum(u for u, _ in heat) / len(heat)
        mean_y = sum(v for _, v in heat) / len(heat)
        draw.text((780, 430), f'평균 위치: 중앙선에서 공격 방향 {mean_u:+.0f} m, 가로 {mean_y:+.0f} m', font=font(20), fill=(220, 226, 232))
    note = '추적된 구간만 계산한 값입니다. 추적이 끊긴 시간의 움직임은 들어 있지 않으므로 경기 전체 기록이 아닙니다.'
    draw.text((30, 560), note, font=font(18), fill=(150, 160, 172))
    draw.text((30, 588), '속도는 경기장 보정으로 얻은 미터 좌표에서 1초 단위로 쟀고, 휴대폰 영상의 한계로 오차가 있을 수 있습니다.', font=font(18), fill=(150, 160, 172))
    return image


def confirmed_card_tracks(chain, player_id):
    """Unverified legacy/automatic names remain in review, never in confirmed cards."""
    return [t for t in (chain or {}).get('mine', [])
            if not t.get('conflict') and t.get('confirmed_player') == player_id]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('store')
    parser.add_argument('calibrations')
    parser.add_argument('out')
    parser.add_argument('--half', action='append', required=True, help='<key>=<spec>')
    parser.add_argument('--team', default='B')
    args = parser.parse_args()
    store, out = Path(args.store), Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    calibrations = json.loads(Path(args.calibrations).read_text(encoding='utf-8'))
    ids = PlayerIdentity(store)
    halves = {}
    for item in args.half:
        key, spec = item.split('=', 1)
        halves[key] = load_half(spec, calibrations, args.team)
    roster = [p for p in ids.state(next(iter(halves)))['roster'] if p['team'] == args.team]
    notes_file = store / 'players' / 'auto_notes.json'
    read_from_shirt = json.loads(notes_file.read_text(encoding='utf-8')).get('notes', {}) if notes_file.is_file() else {}      # tracks whose number was read on a picture: their pictures show the shirt
    overrides_file = store / 'players' / 'card_photos.json'
    overrides = json.loads(overrides_file.read_text(encoding='utf-8')) if overrides_file.is_file() else {}               # {player id: 'h1/21890_0.jpg'}: a picture chosen by a person
    summary = []
    for player in roster:
        per_half, heat, seconds, best = {}, [], 0.0, None
        for key, half in halves.items():
            chain = ids.chain(key, player['id'])
            confirmed_tracks = confirmed_card_tracks(chain, player['id'])
            if not confirmed_tracks:
                continue
            sign = half['direction']
            positions = {}
            for frame, teams in half['by_frame'].items():
                for tid, x, y in teams.get(args.team, []):
                    positions.setdefault(tid, []).append((frame, x * sign, y * sign))
            parts = []
            used = set()                                                     # frames already counted for this player: two tracks that follow him at the same moment must not count twice
            for track in sorted(confirmed_tracks, key=lambda t: t['first'] - t['last']):      # the longest first: two tracks of a player may be far apart, and a jump between them is not a run
                mine = sorted(p for p in positions.get(track['id'], []) if p[0] not in used)
                used |= {p[0] for p in mine}
                parts.append((mine, run_stats(mine, half['fps'])))
                heat += [(u, y) for _, u, y in mine]
                seconds += track['last'] - track['first']
                rank = (track['id'] in read_from_shirt.get(key, {}), max(track.get('sharpness') or [0]))
                if track.get('pictures') and (best is None or rank > best[0]):
                    best = (rank, store / 'players' / key / track['pictures'][0])
            per_half[key] = {'distance': sum(x['distance'] for _, x in parts), 'covered': sum(x['covered'] for _, x in parts), 'sprints': sum(x['sprints'] for _, x in parts), 'top': max((x['top'] for _, x in parts), default=0.0)}
        if not per_half:
            continue
        chosen = (overrides.get(player['id']) and store / 'players' / overrides[player['id']]) or (best and best[1])
        photo = Image.open(chosen) if chosen and Path(chosen).is_file() else None
        stats_only = per_half
        image = card(player, per_half, heat, photo, f'{total_covered(per_half) / 60:.1f}분')
        name = f'card_{player["number"] if player["number"] is not None else player["id"]}.png'
        image.save(out / name)
        summary.append({'assignment_policy': 'human_confirmed_only', 'player': player['name'], 'number': player['number'], 'file': name, 'seconds': round(seconds, 1), 'distance': round(sum(s['distance'] for s in stats_only.values()), 1),
                        'top_kmh': round(max(s['top'] for s in stats_only.values()) * 3.6, 1), 'sprints': sum(s['sprints'] for s in stats_only.values())})
        print(summary[-1])
    (out / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding='utf-8')


if __name__ == '__main__':
    main()
