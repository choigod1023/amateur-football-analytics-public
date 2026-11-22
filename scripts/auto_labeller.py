"""Automatic judge for boxes two person detectors disagree on ("AI chimp"). Research tool: its labels are never mixed with the human ones.

python scripts/auto_labeller.py evaluate --video match.mp4 --store <review store> --out work/auto-labels-20261116
    Cross-validates the judge on the boxes the user judged (work/person-check*-answers.json), over time blocks, and writes judge.json and evaluation.json.
python scripts/auto_labeller.py run --video match.mp4 --store <review store> --out work/auto-labels-20261116 --weights-a ft_n2.pt --weights-b yolo11x.pt [--frames 60]
    Takes new frames, finds the boxes the two detectors disagree on, judges them with judge.json, writes the accepted boxes as YOLO labels
    (origin 'auto_labeller', frames are only partly labelled) and puts the boxes that need a human on /alerts as the new session person-check3 (40 at most).

Rules kept here: the human label folders are only read; the alerts session is a new folder; no image leaves this computer; frames within 15 s of an evaluation scene
and the camera-2 part of the video (about 1495 s to 1735 s) are not used.
"""
import argparse
import json
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402

from app import auto_labeller as al  # noqa: E402
from app.camera_segments import camera_of  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT.parents[1] / 'work'
RESNET_WEIGHTS = WORK / 'role-transfer' / 'torch-cache' / 'checkpoints' / 'resnet18-f37072fd.pth'
ANSWERS = [WORK / 'person-check1-answers.json', WORK / 'person-check2-answers.json']


def eval_times(store):
    from app.training_labels import TrainingLabels
    return [s['clip_time'] for s in TrainingLabels(store).scene_queue() if s['split'] in ('eval', 'buffer_excluded') and s['clip_time'] is not None]


def avoid_file_times(args, files=None):
    """Video seconds of frames already used for judging (person-check sessions, earlier auto-labeller runs): no new frame within 5 s of them (15 s would leave too little video)."""
    found = []
    for path in (args.avoid_files if files is None else files) or []:
        data = json.loads(Path(path).read_text(encoding='utf-8')) if str(path).endswith('.json') else [json.loads(x) for x in Path(path).read_text(encoding='utf-8').splitlines() if x.strip()]
        found += [float(r['time']) for r in data if isinstance(r, dict) and r.get('time') is not None]
    return found


def extra_avoid_times(args):
    """Video seconds of the scenes that hold hand-drawn boxes (they are test material): no new frame within 15 s of them."""
    found = []
    if args.avoid_drawn:
        from app.training_labels import TrainingLabels
        tl = TrainingLabels(args.store)
        for sc in tl.scene_queue():
            if sc['clip_time'] is not None and any(l.get('origin') == 'human_drawn' for l in tl.scene_labels(sc['token'])):
                found.append(float(sc['clip_time']))
    return found


def read_frame(cv2, cap, t):
    cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
    ok, image = cap.read()
    return image if ok else None


class Embedder:
    """resnet18 average-pool features of a padded box crop (local weights only; none is downloaded)."""

    def __init__(self):
        import torch
        import torchvision
        self.torch = torch
        net = torchvision.models.resnet18()
        net.load_state_dict(torch.load(RESNET_WEIGHTS, map_location='cpu'))
        net.fc = torch.nn.Identity()
        self.net = net.eval()

    def __call__(self, cv2, image, box):
        crop = al._crop(image, box, pad=0.25)
        if crop.size == 0:
            return np.zeros(512)
        crop = cv2.resize(crop, (64, 128), interpolation=cv2.INTER_CUBIC)[:, :, ::-1].astype(np.float32) / 255.0
        crop = (crop - np.array([0.485, 0.456, 0.406], dtype=np.float32)) / np.array([0.229, 0.224, 0.225], dtype=np.float32)
        with self.torch.no_grad():
            out = self.net(self.torch.from_numpy(np.ascontiguousarray(crop.transpose(2, 0, 1)))[None])
        return out[0].numpy().astype(np.float64)


def pca_fit(x, k):
    mean = x.mean(axis=0)
    _, _, vt = np.linalg.svd(x - mean, full_matrices=False)
    return mean, vt[:k]


def load_answers():
    rows = []
    for number, path in enumerate(ANSWERS, start=1):
        for r in json.loads(path.read_text(encoding='utf-8')):
            if r.get('label') in ('ok', 'wrong'):
                rows.append({**r, 'check': number})
    return rows


def matrix(rows, names, cnn=None):
    cols = [[r['features'][n] for n in names] for r in rows]
    x = np.array(cols, dtype=float)
    return np.hstack([x, cnn]) if cnn is not None else x


def evaluate(args):
    import cv2
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rows = load_answers()
    avoid = eval_times(args.store)
    cap = cv2.VideoCapture(args.video)
    embed = Embedder() if RESNET_WEIGHTS.is_file() else None
    emb = []
    for r in rows:
        image = read_frame(cv2, cap, r['time'])
        r['features'] = al.box_features(cv2, image, r['box'], r['score'], r['found_by'])
        emb.append(embed(cv2, image, r['box']) if embed else None)
        r['near_eval'] = al.near_any(r['time'], avoid)
    total_judged = len(rows)
    kept = [i for i, r in enumerate(rows) if not r['near_eval']]
    rows = [rows[i] for i in kept]
    emb = [emb[i] for i in kept] if embed else None
    y = np.array([1.0 if r['label'] == 'ok' else 0.0 for r in rows])
    groups = al.time_groups([r['time'] for r in rows])
    print(f'{len(rows)} of {total_judged} judged boxes used (the rest lie within 15 s of an evaluation scene), {int(y.sum())} people, {len(set(groups))} time blocks of 120 s')
    cnn_dim = 6
    cnn_mean = cnn_vt = None
    cnn = None
    if embed:
        stack = np.array(emb)
        cnn_mean, cnn_vt = pca_fit(stack, cnn_dim)
        cnn = (stack - cnn_mean) @ cnn_vt.T
    sets = {'detector_only': ['is_b', 'score'], 'basic': al.BASE_FEATURES, 'image_only': [n for n in al.BASE_FEATURES if n not in ('is_b', 'score')]}
    configs = [(name, names, False) for name, names in sets.items()]
    if embed:
        configs += [('basic+cnn', al.BASE_FEATURES, True), ('cnn_only', [], True)]
    results = []
    for name, names, use_cnn in configs:
        x = matrix(rows, names, cnn if use_cnn else None) if (names or use_cnn) else None
        if names == [] and use_cnn:
            x = cnn
        for lam in (0.3, 1.0, 3.0, 10.0, 30.0):
            prob = al.oof_probabilities(x, y, groups, lam)
            nest = al.nested_evaluation(x, y, groups, lam)
            summary = al.summarise(nest['decision'], y)
            results.append({'features': name, 'lam': lam, 'auc': al.auc(prob, y), 'accuracy': float(((prob >= 0.5) == (y == 1)).mean()),
                            'nested_auc': al.auc(nest['prob'], y), **summary})
            print(f"{name:14s} lam {lam:5.1f} auc {results[-1]['auc']:.3f} acc {results[-1]['accuracy']:.3f} | three levels: accept {summary['accept_people']}/{summary['accept']}, "
                  f"reject {summary['reject_nonpeople']}/{summary['reject']}, ask {summary['ask']}", flush=True)
    base = (y == 1).mean()
    best = max((r for r in results if r['features'] != 'detector_only'), key=lambda r: r['auc'])
    base_detector = max((r for r in results if r['features'] == 'detector_only'), key=lambda r: r['auc'])
    print('share of people among judged boxes', round(float(base), 3))
    print('best with image features (chosen by out-of-fold AUC, so slightly optimistic):', best)
    # final judge: trained on all judged boxes with the best configuration, thresholds from the out-of-fold probabilities of the training set
    names = {'detector_only': sets['detector_only'], 'basic': sets['basic'], 'image_only': sets['image_only'], 'basic+cnn': sets['basic'], 'cnn_only': []}[best['features']]
    use_cnn = best['features'] in ('basic+cnn', 'cnn_only')
    x = matrix(rows, names, cnn if use_cnn else None) if names else cnn
    prob = al.oof_probabilities(x, y, groups, best['lam'])
    # the accept level is only kept when held-out boxes (nested evaluation) reach the 95 % target with at least 20 accepted boxes; stricter inner targets are tried in turn
    accept_trials = []
    target_used = None
    for target in (0.95, 0.98, 1.0):
        nest = al.nested_evaluation(x, y, groups, best['lam'], accept_target=target)
        summary = al.summarise(nest['decision'], y)
        trial = {'inner_target': target, **summary, 'held_out_accept_precision': (summary['accept_people'] / summary['accept']) if summary['accept'] else None,
                 'wilson_lower': al.wilson_lower(summary['accept_people'], summary['accept'])}
        accept_trials.append(trial)
        print('accept trial', trial, flush=True)
        if target_used is None and summary['accept'] >= 20 and trial['held_out_accept_precision'] >= al.ACCEPT_PRECISION:
            target_used = target
    hi, lo = al.pick_thresholds(prob, y, accept_target=target_used or al.ACCEPT_PRECISION)
    if target_used is None:
        hi = None
    model = al.Ridge(best['lam']).fit(x, y)
    judge = {'feature_set': best['features'], 'names': names, 'use_cnn': use_cnn, 'model': model.to_json(), 'accept_threshold': hi, 'reject_threshold': lo,
             'scope': {'score': list(al.SCORE_RANGE), 'found_by': 'one detector only (A = ft_n2, B = yolo11x)'}, 'trained_on': len(rows), 'origin': al.ORIGIN}
    if use_cnn:
        judge['cnn'] = {'mean': cnn_mean.tolist(), 'components': cnn_vt.tolist()}
    (out / 'judge.json').write_text(json.dumps(judge), encoding='utf-8')
    nested_best = next(r for r in results if r['features'] == best['features'] and r['lam'] == best['lam'])
    report = {'judged_boxes': len(rows), 'people': int(y.sum()), 'time_blocks': len(set(groups)), 'judged_total': total_judged, 'excluded_near_eval': total_judged - len(rows), 'baseline_people_share': float(base),
              'results': results, 'chosen': best, 'detector_only_best': base_detector, 'nested_three_level': nested_best,
              'accept_trials': accept_trials, 'accept_inner_target_used': target_used, 'final_thresholds': {'accept': hi, 'reject': lo}}
    (out / 'evaluation.json').write_text(json.dumps(report, indent=1), encoding='utf-8')
    print('final thresholds accept', hi, 'reject', lo)


def spots_of(model_a, model_b, image, camera, tracker):
    found_a, found_b = tracker.detect(model_a, image, camera, 0, 0.25), tracker.detect(model_b, image, camera, 0, 0.25)
    from build_pseudo_tiles import iou
    spots = []
    for mine, other, name in ((found_a, found_b, 'A'), (found_b, found_a, 'B')):
        for d in mine:
            if d[4] < 0.6 and not any(iou(d, o) >= 0.3 for o in other):
                spots.append((d, name))
    return spots


def run(args):
    import cv2
    import track_review_clip as tracker
    from ultralytics import YOLO
    out = Path(args.out)
    judge = json.loads((out / 'judge.json').read_text(encoding='utf-8'))
    model = al.Ridge.from_json(judge['model'])
    embed = Embedder() if judge['use_cnn'] else None
    avoid = eval_times(args.store) + extra_avoid_times(args)
    previous = [r['time'] for r in load_answers()] + avoid_file_times(args)
    train_previous = avoid_file_times(args, args.avoid_train_files)     # frames of earlier training rounds: only a short margin, new frames must still be different frames
    cap = cv2.VideoCapture(args.video)
    fps, total = cap.get(cv2.CAP_PROP_FPS), cap.get(cv2.CAP_PROP_FRAME_COUNT)
    seconds = total / fps
    rng = random.Random(args.seed)
    times, attempts = [], 0
    while len(times) < args.frames and attempts < 400000:
        attempts += 1
        t = rng.uniform(70, seconds - 5)
        if camera_of(t) and not al.near_any(t, avoid) and not al.near_any(t, previous, 5.0) and not al.near_any(t, train_previous, args.train_margin) and not al.near_any(t, times, args.min_gap):
            times.append(t)
    times.sort()
    print(len(times), 'frames sampled (asked for', args.frames, ')', flush=True)
    first, last = args.start, (args.start + args.count) if args.count else len(times)
    a, b = YOLO(args.weights_a), YOLO(args.weights_b)
    for sub in ('images', 'labels'):
        (out / sub).mkdir(exist_ok=True)
    rows, accepted_total = [], 0
    for n, t in enumerate(times):
        if not first <= n < last:
            continue
        image = read_frame(cv2, cap, t)
        if image is None:
            continue
        height, width = image.shape[:2]
        camera = camera_of(t)
        accepted_lines = []
        for d, name in spots_of(a, b, image, camera, tracker):
            scope = al.in_scope(float(d[4]), name)
            feats = al.box_features(cv2, image, d[:4], float(d[4]), name)
            p, decision = None, 'ask'
            if scope:
                x = np.array([[feats[k] for k in judge['names']]]) if judge['names'] else None
                if judge['use_cnn']:
                    emb = (embed(cv2, image, d[:4]) - np.array(judge['cnn']['mean'])) @ np.array(judge['cnn']['components']).T
                    x = np.hstack([x, emb[None]]) if x is not None else emb[None]
                p = float(model.predict(x)[0])
                decision = al.decide(p, judge['accept_threshold'], judge['reject_threshold'])
            rows.append({'frame': n, 'time': round(t, 1), 'camera': camera, 'box': [round(float(v), 1) for v in d[:4]], 'score': round(float(d[4]), 3),
                         'found_by': name, 'in_scope': scope, 'p_person': None if p is None else round(p, 3), 'decision': decision, 'origin': al.ORIGIN})
            if decision == 'accept':
                accepted_lines.append(f'0 {(d[0] + d[2]) / 2 / width:.6f} {(d[1] + d[3]) / 2 / height:.6f} {(d[2] - d[0]) / width:.6f} {(d[3] - d[1]) / height:.6f}')
        if accepted_lines:
            cv2.imwrite(str(out / 'images' / f'frame_{n:04d}.jpg'), image, [cv2.IMWRITE_JPEG_QUALITY, 92])
            (out / 'labels' / f'frame_{n:04d}.txt').write_text('\n'.join(accepted_lines), encoding='utf-8')
            accepted_total += len(accepted_lines)
    suffix = f'_{first:04d}' if args.count else ''
    (out / f'candidates{suffix}.jsonl').write_text('\n'.join(json.dumps(r) for r in rows) + '\n', encoding='utf-8')
    counts = {k: sum(1 for r in rows if r['decision'] == k) for k in ('accept', 'reject', 'ask')}
    scope_n = sum(1 for r in rows if r['in_scope'])
    manifest = {'origin': al.ORIGIN, 'note': 'Only accepted boxes are labelled; the other people in the frame are unlabelled (partial labels). Not human-checked.',
                'frames': len(times), 'candidates': len(rows), 'in_scope': scope_n, 'decisions': counts, 'accepted_boxes': accepted_total,
                'accept_threshold': judge['accept_threshold'], 'reject_threshold': judge['reject_threshold']}
    (out / f'manifest{suffix}.json').write_text(json.dumps(manifest, indent=1), encoding='utf-8')
    print(json.dumps(manifest, indent=1))
    asked = sorted((r for r in rows if r['decision'] == 'ask'), key=lambda r: (not r['in_scope'], abs((r['p_person'] if r['p_person'] is not None else 0.5) - 0.5)))[:40]
    if asked and args.session:
        put_session(cv2, cap, Path(args.store), args.session, asked)


def put_session(cv2, cap, store, session, asked, note='(자동 판정기가 확신하지 못한 후보입니다)'):
    if not re.match(r'^[A-Za-z0-9_-]{1,40}$', session):
        raise SystemExit('bad session name')
    folder = store / 'alerts' / session
    if (folder / 'alerts.jsonl').exists():
        raise SystemExit('session exists; use another name')
    folder.mkdir(parents=True, exist_ok=True)
    meta, lines = [], []
    for n, r in enumerate(asked):
        image = read_frame(cv2, cap, r['time'])
        h, w = image.shape[:2]
        d = r['box']
        cx, cy = (d[0] + d[2]) / 2, (d[1] + d[3]) / 2
        x0, y0 = int(min(max(0, cx - 160), w - 320)), int(min(max(0, cy - 110), h - 220))
        crop = image[y0:y0 + 220, x0:x0 + 320].copy()
        cv2.rectangle(crop, (int(d[0] - x0), int(d[1] - y0)), (int(d[2] - x0), int(d[3] - y0)), (0, 0, 255), 1)
        crop = cv2.resize(crop, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
        cv2.imwrite(str(folder / f'alerts_{n:04d}.jpg'), crop, [cv2.IMWRITE_JPEG_QUALITY, 90])
        meta.append({'n': n, 'time': r['time'], 'box': d, 'score': r['score'], 'found_by': r['found_by'], 'camera': r['camera'], 'auto_p_person': r['p_person']})
        lines.append({'time': r['time'], 'kind': 'person_check', 'polarity': 'neutral', 'title': '이 상자 안에 사람이 있나요?',
                      'text': '빨간 상자 안에 선수나 심판 같은 사람이 있으면 맞음, 사람이 아니면 틀림, 알 수 없으면 쓸모없음을 눌러 주세요. ' + note})
    (folder / 'alerts.jsonl').write_text('\n'.join(json.dumps(r, ensure_ascii=False) for r in lines) + '\n', encoding='utf-8')
    (folder / 'spots.json').write_text(json.dumps(meta), encoding='utf-8')
    print(len(lines), 'boxes for a human ->', folder)


def review_accepted(args):
    """A random sample of the boxes the judge accepted, as a new /alerts session for a human check ('is a person in the box?'): the check that decides whether the accepted boxes may be used for training."""
    import cv2
    rows = []
    for path in sorted(Path(args.out).glob('candidates_*.jsonl')):
        rows += [json.loads(x) for x in path.read_text(encoding='utf-8').splitlines() if x.strip()]
    accepted = [r for r in rows if r['decision'] == 'accept']
    sample = sorted(random.Random(args.seed).sample(accepted, min(args.count or 30, len(accepted))), key=lambda r: r['time'])
    put_session(cv2, cv2.VideoCapture(args.video), Path(args.store), args.session, sample, note='(자동 판정기가 사람이라고 자동 수락한 상자의 표본 검수입니다: 사람이 아니라고 판정하면 그 상자는 학습에 쓰지 않습니다)')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=('evaluate', 'run', 'review-accepted'))
    parser.add_argument('--video', required=True)
    parser.add_argument('--store', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--weights-a')
    parser.add_argument('--weights-b')
    parser.add_argument('--frames', type=int, default=60)
    parser.add_argument('--seed', type=int, default=33)
    parser.add_argument('--session', default='person-check3')
    parser.add_argument('--start', type=int, default=0, help='first frame index of this chunk (with --count, so a long run can be cut into short GPU pieces)')
    parser.add_argument('--count', type=int, default=0)
    parser.add_argument('--avoid-files', nargs='*', help='JSON or JSONL lists of rows with a video-second field "time" whose neighbourhood (5 s) is not sampled')
    parser.add_argument('--avoid-train-files', nargs='*', help='like --avoid-files, for the frames of earlier training rounds, kept away by --train-margin seconds only (never the judged or test frames)')
    parser.add_argument('--train-margin', type=float, default=5.0)
    parser.add_argument('--min-gap', type=float, default=5.0, help='seconds between two new frames')
    parser.add_argument('--avoid-drawn', action='store_true', help='also keep 15 s away from every scene that holds a hand-drawn box')
    args = parser.parse_args()
    {'evaluate': evaluate, 'run': run, 'review-accepted': review_accepted}[args.command](args)


if __name__ == '__main__':
    main()
