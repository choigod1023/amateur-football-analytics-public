"""Read-only raw-detection audit around a suspect interpolated run; never assigns identities."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.track_stitch import _centre, _height


def nearby(box, candidates, maximum_heights=2.0):
    result = []
    for item in candidates:
        distance = math.dist(_centre(box), _centre(item['box'])) / _height(box)
        if distance <= maximum_heights:
            result.append({**item, 'distance_body_heights': round(distance, 4)})
    return sorted(result, key=lambda r: r['distance_body_heights'])


def audit(work):
    track_file = work / 'evidence-policy-eval-20261113/h2_ov3.json'
    cache_file = work / 'detection-cache-20261112/half2_cam3_xn/chunk_02040.npz'
    hashes = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (track_file, cache_file)}
    data = json.loads(track_file.read_text(encoding='utf-8'))
    raw = np.load(cache_file)
    frames = []
    for row in data['tracks']['5869']:
        time = data['first_second'] + row['frame'] / data['fps']
        if not 2088.6 <= time <= 2089.8:
            continue
        index = round((time-float(raw['start']))*float(raw['fps']))
        mask = raw['frames'] == index
        detections = [{'box': [float(v) for v in box], 'score': float(score)}
                      for box, score in zip(raw['boxes'][mask], raw['scores'][mask]) if score >= .1]
        observed = [{'id': tid, 'team': r['team'], 'box': r['box']}
                    for tid, rows in data['tracks'].items() for r in rows
                    if r['frame'] == row['frame'] and not any(r.get(k) for k in ('interpolated', 'estimated', 'predicted'))]
        frames.append({'time': time, 'query_box': row['box'], 'query_is_interpolated': bool(row.get('interpolated')),
                       'raw_nearby': nearby(row['box'], detections), 'observed_tracks_nearby': nearby(row['box'], observed)})
    return {'track': '5869', 'frames': frames, 'raw_confidence_min': .1,
            'frames_with_raw_detection_within_half_body_height': sum(any(r['distance_body_heights'] <= .5 for r in f['raw_nearby']) for f in frames),
            'query_is_ground_truth': False, 'input_sha256': hashes,
            'inputs_unchanged': all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == sha for p, sha in hashes.items()),
            'visual_review': {'source': 'assistant visual audit, not human ground truth',
                'frames': [2088.2,2088.8,2089.4,2090.0],
                'finding': 'The dark-shirt person remains left while the interpolated path heads right toward a different fluorescent-shirt person. The observed endpoint at 2090.0 appears to enclose that fluorescent player.',
                'conclusion': 'Suspected within-track identity switch and synthetic crossing, not a supported missing run. Do not restore interpolation as an observed trajectory.'},
            'limitations': ['Proximity to an interpolated box does not establish identity.',
                            'Raw detections were cached earlier; no detector has been retrained or rerun.',
                            'New frame-scoped human identity evidence is required to confirm the visual hypothesis.']}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('work', type=Path)
    p.add_argument('output', type=Path)
    args = p.parse_args()
    result = audit(args.work)
    with args.output.open('x', encoding='utf-8') as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
    print('raw_hits_within_half_body_height', result['frames_with_raw_detection_within_half_body_height'], 'of', len(result['frames']))


if __name__ == '__main__':
    main()
