"""Add chosen clip frames to the review queue as new scenes, so a person can draw the people the detector missed.

Usage: python scripts/add_review_scenes.py <review store> <selection.json> <source_map_match_from_17min.json> <output pending folder>
       [--small yolo11n.pt] [--large yolo11x.pt] [--dry-run]

selection.json: {"references": {"cam1": {"image": "<scene photo>", "bg": [a, b, tx, ty]}, ...},
                 "scenes": [{"clip": "b04", "frame": 26, "split": "train" | "eval", "note": "..."}]}
The frames come from <store>/ball/clips/<clip>/f_NNN.jpg. Candidate boxes are the union of two detectors (a small and a
large one, score >= 0.20, overlapping boxes merged), written in the same format as the other pending scenes. New files
only: existing scenes and labels are never touched, and a scene whose photo is already in the folder is skipped.
Everything stays on this computer.
"""
import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import track_review_clip as tracker  # noqa: E402

NOTE = 'candidate boxes: union of yolo11n and yolo11x tiles at 384 px, score >= 0.20 (unverified model candidates); added to find people the detector misses'


def source_of(segments, seconds):
    """(source file, seconds inside that file) of a time in match_from_17min.mp4."""
    segment = [s for s in segments if s['cut_start_sec'] <= seconds][-1]
    return segment['source'], segment['source_offset_sec'] + (seconds - segment['cut_start_sec'])


def hints(cv2, np, image, box, height):
    """The same unverified hints the earlier scenes carry: foreground people as spectators, neon vests as colour group 0."""
    stands = (box[3] - box[1]) >= 100 or box[3] >= 0.84 * height
    neon = tracker.shirt_label(cv2, np, image, box) == 'A'
    return ('spectator' if stands else None), (0 if neon and not stands else None)


def registration(reference, shift):
    """bg_to_ref of a new scene: the reference photo's registration composed with the measured shift of the scene against it."""
    a, b, tx, ty = reference
    return [a, b, round(tx - (a * shift[0] - b * shift[1]), 3), round(ty - (b * shift[0] + a * shift[1]), 3)]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('store')
    parser.add_argument('selection')
    parser.add_argument('source_map')
    parser.add_argument('output')
    parser.add_argument('--small', default='yolo11n.pt')
    parser.add_argument('--large', default='yolo11x.pt')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    import cv2
    import numpy as np
    from ultralytics import YOLO
    from app.pitch_map import frame_shift_images

    selection = json.loads(Path(args.selection).read_text(encoding='utf-8'))
    segments = json.loads(Path(args.source_map).read_text(encoding='utf-8-sig'))['segments']
    store, output = Path(args.store), Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    models = [YOLO(args.small), YOLO(args.large)]
    references = {cam: (cv2.imread(r['image']), r['bg']) for cam, r in selection['references'].items()}
    existing = [int(float(json.loads(p.read_text(encoding='utf-8')).get('order', 0))) for p in output.glob('*.json') if len(p.stem) == 32]
    order = max(existing + [0]) + 1
    added = 0
    for item in selection['scenes']:
        clip = json.loads((store / 'ball' / 'clips' / item['clip'] / 'candidates.json').read_text(encoding='utf-8'))
        frame_path = store / 'ball' / 'clips' / item['clip'] / f"f_{item['frame']:03d}.jpg"
        data = frame_path.read_bytes()
        token = hashlib.md5(data).hexdigest()
        if (output / f'{token}.jpg').exists():
            print('skip (already there):', item['clip'], item['frame'])
            continue
        image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        height, width = image.shape[:2]
        found = []
        for model in models:
            found += tracker.detect(model, image, clip['camera'], 0, 0.20)
        found = [[float(v) for v in d] for d in found]
        found.sort(key=lambda d: -d[4])
        kept = []
        for d in found:
            if all(tracker.overlap_share(d, k) <= 0.6 for k in kept):
                kept.append(d)
        kept.sort(key=lambda d: -d[4])
        people = []
        for number, d in enumerate(kept, 1):
            role, colour = hints(cv2, np, image, d[:4], height)
            people.append({'id': f'cand-{number:02d}', 'bbox': [d[0] / width, d[1] / height, d[2] / width, d[3] / height],
                           'suggested_color_group': colour, 'annotation_origin': 'model_candidate', 'detector_score': round(d[4], 3),
                           'role_hint_unverified': role})
        reference_image, reference_bg = references[clip['camera']]
        shift = tuple(float(v) for v in frame_shift_images(reference_image, image))
        seconds = clip['start'] + (item['frame'] - 1) / clip['fps']
        source, offset = source_of(segments, seconds)
        meta = {'people': people, 'timestamp': item.get('note') or f"클립 {item['clip']} · 컷 영상 {int(seconds // 60)}:{int(seconds % 60):02d}",
                'source': 'own_match_clip_frame_hard_case', 'created': time.time(), 'order': order,
                'source_provenance': {'split': item['split'], 'origin': 'own_match_recording_frame', 'frame_file': frame_path.name,
                                      'clip': 'match_from_17min.mp4', 'clip_time_sec': round(seconds, 1), 'source_file': source,
                                      'source_time_sec': round(offset, 1), 'near_seam': False, 'candidate_boxes': NOTE,
                                      'camera_setting': clip['camera'], 'bg_to_ref': registration(reference_bg, shift),
                                      'ball_clip': item['clip'], 'ball_clip_frame': item['frame'],
                                      'split_note': 'added to improve person detection of dark-clothed players; eval scenes are held out from training'}}
        print(f"{item['clip']} frame {item['frame']} -> {token[:8]} {item['split']} {clip['camera']} {len(people)} candidates, shift {shift[0]:.1f},{shift[1]:.1f}")
        if not args.dry_run:
            (output / f'{token}.jpg').write_bytes(data)
            (output / f'{token}.json').write_text(json.dumps(meta, ensure_ascii=False), encoding='utf-8')
        order += 1
        added += 1
    print('added', added, 'scenes' + (' (dry run, nothing written)' if args.dry_run else ''))


if __name__ == '__main__':
    main()
