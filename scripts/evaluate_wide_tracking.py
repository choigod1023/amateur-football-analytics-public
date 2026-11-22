"""Evaluate tracked boxes against SoccerTrack CSV on a short contiguous segment.

Greedy IoU matching and consecutive-frame ID changes are diagnostics, not
standard MOTChallenge scores. Keep video and annotations on the local machine.
"""
import argparse
import csv
import json
from pathlib import Path
import sys
import time

import cv2
import numpy as np
import torch
from ultralytics import YOLO

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.tiled_tracking import TiledPlayerTracker


def load_labels(path):
    with open(path, encoding='utf-8-sig', newline='') as source:
        reader = csv.reader(source)
        teams, ids, fields = next(reader), next(reader), next(reader)
        next(reader)
        frames = {}
        for row in reader:
            if not row or not row[0]:
                continue
            objects = []
            for i in range(1, len(fields), 4):
                if i + 3 >= len(row) or teams[i] not in ('0', '1') or ids[i] == '0':
                    continue
                try:
                    x, y, w, h = map(float, row[i:i+4])
                except (TypeError, ValueError):
                    continue
                if all(np.isfinite([x,y,w,h])) and w > 0 and h > 0:
                    objects.append((f'{teams[i]}:{ids[i]}', [x,y,x+w,y+h]))
            frames[int(row[0])] = objects
        return frames


def match(targets, predictions, threshold=0.5):
    pairs = []
    for gi, (_, g) in enumerate(targets):
        for pi, (p, _) in enumerate(predictions):
            x1,y1,x2,y2 = max(g[0],p[0]),max(g[1],p[1]),min(g[2],p[2]),min(g[3],p[3])
            overlap = max(0., x2-x1)*max(0.,y2-y1)
            union = (g[2]-g[0])*(g[3]-g[1])+(p[2]-p[0])*(p[3]-p[1])-overlap
            score = overlap / union if union > 0 else 0
            if score >= threshold: pairs.append((score,gi,pi))
    used_g, used_p, result = set(), set(), []
    for _, gi, pi in sorted(pairs, reverse=True):
        if gi not in used_g and pi not in used_p:
            used_g.add(gi); used_p.add(pi); result.append((targets[gi][0], str(predictions[pi][1])))
    return result


class MissedReappearanceAudit:
    """Score same annotated person after missed processed frames, not IDF1.

    Only count a return when the annotated person remained in the annotation
    while unmatched. Discard memory when the GT person leaves the annotations,
    because that case cannot be distinguished from ground-truth omission.
    """
    def __init__(self):
        self.last = {}
        self.gap_lengths = []
        self.retained = 0
        self.switched = 0

    def update(self, targets, found):
        ids = [str(tid) for tid, _ in targets]
        matches = dict(found)
        for tid in set(self.last) - set(ids):
            self.last.pop(tid)
        for tid in ids:
            previous = self.last.get(tid)
            if tid not in matches:
                if previous is not None:
                    previous['missed'] += 1
                continue
            track = str(matches[tid])
            if previous and previous['missed']:
                self.gap_lengths.append(previous['missed'])
                if previous['track'] == track:
                    self.retained += 1
                else:
                    self.switched += 1
            self.last[tid] = {'track': track, 'missed': 0}

    def summary(self):
        return {'gap_returns': len(self.gap_lengths), 'reappeared_same_id': self.retained,
                'reappeared_changed_id': self.switched, 'gap_lengths_scored_observations': self.gap_lengths,
                'limitations': 'Only returns after unmatched GT-visible scored observations; GT missing breaks history; not IDF1 or actual unobserved-player accuracy.'}


def evaluate(video, labels, weights, start, count, device, mode, confidence, low_score_recovery=False, stride=1, score_stride=1):
    if stride < 1 or score_stride < 1:
        raise ValueError('strides must be positive')
    ground = load_labels(labels)
    if str(device).startswith('cuda'):
        torch.cuda.init()
        torch.cuda.reset_peak_memory_stats(device)
    model = YOLO(str(weights))
    tracker = TiledPlayerTracker(model, device, 640, confidence, low_score_recovery=low_score_recovery) if mode == 'tiled' else None
    cap = cv2.VideoCapture(str(video))
    cap.set(cv2.CAP_PROP_POS_FRAMES, start)
    totals = dict(frames=0, processed_frames=0, gt=0, predicted=0, matched=0, consecutive_id_changes=0)
    previous = {}
    gaps = MissedReappearanceAudit()
    begun = time.perf_counter()
    try:
        for sample_index, frame_number in enumerate(range(start, start+count*stride, stride)):
            ok, image = cap.read()
            if not ok or frame_number not in ground: break
            if tracker:
                predictions = tracker.update(image)
            else:
                boxes = model.track(image, persist=True, tracker='bytetrack.yaml', classes=[0], verbose=False, device=device, imgsz=640, conf=confidence)[0].boxes
                predictions = [] if boxes is None or boxes.id is None else list(zip(boxes.xyxy.cpu().numpy(), boxes.id.int().cpu().tolist()))
            totals['processed_frames'] += 1
            if sample_index % score_stride == 0:
                found = match(ground[frame_number], predictions)
                gaps.update(ground[frame_number], found)
                now = dict(found)
                totals['consecutive_id_changes'] += sum(key in previous and previous[key] != track for key, track in now.items())
                previous = now
                totals['frames'] += 1; totals['gt'] += len(ground[frame_number]); totals['predicted'] += len(predictions); totals['matched'] += len(found)
            for _ in range(stride-1):
                if not cap.grab(): break
    finally:
        cap.release()
    totals['seconds'] = round(time.perf_counter()-begun, 2)
    totals['effective_fps'] = round(totals['processed_frames']/totals['seconds'], 2) if totals['seconds'] else None
    totals['peak_torch_allocated_mib'] = round(torch.cuda.max_memory_allocated(device)/1048576, 1) if str(device).startswith('cuda') else None
    totals['peak_torch_reserved_mib'] = round(torch.cuda.max_memory_reserved(device)/1048576, 1) if str(device).startswith('cuda') else None
    totals['recall_iou50'] = round(totals['matched']/totals['gt'], 4) if totals['gt'] else None
    totals['precision_iou50'] = round(totals['matched']/totals['predicted'], 4) if totals['predicted'] else None
    totals['gap_reappearance'] = gaps.summary()
    totals['source_frame_stride'] = stride
    totals['score_stride'] = score_stride
    return totals


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for key in ('video','labels','weights'): p.add_argument('--'+key, required=True, type=Path)
    p.add_argument('--mode', choices=('whole','tiled'), default='tiled')
    p.add_argument('--device', default='cpu'); p.add_argument('--start',type=int,default=350)
    p.add_argument('--frames',type=int,default=30); p.add_argument('--confidence',type=float,default=.35)
    p.add_argument('--low-score-recovery', action='store_true')
    p.add_argument('--stride', type=int, default=1, help='Keep every Nth source frame to model dropping between analyses')
    p.add_argument('--score-stride', type=int, default=1, help='Score every Nth processed frame, without skipping inference')
    a=p.parse_args()
    print(json.dumps(evaluate(a.video,a.labels,a.weights,a.start,a.frames,a.device,a.mode,a.confidence,a.low_score_recovery,a.stride,a.score_stride),ensure_ascii=False,indent=2))
