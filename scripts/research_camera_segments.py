exec(open(__import__('os').path.join(__import__('os').path.dirname(__import__('os').path.abspath(__file__)), 'research_camera_view_classifier.py')).read().split("# references:")[0])
import time
refs = {'cam1': cal['cam1']['ref_token'], 'cam3': cal['cam3']['ref_token']}
cam2 = [s for s in scenes if s['camera'] == 'cam2']; refs['cam2'] = cam2[0]['token']
video = __import__('os').environ['FOOTBALL_MATCH_VIDEO']   # the merged match video
cap = cv2.VideoCapture(video)
fps = cap.get(cv2.CAP_PROP_FPS); total = cap.get(cv2.CAP_PROP_FRAME_COUNT); dur = total / fps
print('duration s', round(dur, 1))
def frame_sig(img):
    small = cv2.resize(img, (960, int(img.shape[0]*960/img.shape[1])))
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    kp, de = orb.detectAndCompute(gray, None)
    return kp, de
def classify(img):
    sig = frame_sig(img)
    sc = {cam: matches(data[t], (sig[0], sig[1])) for cam, t in refs.items()}
    best = max(sc, key=sc.get)
    srt = sorted(sc.values())
    return best, sc, (srt[-1] - srt[-2])
t0 = time.time()
seq = []
t = 0.0
while t < dur - 1:
    cap.set(cv2.CAP_PROP_POS_MSEC, t*1000)
    ok, img = cap.read()
    if ok:
        best, sc, margin = classify(img)
        seq.append((t, best, margin, sc))
    t += 10.0
print('classified', len(seq), 'frames in', round(time.time()-t0), 's')
last = None
for t, best, margin, sc in seq:
    if best != last:
        print('start', round(t), best, sc); last = best
import collections
print(collections.Counter(b for _, b, _, _ in seq))
print('lowest margins', sorted((round(m), round(t), b) for t, b, m, _ in seq)[:6])
