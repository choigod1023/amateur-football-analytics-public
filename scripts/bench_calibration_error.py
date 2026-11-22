"""How many metres can a position be off because of the pitch calibration? (research, read only, no video, no GPU)

python scripts/bench_calibration_error.py <calibrations.json> [--runs 400] [--output result.json]

For each camera of calibrations.json (landmark points a person clicked in the reference photo, fitted by app/pitch_map.py) it reports:
  * in-sample error: the distance in metres between the landmark and the fitted position of its click (what pitch_map.fit already prints as rms);
  * leave-one-out error: refit without one landmark and project the click of that landmark; the distance to the true landmark is the error on a point the fit did not use
    (the honest number; landmarks that are the only one of their kind in a region give large values and that is real information);
  * click-noise error: the clicks are moved by random noise of the size of the in-sample error (in the image plane) and the fit is repeated; per zone of the pitch
    (near/far touchline third x left/centre/right) the median and 90th percentile of how far a position moves;
  * pitch-size error: the length and width of the pitch are estimates (pitch_dimensions_are_estimates in the file); the fit is redone with the length and the width changed by
    +-3 m and +-1.5 m and the change of the distance between two players 30 m apart on the pitch is reported.
The result does NOT include the lens (no distortion model), the person's feet being off the ground plane, the camera moving, or the clicks being biased the same way for every point.
It is the part of the position error that the calibration alone explains.
"""
import argparse, json, math, random, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np  # noqa: E402
from app import pitch_map as pm  # noqa: E402

ZONES = [(a, b) for a in ('near', 'far') for b in ('left', 'centre', 'right')]


def pairs_of(record, pitch):
    known = pm.landmarks(pitch)
    return [(p['x'], p['y'], *known[p['landmark']], p['landmark']) for p in record['points'] if p.get('landmark') in known]


def homography(pairs):
    h = pm.solve_homography([p[:4] for p in pairs])
    if h is None:
        return None
    if sum(h[2, 0] * u + h[2, 1] * v + h[2, 2] for u, v, _, _, *_ in pairs) < 0:
        h = -h
    return h


def grid(pitch):
    half, wide = pitch['length'] / 2, pitch['width'] / 2
    points = []
    for gx in np.linspace(-half + 5, half - 5, 9):
        for gy in np.linspace(-wide + 3, wide - 3, 5):
            points.append((float(gx), float(gy)))
    return points


def zone(x, y, pitch):
    side = 'near' if y > 0 else 'far'
    third = pitch['length'] / 6
    return side, ('left' if x < -third else 'right' if x > third else 'centre')


def to_pixels(h, x, y):
    inv = np.linalg.inv(h)
    w = inv[2, 0] * x + inv[2, 1] * y + inv[2, 2]
    return (inv[0, 0] * x + inv[0, 1] * y + inv[0, 2]) / w, (inv[1, 0] * x + inv[1, 1] * y + inv[1, 2]) / w


def percentile(values, q):
    values = sorted(values)
    return values[min(len(values) - 1, int(round(q * (len(values) - 1))))] if values else None


def one_camera(name, record, runs, seed=1):
    pitch = {**pm.DEFAULTS, **(record.get('pitch') or {})}
    pairs = pairs_of(record, pitch)
    h = homography(pairs)
    out = {'points': len(pairs), 'pitch': {k: pitch[k] for k in ('length', 'width')}}
    insample = {}
    for u, v, x, y, label in pairs:
        r = pm.apply(h, u, v)
        insample[label] = math.hypot(r[0] - x, r[1] - y)
    out['in_sample_m'] = {k: round(v, 2) for k, v in insample.items()}
    out['in_sample_rms_m'] = round(math.sqrt(sum(v * v for v in insample.values()) / len(insample)), 3)
    loo = {}
    for i, (u, v, x, y, label) in enumerate(pairs):
        rest = pairs[:i] + pairs[i + 1:]
        hh = homography(rest) if len(rest) >= 4 else None
        r = pm.apply(hh, u, v) if hh is not None else None
        loo[label] = round(math.hypot(r[0] - x, r[1] - y), 2) if r else None
    out['leave_one_out_m'] = loo
    values = [v for v in loo.values() if v is not None]
    out['leave_one_out_median_m'] = round(percentile(values, 0.5), 2) if values else None
    out['leave_one_out_max_m'] = round(max(values), 2) if values else None
    # click noise: the in-sample residual of every click in the image plane, then a random shift of that size
    residual_px = []
    for u, v, x, y, label in pairs:
        pu, pv = to_pixels(h, x, y)
        residual_px.append(math.hypot(pu - u, pv - v))
    sigma = math.sqrt(sum(r * r for r in residual_px) / len(residual_px) / 2)
    out['click_noise_sigma_normalized'] = round(sigma, 5)
    rng = random.Random(seed)
    points = grid(pitch)
    moves = {z: [] for z in ZONES}
    for _ in range(runs):
        noisy = [(u + rng.gauss(0, sigma), v + rng.gauss(0, sigma), x, y, label) for u, v, x, y, label in pairs]
        hn = homography(noisy)
        if hn is None:
            continue
        for x, y in points:
            pu, pv = to_pixels(h, x, y)
            r = pm.apply(hn, pu, pv)
            if r:
                moves[zone(x, y, pitch)].append(math.hypot(r[0] - x, r[1] - y))
    out['click_noise_m'] = {f'{a}/{b}': {'median': round(percentile(v, 0.5), 2), 'p90': round(percentile(v, 0.9), 2), 'n': len(v)} for (a, b), v in moves.items() if v}
    # pitch size error: refit with a different pitch size, how much does the distance between two players 30 m apart change
    sizes = {}
    for dl, dw in ((3, 0), (-3, 0), (0, 3), (0, -3), (1.5, 1.5), (-1.5, -1.5)):
        altered = {**pitch, 'length': pitch['length'] + dl, 'width': pitch['width'] + dw}
        ha = homography(pairs_of(record, altered))
        if ha is None:
            continue
        changes = []
        for x, y in points:
            for dx, dy in ((30, 0), (0, 30), (21, 21)):
                x2, y2 = x + dx, y + dy
                if abs(x2) > pitch['length'] / 2 or abs(y2) > pitch['width'] / 2:
                    continue
                p1, p2 = to_pixels(h, x, y), to_pixels(h, x2, y2)
                a1, a2 = pm.apply(ha, *p1), pm.apply(ha, *p2)
                if a1 and a2:
                    changes.append(abs(math.hypot(a1[0] - a2[0], a1[1] - a2[1]) - math.hypot(dx, dy)))
        sizes[f'length{dl:+}_width{dw:+}'] = {'median_change_of_30m_m': round(percentile(changes, 0.5), 2), 'p90': round(percentile(changes, 0.9), 2), 'n': len(changes)}
    out['pitch_size_error'] = sizes
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('calibrations', type=Path); p.add_argument('--runs', type=int, default=400); p.add_argument('--output', type=Path)
    args = p.parse_args()
    data = json.loads(args.calibrations.read_text(encoding='utf-8'))
    result = {name: one_camera(name, record, args.runs) for name, record in data.items()}
    for name, r in result.items():
        print(f"== {name}: {r['points']} landmarks, pitch {r['pitch']}, in-sample rms {r['in_sample_rms_m']} m, leave-one-out median {r['leave_one_out_median_m']} m max {r['leave_one_out_max_m']} m")
        print('   in-sample', r['in_sample_m'])
        print('   leave-one-out', r['leave_one_out_m'])
        print('   click noise sigma (normalized)', r['click_noise_sigma_normalized'])
        for z, v in r['click_noise_m'].items():
            print(f'   noise {z:14s} median {v["median"]} m p90 {v["p90"]} m (n={v["n"]})')
        for z, v in r['pitch_size_error'].items():
            print(f'   pitch {z:22s} change of a 30 m distance: median {v["median_change_of_30m_m"]} m p90 {v["p90"]} m (n={v["n"]})')
    if args.output:
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding='utf-8')


if __name__ == '__main__':
    main()
