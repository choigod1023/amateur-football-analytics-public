"""Set-piece candidate list for our own match (corner, free kick, throw-in, goal kick): times for a person to answer yes or no.

Usage: python -X utf8 scripts/find_set_piece_candidates.py [--out work/set-piece-candidates-20261117] [--no-audio]

There is no ball for the whole match (ball paths exist only for 54 short clips), so this does NOT see the ball. It collects weak evidence and
adds it up per moment:
  1. A player of team A or B who stands still for 1.6 s or more at a place where a restart is taken (corner zone, touchline, goal area).
  2. Referee whistle sounds in the audio (narrow strong peak at 2.5 to 4.5 kHz).
  3. Stretches where nearly every tracked player moves slowly (play flow breaks).
  4. A ball that rests near a line inside one of the 54 ball-path clips (only where those clips exist).
Each moment gets a kind guess, reasons, a score and a rough confidence. There are no ground-truth labels, so nothing here is a measured
precision or recall. Kick-offs (formation test) and goals are kept in a separate reference list as a sanity check of the machinery.

CPU only. No GPU, no model, no training. Audio is decoded once with ffmpeg (about 48 minutes of mono 16 kHz).
Outputs: <out>/candidates.json (list for the person), <out>/reference.json (kick-off and goal checks, raw evidence counts).
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT.parents[1] / 'work'
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
from app.pitch_map import feet_to_metres, fit  # noqa: E402
from build_team_minimap import parse_schedule, shift_at  # noqa: E402

VIDEO = WORK / 'own-match-merged-20261111' / 'match_from_17min.mp4'
FFMPEG = WORK / 'ffmpeg-local' / 'ffmpeg-9.0.2-essentials_build' / 'bin' / 'ffmpeg.exe'
CALIBRATIONS = WORK / 'human-labels' / 'public-own-match-review-20261111' / 'calibration' / 'calibrations.json'
TRACKS = WORK / 'tracks-ov3-20261113'
BALL_PATHS = WORK / 'ball-paths-v4-balanced.json'
FPS = 5.0
HL, HW = 44.5, 31.0            # half pitch length and width of the 89 x 62 m estimate used everywhere in this project
GOALS = []          # goal times of the match in video seconds (empty in this public copy)
KICKOFFS = []          # kick-off times of the match in video seconds (empty in this public copy)
# half name: tracks file, camera, video second of frame 0, background similarity, camera shift schedule, direction of team A (+1 attacks +x)
HALVES = {
    'h1': dict(file='h1_v3.json', cam='cam1', offset=64.0, bg=(1.000657, 0.000035, -0.67, -0.47), sched='0:0.0,-0.2', dir_a=1),
    'h2': dict(file='h2_v3.json', cam='cam3', offset=1740.0, bg=(1.003087, -0.001614, -7.41, 5.61), sched='0:-1.8,6.8;1950:0.3,0.3', dir_a=-1),
}
UNCOVERED = [(1480.0, 1740.0)]   # halftime and the cam2 scenes: no tracks and no calibration here (whistles only)


def mmss(t):
    t = int(round(t))
    return f'{t // 60}:{t % 60:02d}'


# ---- positions -------------------------------------------------------------------------------------------------------------------
def load_half(name):
    cfg = HALVES[name]
    result = json.loads((TRACKS / cfg['file']).read_text(encoding='utf-8'))
    record = json.loads(CALIBRATIONS.read_text(encoding='utf-8'))[cfg['cam']]
    fitted = fit({**record, 'pitch': {**(record.get('pitch') or {}), 'length': 89, 'width': 62}})
    schedule = parse_schedule(cfg['sched'])
    paths = {}
    for tid, rows in result['tracks'].items():
        for row in rows:
            if row['team'] not in ('A', 'B'):
                continue
            m = feet_to_metres(fitted, row['box'], 1920, 1080, shift_at(schedule, row['frame']), cfg['bg'])
            if m is not None:
                paths.setdefault(tid, []).append((row['frame'], m[0], m[1], row['team']))
    for rows in paths.values():
        rows.sort()
    return dict(cfg=cfg, frames=int(result['frames']), paths=paths, fitted=fitted, schedule=schedule)


def stand_still_episodes(rows, radius=1.3, min_seconds=1.6, max_gap=4):
    """Runs where the track stays within `radius` metres of its running mean (frames of 5 fps, gaps up to max_gap frames)."""
    f = np.array([r[0] for r in rows]); x = np.array([r[1] for r in rows]); y = np.array([r[2] for r in rows])
    out, i, n = [], 0, len(f)
    while i < n:
        j = i
        while j + 1 < n and f[j + 1] - f[j] <= max_gap:
            if np.hypot(x[j + 1] - x[i:j + 1].mean(), y[j + 1] - y[i:j + 1].mean()) > radius:
                break
            j += 1
        if (f[j] - f[i]) / FPS >= min_seconds:
            out.append((i, j))
        i = j + 1
    return f, x, y, out


def zone_of(x, y):
    if abs(x) >= HL - 5 and abs(y) >= HW - 4.5:
        return 'corner'
    if abs(y) >= HW - 2.5:
        return 'touch'
    if abs(x) >= HL - 9 and abs(y) <= 9.2:
        return 'goalarea'
    return None


def position_events(half, name):
    """Standing-still restarter events: corner zone, touchline band, goal area."""
    cfg, events = half['cfg'], []
    team_by_frame = {}
    for tid, rows in half['paths'].items():
        for f, x, y, team in rows:
            team_by_frame.setdefault(f, []).append((tid, team, x, y))
    for tid, rows in half['paths'].items():
        if len(rows) < 12:
            continue
        f, x, y, eps = stand_still_episodes(rows)
        for i, j in eps:
            cx, cy = x[i:j + 1].mean(), y[i:j + 1].mean()
            zone = zone_of(cx, cy)
            if zone is None:
                continue
            seconds = (f[j] - f[i]) / FPS
            before = (f >= f[i] - 40) & (f < f[i]); after = (f > f[j]) & (f <= f[j] + 40)
            far_before = float(np.hypot(x[before] - cx, y[before] - cy).max()) if before.any() else 0.0
            far_after = float(np.hypot(x[after] - cx, y[after] - cy).max()) if after.any() else 0.0
            if max(far_before, far_after) < 5:          # never leaves the spot: bench, staff, or a person who is not playing
                continue
            mid = int(f[(i + j) // 2])
            others = team_by_frame.get(mid, [])
            t0, t1 = cfg['offset'] + f[i] / FPS, cfg['offset'] + f[j] / FPS
            ev = dict(half=name, zone=zone, tid=tid, team=rows[0][3], x=round(float(cx), 1), y=round(float(cy), 1), t0=t0, t1=t1,
                      seconds=round(seconds, 1), far_before=round(far_before, 1), far_after=round(far_after, 1))
            if zone == 'corner':
                att_side = 1 if cx > 0 else -1
                box = [o for o in others if o[2] * att_side >= HL - 16.5 and abs(o[3]) <= 20.15 and o[0] != tid]
                ev['in_box'] = len(box)
            elif zone == 'goalarea':
                side = 1 if cx > 0 else -1
                deeper = [o for o in others if o[1] == rows[0][3] and o[0] != tid and o[2] * side > cx * side]
                if deeper or seconds < 2.4:             # not the deepest player of his team, or too short: ordinary idling
                    continue
                opp = [o for o in others if o[1] != rows[0][3] and o[2] * side >= HL - 16.5]
                ev['opponents_in_box'] = len(opp)
                if opp:
                    continue
            elif zone == 'touch':
                if seconds > 9.0:                        # a long stand at the line is a bench or a spectator
                    continue
            events.append(ev)
    return events


def flow_breaks(half, name):
    """Intervals where the 75th percentile of the smoothed player speeds drops under the 12th percentile of the match (>= 4 s)."""
    n = half['frames']
    cols = list(half['paths'].values())
    X = np.full((n, len(cols)), np.nan); Y = X.copy()
    for j, rows in enumerate(cols):
        for f, x, y, _ in rows:
            X[f, j], Y[f, j] = x, y

    def smooth(A, k=5):
        ok = ~np.isnan(A)
        padded = np.pad(np.where(ok, A, 0.0), ((k // 2, k - 1 - k // 2), (0, 0)), mode='edge')
        counts = np.pad(ok.astype(float), ((k // 2, k - 1 - k // 2), (0, 0)), mode='edge')
        num = np.vstack([np.zeros((1, A.shape[1])), np.cumsum(padded, 0)]); den = np.vstack([np.zeros((1, A.shape[1])), np.cumsum(counts, 0)])
        s, c = (num[k:] - num[:-k]), (den[k:] - den[:-k])
        out = np.where(c > 0.3 * k, s / np.maximum(c, 1e-9), np.nan)
        out[~ok] = np.nan
        return out

    Xs, Ys = smooth(X), smooth(Y)
    L = 10
    V = np.full_like(X, np.nan)
    V[L:-L] = np.hypot(Xs[2 * L:] - Xs[:-2 * L], Ys[2 * L:] - Ys[:-2 * L]) / (2 * L / FPS)
    q = np.array([np.nanpercentile(r, 75) if np.sum(~np.isnan(r)) >= 6 else np.nan for r in V])
    low = q < np.nanpercentile(q, 12)
    out, j = [], 0
    while j < n:
        if not low[j]:
            j += 1
            continue
        k = j
        while k + 1 < n and (low[k + 1] or (k + 3 < n and low[k + 3])):
            k += 1
        if (k - j) / FPS >= 4:
            off = half['cfg']['offset']
            out.append(dict(half=name, t0=off + j / FPS, t1=off + k / FPS))
        j = k + 1
    return out


def kickoff_formations(half, name):
    """Moments where both teams stand in their own half with someone near the centre spot (reference only: kick-off check)."""
    cfg = half['cfg']
    by_frame = {}
    for tid, rows in half['paths'].items():
        for f, x, y, team in rows:
            by_frame.setdefault(f, {'A': [], 'B': []})[team].append((x, y))
    hit = []
    for f in range(0, half['frames'], 5):
        a, b = by_frame.get(f, {}).get('A', []), by_frame.get(f, {}).get('B', [])
        if len(a) < 6 or len(b) < 6:
            continue
        own_a = np.mean([x * cfg['dir_a'] < 4 for x, _ in a]); own_b = np.mean([-x * cfg['dir_a'] < 4 for x, _ in b])
        if own_a < 0.8 or own_b < 0.8:
            continue
        if any(np.hypot(x, y) < 5 for x, y in a + b):
            hit.append(cfg['offset'] + f / FPS)
    runs, cur = [], []
    for t in hit:
        if cur and t - cur[-1] <= 3:
            cur.append(t)
        else:
            if len(cur) >= 3:
                runs.append((cur[0], cur[-1]))
            cur = [t]
    if len(cur) >= 3:
        runs.append((cur[0], cur[-1]))
    return runs


# ---- audio -----------------------------------------------------------------------------------------------------------------------
def whistles():
    """Seconds with a narrow strong peak at 2.5 to 4.5 kHz (referee whistle). Returns [] when ffmpeg or the video is missing."""
    if not FFMPEG.exists() or not VIDEO.exists():
        return []
    raw = subprocess.run([str(FFMPEG), '-hide_banner', '-loglevel', 'error', '-i', str(VIDEO), '-vn', '-ac', '1', '-ar', '16000', '-f', 's16le', '-'],
                         capture_output=True, check=True).stdout
    x = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
    sr, size, hop = 16000, 1024, 512
    window = np.hanning(size)
    freqs = np.fft.rfftfreq(size, 1 / sr)
    band = (freqs >= 2500) & (freqs <= 4500)
    count = (len(x) - size) // hop
    tonal = np.zeros(count)
    for start in range(0, count, 4000):
        stop = min(count, start + 4000)
        idx = np.arange(start, stop)[:, None] * hop + np.arange(size)[None, :]
        spec = np.abs(np.fft.rfft(x[idx] * window, axis=1)) ** 2
        tonal[start:stop] = spec[:, band].max(axis=1) / (np.median(spec, axis=1) + 1e-9)
    seconds = int(len(x) / sr)
    per_second = np.zeros(seconds)
    t = np.arange(count) * hop / sr
    for s in range(seconds):
        m = (t >= s) & (t < s + 1)
        if m.any():
            per_second[s] = np.percentile(tonal[m], 90)
    hits = [s for s in range(seconds) if per_second[s] >= 3000]
    groups, cur = [], []
    for s in hits:
        if cur and s - cur[-1] <= 2:
            cur.append(s)
        else:
            if cur:
                groups.append(cur)
            cur = [s]
    if cur:
        groups.append(cur)
    return [dict(t=float(g[0]), strength=float(max(per_second[s] for s in g))) for g in groups]


# ---- ball clips ------------------------------------------------------------------------------------------------------------------
def ball_rest_events(halves):
    """Where a clip's ball path rests (>= 1.2 s within 0.8 m, confidence >= 0.5) within 3 m of a boundary line."""
    if not BALL_PATHS.exists():
        return [], 0
    data = json.loads(BALL_PATHS.read_text(encoding='utf-8'))
    events, covered = [], 0
    for clip, rec in data.items():
        name = 'h1' if rec['camera'] == 'cam1' else ('h2' if rec['camera'] == 'cam3' else None)
        if name is None:
            continue
        half = halves[name]; cfg = half['cfg']
        pts = []
        for frame_name, (u, v, conf) in rec['path'].items():
            idx = int(frame_name.split('_')[1].split('.')[0])
            t = rec['start'] + (idx - 1) / rec['fps']
            if conf < 0.5:
                continue
            m = feet_to_metres(half['fitted'], [u, v, u, v], 1920, 1080, shift_at(half['schedule'], int((t - cfg['offset']) * FPS)), cfg['bg'])
            if m is not None:
                pts.append((t, m[0], m[1]))
        pts.sort()
        covered += 1
        i = 0
        while i < len(pts):
            j = i
            while j + 1 < len(pts) and np.hypot(pts[j + 1][1] - np.mean([p[1] for p in pts[i:j + 1]]), pts[j + 1][2] - np.mean([p[2] for p in pts[i:j + 1]])) <= 0.8 and pts[j + 1][0] - pts[j][0] <= 1.0:
                j += 1
            if pts[j][0] - pts[i][0] >= 1.2:
                cx, cy = np.mean([p[1] for p in pts[i:j + 1]]), np.mean([p[2] for p in pts[i:j + 1]])
                near_goal_line, near_touch = HL - abs(cx) <= 3.0, HW - abs(cy) <= 3.0
                if near_goal_line or near_touch:
                    kind = 'corner' if (near_goal_line and near_touch) else ('goalline' if near_goal_line else 'touch')
                    events.append(dict(clip=clip, zone=kind, x=round(float(cx), 1), y=round(float(cy), 1), t0=pts[i][0], t1=pts[j][0]))
            i = j + 1
    return events, covered


# ---- fusion ----------------------------------------------------------------------------------------------------------------------
def build(args):
    halves = {name: load_half(name) for name in HALVES}
    positions, flows, kicks = [], [], {}
    for name, half in halves.items():
        positions += position_events(half, name)
        flows += flow_breaks(half, name)
        kicks[name] = kickoff_formations(half, name)
    whistle = [] if args.no_audio else whistles()
    balls, ball_clips = ball_rest_events(halves)

    events = []     # every piece of evidence: time, source, score, kind guess, reason
    for e in positions:
        t = (e['t0'] + e['t1']) / 2
        if e['zone'] == 'corner':
            extra = f", 박스 안 선수 {e['in_box']}명" if 'in_box' in e else ''
            events.append(dict(t=t, src='corner', score=3.0, kind='코너킥', w=(e['t0'], e['t1']), x=e['x'], y=e['y'],
                               reason=f"코너 부근({e['x']:.0f}, {e['y']:.0f} m)에 {e['team']}팀 선수가 {e['seconds']}초 서 있음{extra}"))
        elif e['zone'] == 'touch':
            events.append(dict(t=t, src='touch', score=2.0, kind='스로인', w=(e['t0'], e['t1']), x=e['x'], y=e['y'],
                               reason=f"터치라인({e['x']:.0f}, {e['y']:.0f} m)에 {e['team']}팀 선수가 {e['seconds']}초 서 있음"))
        else:
            events.append(dict(t=t, src='goalarea', score=1.0, kind='골킥', w=(e['t0'], e['t1']), x=e['x'], y=e['y'],
                               reason=f"골 에어리어({e['x']:.0f}, {e['y']:.0f} m)에서 가장 깊은 {e['team']}팀 선수가 {e['seconds']}초 서 있고 상대는 박스 밖"))
    # a touchline event inside a crowded stretch of touchline events is probably a bench or spectators: lower it by one point
    touch = [e for e in events if e['src'] == 'touch']
    for e in touch:
        near = [o for o in touch if abs(o['t'] - e['t']) <= 40 and abs(o['x'] - e['x']) <= 15 and np.sign(o['y']) == np.sign(e['y'])]
        if len(near) >= 4:
            e['score'] = 1.0
            e['reason'] += ' (같은 자리에 비슷한 기록이 많아 벤치나 관중일 수 있음)'
    explained = [g + d for g in GOALS for d in range(-1, 9)] + [k + d for k in KICKOFFS for d in range(-1, 9)]
    for w in whistle:
        if any(abs(w['t'] - s) <= 1 for s in explained):
            continue                                            # whistle for a goal or a kick-off: reference only
        events.append(dict(t=w['t'], src='whistle', score=2.0, kind='프리킥', w=(w['t'] - 1, w['t'] + 1), x=None, y=None,
                           reason=f"심판 휘슬 같은 소리(강도 {w['strength']:.0f})"))
    for f in flows:
        events.append(dict(t=(f['t0'] + f['t1']) / 2, src='flow', score=1.5, kind='중단', w=(f['t0'], f['t1']), x=None, y=None,
                           reason=f"선수 대부분이 {f['t1'] - f['t0']:.0f}초 동안 느리게 움직임(경기 끊김)"))
    for b in balls:
        kind = {'corner': '코너킥', 'goalline': '골킥', 'touch': '스로인'}[b['zone']]
        events.append(dict(t=(b['t0'] + b['t1']) / 2, src='ball', score=3.0, kind=kind, w=(b['t0'], b['t1']), x=b['x'], y=b['y'],
                           reason=f"공 추적 클립 {b['clip']}에서 공이 선 근처({b['x']:.0f}, {b['y']:.0f} m)에 멈춤"))

    events.sort(key=lambda e: e['t'])
    clusters, cur = [], []
    for e in events:
        if cur and e['t'] - cur[-1]['t'] > 8:
            clusters.append(cur)
            cur = []
        cur.append(e)
    if cur:
        clusters.append(cur)
    candidates = []
    for c in clusters:
        by_src = {}
        for e in c:
            by_src[e['src']] = max(by_src.get(e['src'], 0), e['score'])
        score = sum(by_src.values())
        if score < 2.0:
            continue
        srcs = set(by_src)
        pos_kinds = [e['kind'] for e in sorted(c, key=lambda e: -e['score']) if e['src'] in ('ball', 'corner', 'touch', 'goalarea')]
        if 'corner' in srcs or ('ball' in srcs and '코너킥' in pos_kinds):
            kind = '코너킥'
        elif pos_kinds and 'whistle' in srcs and pos_kinds[0] == '스로인':
            kind = '스로인 또는 프리킥'
        elif pos_kinds:
            kind = pos_kinds[0]
        elif 'whistle' in srcs:
            kind = '프리킥 또는 파울로 멈춤'
        else:
            kind = '경기 멈춤(종류 모름)'
        if kind == '골킥' and len(srcs) == 1:                  # a goal-area stand alone is just a keeper idling
            continue
        t = float(np.mean([e['t'] for e in c if e['score'] >= max(by_src.values())]) if False else np.mean([e['t'] for e in c]))
        w0, w1 = min(e['w'][0] for e in c), max(e['w'][1] for e in c)
        covered = not any(a <= t < b for a, b in UNCOVERED)
        reasons = [e['reason'] for e in sorted(c, key=lambda e: -e['score'])]
        if not covered:
            reasons.append('이 구간(카메라 2번 장면)은 선수 위치 기록이 없어 휘슬만 단서입니다')
        confidence = '높음' if score >= 4.5 else ('중간' if score >= 3.0 else '낮음')
        candidates.append(dict(time_s=round(t, 1), time=mmss(t), window=[round(w0, 1), round(w1, 1)], window_text=f'{mmss(w0)}~{mmss(w1)}',
                               kind_guess=kind, confidence=confidence, score=round(score, 1), reasons=reasons[:4],
                               evidence=sorted(srcs), position_available=covered))
    near_goal = lambda t: any(0 <= t - g <= 60 for g in GOALS)
    for i, c in enumerate(candidates, 1):
        c['id'] = f's{i:03d}'
        c['within_60s_after_goal'] = near_goal(c['time_s'])
    reference = dict(
        kickoff_formation_runs={n: [[round(a, 1), round(b, 1)] for a, b in r] for n, r in kicks.items()},
        goals=GOALS, kickoffs=KICKOFFS, whistles=[round(w['t']) for w in whistle], evidence_counts=dict(
            standing_corner=sum(e['zone'] == 'corner' for e in positions), standing_touch=sum(e['zone'] == 'touch' for e in positions),
            standing_goalarea=sum(e['zone'] == 'goalarea' for e in positions), flow_breaks=len(flows), whistles=len(whistle),
            ball_rest_events=len(balls), ball_clips=ball_clips))
    return candidates, reference


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', default=str(WORK / 'set-piece-candidates-20261117'))
    parser.add_argument('--no-audio', action='store_true')
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    candidates, reference = build(args)
    note = ('추정 후보입니다. 공이 전 구간에 없어 공을 직접 보지 못했고, 정답 라벨이 없어 정밀도와 재현율을 알 수 없습니다. '
            '사용자님이 영상 시각에서 맞음 또는 아님만 판정하면 됩니다.')
    (out / 'candidates.json').write_text(json.dumps(dict(note=note, video='work/own-match-merged-20261111/match_from_17min.mp4', count=len(candidates), candidates=candidates),
                                                       ensure_ascii=False, indent=1), encoding='utf-8')
    (out / 'reference.json').write_text(json.dumps(reference, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f'{len(candidates)} candidates written to {out}')


if __name__ == '__main__':
    main()
