"""How many of the boxes a human confirmed does a detector find? (research benchmark, read only)

python scripts/bench_human_boxes.py <review store> <video> <confidences> <weights> [<weights> ...] [--train-times times.json ...]

Test boxes:
  * the boxes the user drew by hand on the training scenes (origin human_drawn, 34 of them in 14 scenes; 7 lie in scenes of the evaluation split),
  * the boxes the user judged "a person" in the person-check sessions (work/person-check*-answers.json, label ok; the frame is read again from the video by its time).
A box counts as found when a detection overlaps it with IoU >= 0.3 (same rule as scripts/bench_drawn_boxes.py), detection is the 384 px tile detector of the tracker.
Caveats printed with the result: the person-check boxes were chosen because ONE of two detectors (A = ft_n2, B = yolo11x) found them with a score of 0.25 to 0.6 and the other did not,
so the detector that found them is favoured on its own boxes; they never went into the training sets of the detectors (the person-check judge used them, a different model).
--train-times: JSON/JSONL files with rows holding a video second "time" (frames used to build training data). The benchmark prints how close the nearest training frame is to each test frame.
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
import cv2  # noqa: E402
import track_review_clip as tracker  # noqa: E402
from app.training_labels import TrainingLabels  # noqa: E402
from build_pseudo_tiles import iou  # noqa: E402

WORK = ROOT.parents[1] / 'work'
ANSWERS = [WORK / 'person-check1-answers.json', WORK / 'person-check2-answers.json']


def read_times(paths):
    found = []
    for p in paths:
        text = Path(p).read_text(encoding='utf-8')
        rows = json.loads(text) if str(p).endswith('.json') else [json.loads(x) for x in text.splitlines() if x.strip()]
        found += [float(r['time']) for r in rows if isinstance(r, dict) and r.get('time') is not None]
    return found


def camera_key(name):
    return name if name in tracker.PITCH_TOP else 'cam3'


def build_cases(store, video):
    """-> list of dict(image, boxes px, group, time)"""
    cases = []
    tl = TrainingLabels(store)
    for scene in tl.scene_queue():
        drawn = [l['bbox'] for l in tl.scene_labels(scene['token']) if l.get('origin') == 'human_drawn']
        if not drawn:
            continue
        image = cv2.imread(str(Path(store) / 'pending' / (scene['token'] + '.jpg')))
        h, w = image.shape[:2]
        cases.append({'image': image, 'camera': camera_key(scene['camera']), 'boxes': [[b[0] * w, b[1] * h, b[2] * w, b[3] * h] for b in drawn],
                      'group': 'drawn/' + str(scene['split']), 'time': scene['clip_time'], 'tags': ['drawn'] * len(drawn)})
    cap = cv2.VideoCapture(str(video))
    by_time = defaultdict(list)
    for number, path in enumerate(ANSWERS, start=1):
        for r in json.loads(path.read_text(encoding='utf-8')):
            if r.get('label') == 'ok':
                by_time[(number, r['time'], r['camera'])].append(r)
    for (number, t, camera), rows in sorted(by_time.items()):
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, image = cap.read()
        if not ok:
            continue
        cases.append({'image': image, 'camera': camera_key(camera), 'boxes': [r['box'] for r in rows], 'group': f'check{number}', 'time': t, 'tags': [r['found_by'] for r in rows]})
    return cases


def main():
    args = [a for a in sys.argv[1:]]
    train_times = []
    if '--train-times' in args:
        i = args.index('--train-times')
        train_times = read_times(args[i + 1:])
        args = args[:i]
    if len(args) < 4:
        raise SystemExit(__doc__)
    store, video, confidences, weights = args[0], args[1], [float(v) for v in args[2].split(',')], args[3:]
    from ultralytics import YOLO
    cases = build_cases(store, video)
    total = sum(len(c['boxes']) for c in cases)
    print(f'{len(cases)} frames, {total} human-confirmed boxes (drawn {sum(len(c["boxes"]) for c in cases if c["group"].startswith("drawn"))}, '
          f'person-check ok {sum(len(c["boxes"]) for c in cases if c["group"].startswith("check"))})')
    if train_times:
        near = [min(abs(c['time'] - t) for t in train_times) for c in cases if c['time'] is not None]
        print(f'training-frame check: {len(train_times)} training frames; nearest one to a test frame: min {min(near):.1f} s, test frames closer than 5 s to a training frame: {sum(1 for d in near if d < 5)} of {len(near)}')
    for w in weights:
        model = YOLO(w)
        for conf in confidences:
            found = defaultdict(lambda: [0, 0])
            for c in cases:
                dets = tracker.detect(model, c['image'], c['camera'], 0, conf)
                for box, tag in zip(c['boxes'], c['tags']):
                    hit = any(iou(box, d) >= 0.3 for d in dets)
                    for key in ('all', c['group'], 'tag/' + tag if c['group'].startswith('check') else None):
                        if key:
                            found[key][0] += hit
                            found[key][1] += 1
            line = ' | '.join(f'{k} {v[0]}/{v[1]}' for k, v in sorted(found.items(), key=lambda kv: (kv[0] != 'all', kv[0])))
            print(f'{Path(w).parent.name + "/" + Path(w).name:40s} conf {conf}: {line}', flush=True)


if __name__ == '__main__':
    main()
