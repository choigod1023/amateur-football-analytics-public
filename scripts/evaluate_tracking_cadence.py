"""Four-way cadence/camera ablation on a common 5Hz scoring grid."""
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
import cv2
import numpy as np
import torch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.tracking_motion import make_tracker
from evaluate_wide_tracking import match
from ultralytics import YOLO
from ultralytics.engine.results import Boxes

MODES = {'5fps': (6, False), '15fps': (2, False),
         '15fps_legacy_camera': (2, True), '15fps_camera': (2, True)}


def main():
    p = argparse.ArgumentParser()
    for name in ('video', 'labels', 'weights', 'output'):
        p.add_argument(name, type=Path)
    p.add_argument('--alignment-guard', action='store_true')
    p.add_argument('--half', action='store_true')
    p.add_argument('--fast-profile', action='store_true', help='10Hz, FP16, guarded XYAH compensation at downscale 4')
    a = p.parse_args()
    modes = {'10fps_fast_camera': (3, True)} if a.fast_profile else MODES
    if a.fast_profile:
        a.half, a.alignment_guard = True, True
    a.output.mkdir(exist_ok=False)
    labels = {int(r['frame']): r['data'] for r in json.loads(a.labels.read_text(encoding='utf-8'))['tag']}
    cap = cv2.VideoCapture(str(a.video)); fps = cap.get(cv2.CAP_PROP_FPS)
    if abs(fps - 30) > .1:
        raise ValueError('Fixed experiment expects 30fps input')
    model = YOLO(str(a.weights))
    totals = {m: {k: 0 for k in ('id_switches', 'matched', 'missed_gt', 'unmatched_detection',
              'same_id_cross_person', 'same_id_comparisons', 'return_same', 'return_switched',
              'updates', 'camera_accepted', 'camera_rejected', 'camera_initialized')} for m in modes}
    durations = {m: [] for m in modes}; detection_times = []; trace = []; events = []
    common = {m: 0 for m in modes}; common_n = 0
    started = time.perf_counter(); torch.cuda.reset_peak_memory_stats()
    for start, end in ((0, 30), (300, 330), (600, 630)):
        trackers = {m: make_tracker(30 / step, camera, legacy_camera=m.endswith('legacy_camera'), alignment_guard=a.alignment_guard, camera_downscale=4 if a.fast_profile else 2) for m, (step, camera) in modes.items()}
        gt_history = {m: {} for m in modes}; id_history = {m: {} for m in modes}; prev_common = {}
        cap.set(cv2.CAP_PROP_POS_FRAMES, round(start * fps)); step_n = 0
        for index in range(round(start * fps), round(end * fps)):
            ok, frame = cap.read()
            if not ok:
                raise RuntimeError('Input ended early')
            if all((index - round(start * fps)) % interval for interval, _ in modes.values()):
                continue
            tick = time.perf_counter()
            result = model.predict(frame, device=0, imgsz=1280, conf=.1, classes=[0], max_det=150, verbose=False, quantize=16 if a.half else 32)[0]
            boxes = result.boxes.data.cpu().numpy() if result.boxes is not None else np.zeros((0, 6), np.float32)
            detection_times.append(time.perf_counter() - tick)
            targets = [(str(r['id']), [r['tag'][0], r['tag'][1], r['tag'][0]+r['tag'][2], r['tag'][1]+r['tag'][3]])
                       for r in labels.get(index, []) if r['tag'][2] > 0 and r['tag'][3] > 0 and not r.get('jump', False)]
            visible = {gt for gt, _ in targets}; by_mode = {}; t = index / fps
            for mode, (interval, camera) in modes.items():
                if (index - round(start * fps)) % interval:
                    continue
                tracker = trackers[mode]; tick = time.perf_counter()
                tracks = tracker.update(Boxes(boxes.copy(), frame.shape[:2]), frame if camera else None)
                durations[mode].append(time.perf_counter() - tick)
                totals[mode]['updates'] += 1
                if (index - round(start * fps)) % 6:
                    continue
                matches = match(targets, [(r[:4], str(int(r[4]))) for r in tracks])
                found = dict(matches); by_mode[mode] = found
                memory = gt_history[mode]; ids = id_history[mode]; total = totals[mode]
                for gt in list(memory):
                    if gt not in visible:
                        del memory[gt]
                for gt, identity in matches:
                    old = memory.get(gt)
                    if old:
                        total['id_switches'] += old['id'] != identity
                        if old['step'] < step_n - 1:
                            total['return_same' if old['id'] == identity else 'return_switched'] += 1
                    memory[gt] = {'id': identity, 'step': step_n}
                    old_id = ids.get(identity)
                    if old_id:
                        total['same_id_comparisons'] += 1
                        if old_id['gt'] != gt:
                            total['same_id_cross_person'] += 1
                            events.append({'mode': mode, 'id': identity, 'before_gt': old_id['gt'],
                                           'after_gt': gt, 'before_time': old_id['time'], 'after_time': t})
                    ids[identity] = {'gt': gt, 'time': t}
                total['matched'] += len(matches); total['missed_gt'] += len(targets) - len(matches)
                total['unmatched_detection'] += len(tracks) - len(matches)
            if by_mode:
                all_gt = set.intersection(*(set(rows) for rows in by_mode.values()))
                for gt in all_gt & prev_common.keys():
                    common_n += 1
                    for mode in modes:
                        common[mode] += prev_common[gt][mode] != by_mode[mode][gt]
                prev_common = {gt: {m: by_mode[m][gt] for m in modes} for gt in all_gt}
                trace.append({'time': t, 'matched_ids': by_mode})
                step_n += 1
        for mode, tracker in trackers.items():
            if hasattr(tracker, 'gmc'):
                for k, v in tracker.gmc.counts.items():
                    totals[mode]['camera_' + k] += v
    cap.release()
    result = {'windows': [[0, 30], [300, 330], [600, 630]], 'scored_frames': len(trace),
              'alignment_guard': a.alignment_guard,
              'half_precision': a.half,
              'fast_profile': a.fast_profile,
              'results': totals, 'common_consecutive_gt_pairs': common_n,
              'common_pair_id_switches': common, 'wall_s_all_modes': time.perf_counter() - started,
              'detector_calls': len(detection_times), 'detector_ms_mean': float(np.mean(detection_times)*1000),
              'tracker_ms_mean': {m: float(np.mean(v)*1000) for m,v in durations.items()},
              'cuda_peak_allocated_mb': torch.cuda.max_memory_allocated()/1024**2,
              'video_sha256': hashlib.sha256(a.video.read_bytes()).hexdigest(),
              'limits': ['Diagnostic IoU>=0.5, not HOTA/IDF1.',
                         'Unmatched boxes are not all confirmed false positives.',
                         'Same-ID cross-person counts proven GT assignment changes within a window, not relinker proposals.',
                         'Scored on the same 5Hz grid; reference traces may come from a separate run.',
                         'Lost-track retention fixed at 10 seconds, scaled to each tracking cadence.']}
    for name, value in [('comparison.json', result), ('trace.json', trace), ('identity-errors.json', events)]:
        (a.output/name).write_text(json.dumps(value, indent=2), encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
