"""Frozen, video-disjoint comparison using identical measured detections.

Temporal output is delayed two frames, never retroactively rewritten after
publication. Existing baseline and endpoint model use the same scored frames.
"""
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
from app.learned_reconnect import LearnedLinker, validate_eval_group
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


def main():
    p = argparse.ArgumentParser()
    for name in ('video', 'labels', 'model', 'endpoint_model', 'weights', 'output'):
        p.add_argument(name, type=Path)
    p.add_argument('--group', required=True)
    a = p.parse_args()
    model = json.loads(a.model.read_text())
    endpoint = json.loads(a.endpoint_model.read_text())
    for m in (model, endpoint):
        validate_eval_group(m, a.group)
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
              for mode in ('raw', 'endpoint', 'temporal')}
    events, traces = [], []
    started = time.perf_counter()
    for start, end in windows:
        config = IterableSimpleNamespace(track_high_thresh=.12, new_track_thresh=.12,
            track_low_thresh=.06, track_buffer=50, match_thresh=.98, fuse_score=True)
        tracker = BYTETracker(config)
        linkers = {'endpoint': LearnedLinker(endpoint), 'temporal': TemporalLinker(model)}
        memories = {m: {} for m in totals}
        last_gt, pending, step = {}, deque(), 0
        cap.set(cv2.CAP_PROP_POS_FRAMES, round(start * fps))

        def publish(item, now):
            mappings = item['mappings']
            mappings['temporal'] = {raw: linkers['temporal'].resolve(raw) for raw in item['raw_ids']}
            # A conflicting identity in a buffered frame is also rejected.
            values = list(mappings['temporal'].values())
            mappings['temporal'] = {raw: raw if values.count(canonical) > 1 else canonical
                                    for raw, canonical in mappings['temporal'].items()}
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
                if mode == 'endpoint':
                    mappings[mode] = mapping
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
    result = {'group': a.group, 'windows': windows, 'frames': len(traces), 'analysis_fps': 5,
              'confirmation_delay_s': .4, 'results': totals, 'wall_s': time.perf_counter() - started,
              'model_sha256': hashlib.sha256(a.model.read_bytes()).hexdigest(),
              'endpoint_sha256': hashlib.sha256(a.endpoint_model.read_bytes()).hexdigest(),
              'video_sha256': hashlib.sha256(a.video.read_bytes()).hexdigest(),
              'limits': ['Diagnostic greedy IoU>=0.5 matching, not official HOTA/IDF1.',
                         'Unmatched detections are not all confirmed false positives.',
                         '5fps is a difficult low-overlap tracking condition, not a full production accuracy measure.',
                         'GT used for scoring only; all modes share boxes; no synthetic dropout or hidden-player positions.']}
    boundary = audit_join_boundaries(events, traces, windows)
    result['boundary_audit'] = {mode: {kind: sum(e['mode'] == mode and e['boundary_verdict'] == kind for e in boundary)
                                     for kind in ('correct', 'wrong', 'unresolved')}
                                for mode in ('endpoint', 'temporal')}
    for name, value in [('comparison.json', result), ('events.json', events), ('trace.json', traces), ('boundary-audit.json', boundary)]:
        (a.output / name).write_text(json.dumps(value, indent=2), encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
