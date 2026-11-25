exec(open(__import__('os').path.join(__import__('os').path.dirname(__import__('os').path.abspath(__file__)), 'research_camera_view_classifier.py')).read().split("# references:")[0])
import statistics
refs = {'cam1': cal['cam1']['ref_token'], 'cam3': cal['cam3']['ref_token']}
cam2 = [s for s in scenes if s['camera'] == 'cam2']; refs['cam2'] = cam2[0]['token']
def affine(a, b):
    m = bf.knnMatch(a[1], b[1], k=2)
    good = [p[0] for p in m if len(p) == 2 and p[0].distance < .75*p[1].distance]
    if len(good) < 12: return None
    src = np.float32([a[0][g.queryIdx].pt for g in good]).reshape(-1, 1, 2)
    dst = np.float32([b[0][g.trainIdx].pt for g in good]).reshape(-1, 1, 2)
    M, inl = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC, ransacReprojThreshold=2.0, maxIters=2000, confidence=.99)
    if M is None: return None
    sel = inl.ravel().astype(bool)
    if sel.sum() < 12: return None
    proj = cv2.transform(src[sel], M).reshape(-1, 2)
    disp = np.linalg.norm(proj - src[sel].reshape(-1, 2), axis=1)
    return M, float(np.percentile(disp, 90)), int(sel.sum())
rows = []
for s in sorted([x for x in scenes if x['clip_time'] is not None], key=lambda s: s['clip_time']):
    cam = s['camera']
    if s['token'] == refs[cam]: continue
    r = affine(data[refs[cam]], data[s['token']])
    if r is None: rows.append((s['clip_time'], cam, None)); continue
    M, p90, n = r
    rows.append((s['clip_time'], cam, (M[0, 2], M[1, 2], float(np.hypot(M[0, 0], M[1, 0])), p90, n, s['bg'])))
for cam in ('cam1', 'cam2', 'cam3'):
    rr = [r for r in rows if r[1] == cam]
    ok = [r for r in rr if r[2]]
    p90s = [r[2][3] for r in ok]
    print(cam, 'scenes', len(rr), 'fit ok', len(ok), 'p90 displacement px(960w): median', round(statistics.median(p90s), 2), 'max', round(max(p90s), 2),
          '| over guard limit 2.88px:', sum(1 for v in p90s if v > 2.88))
    tx = [r[2][0] for r in ok]; ty = [r[2][1] for r in ok]; sc = [r[2][2] for r in ok]
    print('   tx range', round(min(tx), 1), round(max(tx), 1), 'ty range', round(min(ty), 1), round(max(ty), 1), 'scale range', round(min(sc), 4), round(max(sc), 4))
for cam in ('cam1', 'cam3'):
    print(cam, 'tx,ty by time:', [(round(r[0]), round(r[2][0],1), round(r[2][1],1)) for r in rows if r[1] == cam and r[2]][::2])
bgs = [s['bg'] for s in scenes if s['bg']]
ident = sum(1 for b in bgs if abs(b[0]-1) < 1e-6 and abs(b[1]) < 1e-6 and abs(b[2]) < 1e-6 and abs(b[3]) < 1e-6)
print('stored bg_to_ref: total', len(bgs), 'identity', ident)
