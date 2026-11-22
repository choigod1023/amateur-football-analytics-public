"""Cut context crops around every box a human judged in the person-check sessions, for testing outside verifier models (research only, read only).

python scripts/dump_verifier_crops.py <video> <output folder>

For each judged box (work/person-check1-answers.json, person-check2-answers.json) two PNG files are written, so a second Python environment without OpenCV can score them:
  <n>_ctx.png   a context window of CONTEXT px around the box centre (clipped to the frame), enlarged by SCALE; the box inside it is stored in manifest.json as 'box_ctx'.
  <n>_tight.png the box with 50 % padding on every side, enlarged to at least 224 px on the long side.
manifest.json keeps: n, file number, time, camera, label (the human judgement), score, found_by, box (frame pixels), box_ctx, ctx_origin, scale.
The human labels stay in the manifest only to score the verifiers afterwards; the verifiers never see them.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT.parents[1] / 'work'
ANSWERS = [WORK / 'person-check1-answers.json', WORK / 'person-check2-answers.json']
CONTEXT = 160
SCALE = 4


def cut_crops(image, box):
    """-> (context crop, tight crop, box inside the context crop, context origin) of one box in a frame (OpenCV is imported by the caller's environment)."""
    import cv2
    height, width = image.shape[:2]
    x1, y1, x2, y2 = box
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    ox, oy = int(max(0, min(width - CONTEXT, cx - CONTEXT / 2))), int(max(0, min(height - CONTEXT, cy - CONTEXT / 2)))
    ctx = cv2.resize(image[oy:oy + CONTEXT, ox:ox + CONTEXT], None, fx=SCALE, fy=SCALE, interpolation=cv2.INTER_CUBIC)
    w, h = x2 - x1, y2 - y1
    tx1, ty1, tx2, ty2 = int(max(0, x1 - w / 2)), int(max(0, y1 - h / 2)), int(min(width, x2 + w / 2)), int(min(height, y2 + h / 2))
    tight = image[ty1:ty2, tx1:tx2]
    factor = max(1.0, 224 / max(tight.shape[:2]))
    tight = cv2.resize(tight, None, fx=factor, fy=factor, interpolation=cv2.INTER_CUBIC)
    return ctx, tight, [(x1 - ox) * SCALE, (y1 - oy) * SCALE, (x2 - ox) * SCALE, (y2 - oy) * SCALE], [ox, oy]


def main():
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    import cv2
    video, out = sys.argv[1], Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(video)
    manifest, cache = [], {}
    for number, path in enumerate(ANSWERS, start=1):
        for r in json.loads(path.read_text(encoding='utf-8')):
            key = (r['time'])
            if key not in cache:
                cap.set(cv2.CAP_PROP_POS_MSEC, r['time'] * 1000)
                ok, image = cap.read()
                cache = {key: image if ok else None}
            image = cache[key]
            if image is None:
                continue
            ctx, tight, box_ctx, origin = cut_crops(image, r['box'])
            n = len(manifest)
            cv2.imwrite(str(out / f'{n:03d}_ctx.png'), ctx)
            cv2.imwrite(str(out / f'{n:03d}_tight.png'), tight)
            manifest.append({'n': n, 'file': number, 'time': r['time'], 'camera': r['camera'], 'label': r['label'], 'score': r['score'], 'found_by': r['found_by'], 'box': r['box'],
                             'box_ctx': box_ctx, 'ctx_origin': origin, 'scale': SCALE})
    (out / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    print(len(manifest), 'boxes,', sum(1 for m in manifest if m['label'] == 'ok'), 'judged person')


if __name__ == '__main__':
    main()
