"""Track the people in one short ball-review clip and write the tracks to a local JSON file.

Usage: python scripts/track_review_clip.py <clip folder with f_*.jpg> <cam1|cam3> <output.json> [--model yolo11n.pt]

Image-space prototype only: no pitch calibration is used, so positions are pixels, never metres. Team labels are a
colour heuristic voted over each track (unclear tracks stay null). Nothing is sent anywhere.
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.profile_teams import MODES, OfflineTeams, profile_probabilities  # noqa: E402
from app.team_color_profile import load_profile  # noqa: E402
from app.team_role_features import FEATURE_NAMES, box_features  # noqa: E402
from app.team_role_infer import load_model, predict, track_label, windowed_labels  # noqa: E402
from app.track_stitch import fill_gaps, stitch_tracks  # noqa: E402
from app.track_vote import SPECTATOR, TRACKER_SETTINGS, drop_short_tracks, is_person_track, summarise_tracks, vote_tracks  # noqa: E402

PITCH_TOP = {'cam1': 0.62, 'cam3': 0.50, 'cam4': 0.38}       # the part of the frame above this fraction is stands and sky
TILE = 384


def starts(total, size, overlap):
    found = list(range(0, max(1, total - size + 1), max(1, int(size * (1 - overlap)))))
    if found[-1] != max(0, total - size):
        found.append(max(0, total - size))
    return found


def overlap_share(a, b):
    width = min(a[2], b[2]) - max(a[0], b[0])
    height = min(a[3], b[3]) - max(a[1], b[1])
    smaller = min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1]))
    return width * height / max(1e-6, smaller) if width > 0 and height > 0 else 0.0


def detect(model, image, camera, device, confidence=0.20, batch_size=1, half=False, tile_size=768, imgsz=None):
    """Run unchanged tiles in bounded batches; retain legacy single-image default.

    All tiles within one input have the same shape, including small inputs, so
    batching does not change Ultralytics' per-image letterbox dimensions. GPU
    kernels can still produce small numerical differences; validate real output
    before enabling a different batch size in production.
    """
    if isinstance(batch_size, bool) or not isinstance(batch_size, int) or batch_size < 1:
        raise ValueError('batch_size must be a positive integer')
    if imgsz is not None:                      # the older name of the same setting (scripts/run_live_feedback.py --detector-imgsz)
        tile_size = imgsz
    # 384 px tiles are enlarged to this size. 1024 and 1280 were measured on the human-checked night boxes (wiki/night-recognition.md);
    # the 2026-11-20 merge kept a 640/768-only check that stopped --detector-imgsz 1024 at every frame.
    if isinstance(tile_size, bool) or not isinstance(tile_size, int) or not (320 <= tile_size <= 1600) or tile_size % 32:
        raise ValueError('tile_size must be a multiple of 32 between 320 and 1600')
    height, width = image.shape[:2]
    top = int(height * PITCH_TOP[camera])
    found = []
    locations = [(x, top + y) for y in starts(height - top, TILE, 0.25)
                 for x in starts(width, TILE, 0.25)]
    for offset in range(0, len(locations), batch_size):
        chunk = locations[offset:offset + batch_size]
        crops = [image[y:y + TILE, x:x + TILE] for x, y in chunk]
        source = crops[0] if batch_size == 1 else crops
        results = model.predict(source, device=device, imgsz=tile_size, conf=confidence, quantize=16 if half else 32,
                                classes=[0], max_det=100, verbose=False)
        if len(results) != len(chunk):
            raise RuntimeError('Detector returned a different number of tile results')
        for (x, y), result in zip(chunk, results):
            if result.boxes is None:
                continue
            # Copy each result tensor once; avoid many tiny device synchronizations.
            if hasattr(result.boxes, 'data'):
                rows = result.boxes.data.cpu().numpy()
                values = ((r[:4], r[4]) for r in rows)
            else:
                values = zip(result.boxes.xyxy.cpu().numpy(), result.boxes.conf.cpu().numpy())
            for box, score in values:
                # Python floats make the small, scalar cross-tile NMS much cheaper.
                found.append([float(box[0] + x), float(box[1] + y), float(box[2] + x), float(box[3] + y), float(score)])
    found.sort(key=lambda d: -d[4])
    kept = []
    for d in found:
        if all(overlap_share(d, k) <= 0.6 for k in kept):
            kept.append(d)
    return kept


def shirt_label(cv2, np, image, box, teams=None):
    """Team letter of one box. With `teams` (app.profile_teams.OfflineTeams, from --team-profile) the colours the coach chose decide: 'B' own, 'A' opponent, None unclear.
    Without it the colour rule of the first match stays (neon share 0.14 or more is 'A', everything else 'B')."""
    if teams is not None:
        return teams.letter_of_box(image, box)
    h, w = box[3] - box[1], box[2] - box[0]
    patch = image[int(box[1] + .18 * h):int(box[1] + .55 * h) + 1, int(box[0] + .2 * w):int(box[2] - .2 * w) + 1]
    if patch.size == 0:
        return 'B'
    hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV).reshape(-1, 3).astype(np.float32)
    neon = ((hsv[:, 0] >= 22) & (hsv[:, 0] <= 44) & (hsv[:, 1] > 90) & (hsv[:, 2] > 110)).mean()
    return 'A' if neon >= .14 else 'B'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('clip')
    parser.add_argument('camera', choices=sorted(PITCH_TOP))
    parser.add_argument('output')
    parser.add_argument('--model', default='yolo11n.pt')
    parser.add_argument('--device', default=0)
    parser.add_argument('--confidence', type=float, default=0.20, help='lowest detector score kept; a lower value finds more of the dim, far players and more false ones')
    parser.add_argument('--label-window', type=int, default=0, help='label every frame from the class probabilities of this many frames on each side instead of one label per track (follows tracker identity swaps)')
    parser.add_argument('--fill-gaps', type=int, default=0, help='interpolate gaps of up to this many frames inside a track (rows are marked interpolated)')
    parser.add_argument('--min-track-length', type=int, default=1, help='drop person tracks shorter than this many frames after joining (use about 10 with a low --confidence)')
    parser.add_argument('--start-threshold', type=float, help='score a detection needs to start a new track (and to count as a confident detection); by default the tracker settings are used')
    parser.add_argument('--classifier', help='model.pt from scripts/train_team_role.py; without it a colour rule labels the teams')
    parser.add_argument('--team-profile', help='team_profile.json of /team-select: the own team (letter B) and the opponent (letter A) are told apart by the colours the coach chose; without it the colour rule of the first match stays')
    parser.add_argument('--profile-mode', choices=MODES, default='profile', help='with --classifier and --team-profile: profile only, or the model decides where the profile is unclear (fallback), or the reverse (model)')
    args = parser.parse_args()
    import cv2
    import numpy as np
    from ultralytics import YOLO
    from ultralytics.engine.results import Boxes
    from ultralytics.trackers.byte_tracker import BYTETracker
    from ultralytics.utils import IterableSimpleNamespace, YAML
    from ultralytics.utils.checks import check_yaml

    frames = sorted(Path(args.clip).glob('f_*.jpg'))
    if not frames:
        raise SystemExit('No f_*.jpg frames in the clip folder')
    model = YOLO(args.model)
    config = IterableSimpleNamespace(**YAML.load(check_yaml('bytetrack.yaml')))
    for key, value in TRACKER_SETTINGS.items():
        setattr(config, key, value)
    if args.start_threshold:
        config.track_high_thresh = config.new_track_thresh = args.start_threshold
        config.track_low_thresh = min(config.track_low_thresh, args.start_threshold / 2)
    tracker = BYTETracker(args=config)
    classifier = load_model(args.classifier) if args.classifier else None
    profile = load_profile(args.team_profile) if args.team_profile else None
    if args.team_profile and profile is None:
        raise SystemExit(f'Team profile file not found: {args.team_profile}. Choose the own team on /team-select first, or run without --team-profile.')
    teams = OfflineTeams(profile) if profile else None
    tracks, class_scores, neon_shares = {}, {}, {}
    for index, path in enumerate(frames):
        image = cv2.imread(str(path))
        height, width = image.shape[:2]
        detections = detect(model, image, args.camera, args.device, args.confidence)
        array = np.array([[*d[:4], d[4], 0.0] for d in detections], np.float32).reshape(-1, 6)
        tracked = [[float(v) for v in row[:5]] for row in tracker.update(Boxes(array, (height, width)), image)]
        scores = None
        if classifier and tracked:
            features = np.array([box_features(image, [r[0] / width, r[1] / height, r[2] / width, r[3] / height]) for r in tracked])
            scores = predict(classifier, features)
            if teams is not None:
                scores = np.array([profile_probabilities(teams, f, classifier['classes'], p, args.profile_mode) for f, p in zip(features, scores)])
        for k, (x1, y1, x2, y2, track_id) in enumerate(tracked):
            track_id = int(track_id)
            stands = (y2 - y1) >= 90 or y2 >= 0.84 * height
            label = SPECTATOR if stands else shirt_label(cv2, np, image, [x1, y1, x2, y2], teams)
            tracks.setdefault(track_id, []).append((index, label, [round(v, 1) for v in (x1, y1, x2, y2)]))
            if scores is not None:
                class_scores.setdefault(track_id, []).append(scores[k])
                neon_shares.setdefault(track_id, []).append(float(features[k][FEATURE_NAMES.index('neon')]))
    if classifier:
        # one label per track from the summed class probabilities; unclear tracks stay unknown
        if args.label_window:
            tracks = {tid: [(f, label, box) for (f, _, box), label in zip(rows, windowed_labels(class_scores[tid], [] if teams is not None else neon_shares[tid], classifier['classes'], args.label_window))]
                      for tid, rows in tracks.items()}
        else:
            tracks = {tid: [(f, track_label(class_scores[tid], classifier['classes'], neon=None if teams is not None else float(np.mean(neon_shares[tid]))), box) for f, _, box in rows] for tid, rows in tracks.items()}
    # per-frame labels are kept as they are when a window is used; otherwise every track gets the majority label of its rows
    voted = {tid: [(f, label) for f, label, _ in rows] for tid, rows in tracks.items()} if args.label_window else vote_tracks({tid: [(f, label) for f, label, _ in rows] for tid, rows in tracks.items()})
    before = summarise_tracks(voted, len(frames))
    rows_by_id = {tid: [{'frame': f, 'team': label, 'box': box} for (f, _, box), (_, label) in zip(rows, voted[tid])]
                  for tid, rows in tracks.items()}
    people = {tid: rows for tid, rows in rows_by_id.items() if is_person_track(row['team'] for row in rows)}
    stands = {tid: rows for tid, rows in rows_by_id.items() if tid not in people}
    joined, joins = stitch_tracks(people)
    joined = drop_short_tracks(joined, args.min_track_length)
    interpolated = 0
    if args.fill_gaps:
        joined, interpolated = fill_gaps(joined, args.fill_gaps)
    if not args.label_window:
        revoted = vote_tracks({tid: [(r['frame'], r['team']) for r in rows] for tid, rows in joined.items()})
        for tid, rows in joined.items():
            for row, (_, label) in zip(rows, revoted[tid]):
                row['team'] = label
    after = summarise_tracks({tid: [(r['frame'], r['team']) for r in rows] for tid, rows in joined.items()}, len(frames))
    everything = {**joined, **stands}
    label_counts = dict(Counter(str(rows[0]['team']) for rows in everything.values()))
    per_frame = [Counter(row['team'] for rows in everything.values() for row in rows if row['frame'] == i) for i in range(len(frames))]
    typical = {key: sorted(c.get(key, 0) for c in per_frame)[len(per_frame) // 2] for key in ('A', 'B', 'R', 'S', None)}
    result = {'clip': Path(args.clip).name, 'camera': args.camera, 'frames': len(frames), 'settings': TRACKER_SETTINGS,
              'summary': after, 'summary_before_joining': before, 'joins': joins, 'interpolated_rows': interpolated, 'track_label_counts': label_counts,
              'typical_people_per_frame': {str(k): v for k, v in typical.items()},
              'team_profile': {'file': Path(args.team_profile).name, 'created': profile['created'], 'letters': 'B = own team, A = opponent'} if profile else None,
              'note': ('team label = trained classifier summed over each track' if classifier else 'team label = colour rule voted per track') + (' with the colours of the team profile (--team-profile, mode %s)' % args.profile_mode if profile and classifier else ' of the team profile (--team-profile)' if profile else '')
                      + ', null when unclear; pixel coordinates; joins are a distance rule, unchecked',
              'tracks': {str(tid): rows for tid, rows in everything.items()}}
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')
    print('after ', json.dumps(after, ensure_ascii=False), '\njoins', joins, '| track labels', label_counts,
          '| typical people per frame', result['typical_people_per_frame'])


if __name__ == '__main__':
    main()
