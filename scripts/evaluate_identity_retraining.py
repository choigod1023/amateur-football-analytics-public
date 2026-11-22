"""Frozen old/new TemporalLinker comparison; shared detections and causal delay."""
import argparse
import hashlib
import json
import sys
import time
from collections import deque
from pathlib import Path
import cv2
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.learned_reconnect import validate_eval_group
from app.temporal_reconnect import TemporalLinker
from app.reconnect_evaluation import audit_join_boundaries
from evaluate_wide_tracking import match
from ultralytics import YOLO
from ultralytics.engine.results import Boxes
from ultralytics.trackers.byte_tracker import BYTETracker
from ultralytics.utils import IterableSimpleNamespace


def score_frame(item, mapping, memory, total):
    visible = {gt for gt, _ in item['targets']}
    for gt in list(memory):
        if gt not in visible:
            del memory[gt]
    found = {gt: mapping[raw] for gt, raw in item['matches']}
    for gt, identity in found.items():
        old = memory.get(gt)
        if old:
            total['id_switches'] += old['id'] != identity
            if old['step'] < item['step'] - 1:
                total['return_same' if old['id'] == identity else 'return_switched'] += 1
        memory[gt] = {'id': identity, 'step': item['step']}
    total['matched'] += len(found)
    total['missed_gt'] += len(item['targets']) - len(found)
    total['unmatched_detection'] += len(item['raw_ids']) - len(found)


def validate_comparison(baseline, candidate, group):
    for model in (baseline, candidate):
        validate_eval_group(model, group)
    for key in ('features', 'threshold', 'ambiguity_margin', 'confirmation_frames',
                'output_delay_frames', 'max_prediction_residual_heights'):
        if baseline[key] != candidate[key]:
            raise ValueError('Comparison changes frozen policy: ' + key)
    if baseline['confirmation_frames'] != 3 or baseline['output_delay_frames'] != 2:
        raise ValueError('Frozen evaluation requires three observations and two-frame delay')


def publication_mapping(raw_ids, linker):
    mapping = {raw: linker.resolve(raw) for raw in raw_ids}
    values = list(mapping.values())
    return {raw: raw if values.count(canonical) > 1 else canonical
            for raw, canonical in mapping.items()}


def validate_source_hash(candidate, digest):
    sources = candidate.get('train_source_sha256')
    if not isinstance(sources, list) or not sources or digest in sources:
        raise ValueError('Candidate training source hashes missing or evaluation source was used for training')


def main():
    p = argparse.ArgumentParser()
    for name in ('video', 'labels', 'baseline_model', 'candidate_model', 'weights', 'output'):
        p.add_argument(name, type=Path)
    p.add_argument('--group', required=True)
    a = p.parse_args()
    baseline = json.loads(a.baseline_model.read_text(encoding='utf-8'))
    candidate = json.loads(a.candidate_model.read_text(encoding='utf-8'))
    validate_comparison(baseline, candidate, a.group)
    with a.video.open('rb') as source:
        video_sha256 = hashlib.file_digest(source, 'sha256').hexdigest()
    validate_source_hash(candidate, video_sha256)
    a.output.mkdir(exist_ok=False)
    annotation = json.loads(a.labels.read_text(encoding='utf-8'))
    labels = {int(r['frame']): r['data'] for r in annotation['tag']}
    cap = cv2.VideoCapture(str(a.video))
    fps = cap.get(cv2.CAP_PROP_FPS)
    if abs(fps - 30) > .1:
        raise ValueError('Frozen evaluation requires 30fps sources')
    detector = YOLO(str(a.weights))
    windows = [(0, 30), (300, 330), (600, 630)]
    totals = {mode: {k: 0 for k in ('id_switches', 'matched', 'missed_gt', 'unmatched_detection',
              'joins', 'correct_joins', 'wrong_joins', 'unresolved_joins', 'return_same', 'return_switched')}
              for mode in ('raw', 'baseline', 'candidate')}
    events, traces = [], []
    detection_digest = hashlib.sha256()
    started = time.perf_counter()
    for start, end in windows:
        config = IterableSimpleNamespace(track_high_thresh=.12, new_track_thresh=.12,
            track_low_thresh=.06, track_buffer=50, match_thresh=.98, fuse_score=True)
        tracker = BYTETracker(config)
        linkers = {'baseline': TemporalLinker(baseline), 'candidate': TemporalLinker(candidate)}
        memories = {m: {} for m in totals}
        last_gt, pending, step = {}, deque(), 0
        cap.set(cv2.CAP_PROP_POS_FRAMES, round(start * fps))

        def publish(item, now):
            mappings = item['mappings']
            for mode, linker in linkers.items():
                mappings[mode] = publication_mapping(item['raw_ids'], linker)
            for mode, mapping in mappings.items():
                score_frame(item, mapping, memories[mode], totals[mode])
            traces.append({'time': item['time'], 'published_at': now, 'matches': item['matches'],
                           'aliases': mappings, 'tracked': len(item['raw_ids'])})

        for index in range(round(start * fps), round(end * fps)):
            ok, frame = cap.read()
            if not ok:
                raise RuntimeError('Video ended during fixed window')
            if (index - round(start * fps)) % 6:
                continue
            t = index / fps
            prediction = detector.predict(frame, device=0, imgsz=1280, conf=.1,
                                          classes=[0], max_det=150, verbose=False)[0]
            array = prediction.boxes.data.cpu().numpy() if prediction.boxes is not None else np.zeros((0, 6), np.float32)
            detection_digest.update(np.asarray([index, len(array)], dtype=np.int64).tobytes())
            detection_digest.update(array.tobytes())
            tracks = tracker.update(Boxes(array, frame.shape[:2]), None)
            targets = []
            for row in labels.get(index, []):
                x, y, w, h = row['tag']
                if w > 0 and h > 0 and not row.get('jump', False):
                    targets.append((str(row['id']), [x, y, x + w, y + h]))
            matches = match(targets, [(r[:4], str(int(r[4]))) for r in tracks])
            raw_to_gt = {raw: gt for gt, raw in matches}
            raw_ids = [str(int(r[4])) for r in tracks]
            mappings = {'raw': {raw: raw for raw in raw_ids}}
            for mode, linker in linkers.items():
                mapping, joins = linker.update(t, frame, tracks)
                for event in joins:
                    old_gt, new_gt = last_gt.get(event['previous_raw']), raw_to_gt.get(event['raw'])
                    kind = ('unresolved_joins' if old_gt is None or new_gt is None else
                            'correct_joins' if old_gt == new_gt else 'wrong_joins')
                    totals[mode]['joins'] += 1
                    totals[mode][kind] += 1
                    events.append({'mode': mode, **event, 'old_gt': old_gt, 'new_gt': new_gt, 'classification': kind})
            last_gt.update(raw_to_gt)
            pending.append({'time': t, 'step': step, 'targets': targets, 'matches': matches,
                            'raw_ids': raw_ids, 'mappings': mappings})
            if len(pending) > 2:
                publish(pending.popleft(), t)
            step += 1
        # End of stream: flush existing observations without looking beyond window.
        while pending:
            publish(pending.popleft(), t)
    cap.release()
    result = {'mode_names': {'baseline': 'original_four_pair_model', 'candidate': 'new_human_answers_retrained'}, 'operationally_approved': False, 'group': a.group, 'windows': windows, 'frames': len(traces), 'analysis_fps': 5,
              'confirmation_delay_s': .4, 'results': totals, 'wall_s': time.perf_counter() - started,
              'baseline_sha256': hashlib.sha256(a.baseline_model.read_bytes()).hexdigest(),
              'candidate_sha256': hashlib.sha256(a.candidate_model.read_bytes()).hexdigest(),
              'labels_sha256': hashlib.sha256(a.labels.read_bytes()).hexdigest(),
              'weights_sha256': hashlib.sha256(a.weights.read_bytes()).hexdigest(),
              'shared_detection_sha256': detection_digest.hexdigest(),
              'video_sha256': video_sha256,
              'limits': ['Diagnostic greedy IoU>=0.5 matching, not official HOTA/IDF1.',
                         'Unmatched detections are not all confirmed false positives.',
                         '5fps is a difficult low-overlap tracking condition, not a full production accuracy measure.',
                         'GT used for scoring only; all modes share boxes; no synthetic dropout or hidden-player positions.',
                         'These video groups were inspected in prior experiments: held out from training, not a fresh final test.']}
    result['split_checks'] = {'group_excluded_from_both_models': True,
                              'video_hash_excluded_from_candidate_sources': True,
                              'baseline_has_source_hashes': bool(baseline.get('train_source_sha256'))}
    boundary = audit_join_boundaries(events, traces, windows)
    result['boundary_audit'] = {mode: {kind: sum(e['mode'] == mode and e['boundary_verdict'] == kind for e in boundary)
                                     for kind in ('correct', 'wrong', 'unresolved')}
                                for mode in ('baseline', 'candidate')}
    delays = [r['published_at']-r['time'] for r in traces]
    assert all(-1e-6 <= delay <= .400001 for delay in delays)
    result['measured_publication_delay_s'] = {'min': min(delays), 'max': max(delays)}
    for name, value in [('comparison.json', result), ('events.json', events), ('trace.json', traces), ('boundary-audit.json', boundary)]:
        (a.output / name).write_text(json.dumps(value, indent=2), encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
