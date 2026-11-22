"""Compare landmark-based projection methods on held-out field marks.

No player or GNSS data is used; this experiment does not auto-detect marks or
enable calibration. Inputs are the original SoccerTrack public keypoint JSON.
"""
import argparse, ast, json, sys
from pathlib import Path
import cv2
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.main import project

def load(path):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    pairs = []
    for key, value in data.items():
        target = ast.literal_eval(key)
        pairs.append((np.asarray(value, dtype=float), np.asarray(target, dtype=float)))
    return pairs

def perspective(p, src, dst):
    matrix, _ = cv2.findHomography(src.astype(np.float64), dst.astype(np.float64), 0)
    if matrix is None: return None
    q = matrix @ np.array([*p, 1.])
    return None if abs(q[2]) < 1e-10 else q[:2]/q[2]

def triangles(src, width=6500, height=1000):
    sub = cv2.Subdiv2D((0, 0, width, height))
    for p in src: sub.insert((float(p[0]), float(p[1])))
    result = []
    for triangle in sub.getTriangleList().reshape(-1, 3, 2):
        idx = [int(np.argmin(np.linalg.norm(src - p, axis=1))) for p in triangle]
        if len(set(idx)) == 3 and all(np.linalg.norm(src[i]-p) < .1 for i,p in zip(idx, triangle)):
            result.append(idx)
    return result

def piecewise(p, src, dst):
    for idx in triangles(src):
        pts = src[idx]
        matrix = np.vstack([pts.T, np.ones(3)])
        if abs(np.linalg.det(matrix)) < 1e-8: continue
        weights = np.linalg.solve(matrix, np.array([*p,1.]))
        if np.all(weights >= -1e-8): return weights @ dst[idx]
    return None

def summary(errors, total):
    return {'eligible':total, 'returned':len(errors), 'median_m':round(float(np.median(errors)),3) if errors else None,
            'p90_m':round(float(np.percentile(errors,90)),3) if errors else None,
            'max_m':round(float(np.max(errors)),3) if errors else None}

def evaluate(pairs):
    corners = {(0.,0.),(0.,68.),(105.,0.),(105.,68.)}
    anchors = [pair for pair in pairs if tuple(pair[1]) in corners]
    if len(anchors)!=4: raise ValueError('Expected all four field corner labels')
    heldout = [pair for pair in pairs if tuple(pair[1]) not in corners]
    anchor_x, anchor_y = np.array([a for a,b in anchors]), np.array([b for a,b in anchors])
    errors = {'four_corners':[], 'runtime_guarded_four_corners':[], 'all_other_landmarks':[], 'piecewise_all_other':[]}
    cal = make_candidate(pairs)
    # Evaluation only: the emitted candidate remains unvalidated.
    evaluation_cal = {**cal, 'validated':True}
    for p, target in heldout:
        training = [(a,b) for a,b in pairs if not np.array_equal(a,p)]
        src,dst = np.array([a for a,b in training]), np.array([b for a,b in training])
        x,y = project(p, evaluation_cal)
        guarded = None if x is None or y is None else np.array([x*105,y*68])
        for name, prediction in [('four_corners', perspective(p, anchor_x,anchor_y)), ('runtime_guarded_four_corners',guarded), ('all_other_landmarks', perspective(p,src,dst)), ('piecewise_all_other',piecewise(p,src,dst))]:
            if prediction is not None and np.isfinite(prediction).all(): errors[name].append(float(np.linalg.norm(prediction-target)))
    return {name:summary(vals,len(heldout)) for name,vals in errors.items()}

def make_candidate(pairs):
    by_field={tuple(field):image for image,field in pairs}
    corners=[(0.,0.),(105.,0.),(105.,68.),(0.,68.)]
    if not all(c in by_field for c in corners): raise ValueError('Missing corner')
    return {'validated':False,'image_size_px':[6500,1000], 'field_size_m':[105.,68.],
            'image_points':[by_field[c].tolist() for c in corners], 'field_points_m':[list(c) for c in corners]}

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('landmark_json');parser.add_argument('--base',help='existing local config (optional)');parser.add_argument('--output',help='new candidate config, never overwritten');args=parser.parse_args()
    pairs=load(args.landmark_json)
    if bool(args.base) != bool(args.output): parser.error('--base and --output must be specified together')
    if args.base:
        base=json.loads(Path(args.base).read_text(encoding='utf-8-sig'))
        base['calibration']=make_candidate(pairs)
        with Path(args.output).open('x',encoding='utf-8') as out:json.dump(base,out,ensure_ascii=False,indent=2)
    print(json.dumps(evaluate(pairs),ensure_ascii=False,indent=2))
