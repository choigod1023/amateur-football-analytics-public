"""Score detectors on the held-out frames of one cross-validation fold of the person-check judgements (research benchmark, read only).

python scripts/bench_human_cv.py <video> <fold> <folds> <confidences> <weights> [<weights> ...]

Test frames = the judged frames of work/person-check1-answers.json and person-check2-answers.json whose five-minute block number modulo <folds> equals <fold>
(the frames scripts/build_human_tiles.py left out for that fold). For every model: found = judged-ok boxes found (IoU >= 0.3), false = judged-wrong boxes still reported,
dets = average detections per test frame (a model that only reports more of everything shows up here).
Caveat: the ok boxes were mostly found by the large model, which favours models taught by it; the same caveat applies to every model in the table.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
import cv2  # noqa: E402
import track_review_clip as tracker  # noqa: E402
from build_human_tiles import fold_of, judged_frames  # noqa: E402
from build_pseudo_tiles import iou  # noqa: E402


def main():
    if len(sys.argv) < 6:
        raise SystemExit(__doc__)
    video, fold, folds, confidences, weights = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), [float(v) for v in sys.argv[4].split(',')], sys.argv[5:]
    from ultralytics import YOLO
    cap = cv2.VideoCapture(video)
    cases = []
    for (number, t, camera), rows in sorted(judged_frames().items()):
        if fold >= 0 and fold_of(t, folds) != fold:
            continue
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, image = cap.read()
        if ok:
            cases.append({'image': image, 'camera': camera if camera in tracker.PITCH_TOP else 'cam3', 'ok': [r['box'] for r in rows if r['label'] == 'ok'],
                          'wrong': [r['box'] for r in rows if r['label'] == 'wrong']})
    n_ok, n_wrong = sum(len(c['ok']) for c in cases), sum(len(c['wrong']) for c in cases)
    print(f'fold {fold}/{folds}: {len(cases)} frames, {n_ok} judged-ok boxes, {n_wrong} judged-wrong boxes')
    for w in weights:
        model = YOLO(w)
        for conf in confidences:
            found = false = dets = 0
            for c in cases:
                d = tracker.detect(model, c['image'], c['camera'], 0, conf)
                dets += len(d)
                found += sum(any(iou(b, x) >= 0.3 for x in d) for b in c['ok'])
                false += sum(any(iou(b, x) >= 0.3 for x in d) for b in c['wrong'])
            print(f'{Path(w).parent.name + "/" + Path(w).name:42s} conf {conf}: found {found}/{n_ok}  false {false}/{n_wrong}  dets/frame {dets / max(1, len(cases)):.1f}', flush=True)


if __name__ == '__main__':
    main()
