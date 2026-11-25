import sys, json, collections, time
sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.dirname(__import__('os').path.abspath(__file__))))
from pathlib import Path
import cv2, numpy as np
from app.training_labels import TrainingLabels
store = Path(__import__('os').environ['FOOTBALL_REVIEW_DIR'])
tl = TrainingLabels(store)
cal = json.load(open(store/'calibration'/'calibrations.json', encoding='utf-8'))
scenes = [s for s in tl.scene_queue() if s['camera']]
orb = cv2.ORB_create(nfeatures=1500)
bf = cv2.BFMatcher(cv2.NORM_HAMMING)
def prep(token):
    img = cv2.imread(str(store/'pending'/(token+'.jpg')))
    small = cv2.resize(img, (960, int(img.shape[0]*960/img.shape[1])))
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    # ignore the lower 12% and the players are small; use whole frame but mask nothing
    kp, de = orb.detectAndCompute(gray, None)
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    h = cv2.calcHist([hsv], [0, 1], None, [18, 8], [0, 180, 0, 256]); cv2.normalize(h, h, 1, 0, cv2.NORM_L1)
    # coarse layout signature: 8x6 grid mean gray
    g = cv2.resize(gray, (16, 9), interpolation=cv2.INTER_AREA).astype(np.float32).ravel()
    return kp, de, h.ravel(), g
t0 = time.time()
data = {s['token']: prep(s['token']) for s in scenes}
print('prep', len(data), 'frames', round(time.time()-t0, 1), 's')
def matches(a, b):
    if a[1] is None or b[1] is None: return 0
    m = bf.knnMatch(a[1], b[1], k=2)
    good = [p[0] for p in m if len(p) == 2 and p[0].distance < .75*p[1].distance]
    if len(good) < 8: return len(good)
    src = np.float32([a[0][g.queryIdx].pt for g in good]).reshape(-1, 1, 2)
    dst = np.float32([b[0][g.trainIdx].pt for g in good]).reshape(-1, 1, 2)
    M, inl = cv2.findHomography(src, dst, cv2.RANSAC, 4.0)
    return int(inl.sum()) if inl is not None else 0
# references: the calibration reference frames for cam1/cam3; cam2 reference = first cam2 scene
refs = {}
for cam in ('cam1', 'cam3'):
    tok = cal[cam]['ref_token']; refs[cam] = [tok]
cam2 = [s for s in scenes if s['camera'] == 'cam2']
refs['cam2'] = [cam2[0]['token']]
print({k: v for k, v in refs.items()})
res = []
t0 = time.time()
conf = collections.Counter(); conf_h = collections.Counter(); conf_g = collections.Counter()
for s in scenes:
    tok = s['token']; d = data[tok]
    inl = {}; hd = {}; gd = {}
    for cam, toks in refs.items():
        r = data[toks[0]] if toks[0] in data else prep(toks[0])
        if tok == toks[0]: inl[cam] = None; continue
        inl[cam] = matches(r, d)
        hd[cam] = float(cv2.compareHist(r[2].astype(np.float32), d[2].astype(np.float32), cv2.HISTCMP_BHATTACHARYYA))
        gd[cam] = float(np.abs(r[3]-d[3]).mean())
    valid = {k: v for k, v in inl.items() if v is not None}
    pred = max(valid, key=valid.get) if valid and max(valid.values()) >= 15 else 'unknown'
    conf[(s['camera'], pred)] += 1
    vh = {k: v for k, v in hd.items()}
    predh = min(vh, key=vh.get) if vh else 'ref'
    conf_h[(s['camera'], predh)] += 1
    vg = {k: v for k, v in gd.items()}
    predg = min(vg, key=vg.get) if vg else 'ref'
    conf_g[(s['camera'], predg)] += 1
print('match time per scene ms', round((time.time()-t0)/len(scenes)*1000, 1))
print('ORB-homography inliers (>=15) :', dict(conf))
print('color histogram nearest       :', dict(conf_h))
print('gray 16x9 layout nearest      :', dict(conf_g))
print('--- errors')
for s in scenes:
    tok = s['token']; d = data[tok]
    inl = {}
    for cam, toks in refs.items():
        if tok == toks[0]: continue
        inl[cam] = matches(data[toks[0]], d)
    pred = max(inl, key=inl.get) if inl else None
    if pred != s['camera'] and tok not in [v[0] for v in refs.values()]:
        print(s['camera'], 'pred', pred, 'clip_time', s['clip_time'], 'split', s['split'], inl)
# margin: how separated are correct ones
import statistics
marg = []
for s in scenes:
    tok = s['token']; d = data[tok]
    inl = {cam: matches(data[t[0]], d) for cam, t in refs.items() if tok != t[0]}
    own = inl.get(s['camera'])
    others = [v for k, v in inl.items() if k != s['camera']]
    if own is not None and others: marg.append((s['camera'], own, max(others)))
for cam in ('cam1', 'cam2', 'cam3'):
    own = [m[1] for m in marg if m[0] == cam]; oth = [m[2] for m in marg if m[0] == cam]
    print(cam, 'own-ref inliers median', statistics.median(own), 'min', min(own), '| best-other median', statistics.median(oth), 'max', max(oth))
