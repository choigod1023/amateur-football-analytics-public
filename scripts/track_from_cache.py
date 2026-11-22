"""Track and label the people of a stretch whose detections were cached by scripts/cache_detections.py.

Usage: python scripts/track_from_cache.py <cache folder> <classifier model.pt> <output.json>
       [--confidence 0.10] [--start-threshold 0.12] [--min-track-length 10] [--fill-gaps 8] [--label-window 0]
       [--from-second S] [--to-second E]

No video and no detector are needed, so a run takes seconds to minutes and can be repeated with other settings or another
classifier. The output has the same format as scripts/track_review_clip.py, with frames counted from the first cached chunk
(or from --from-second), so scripts/build_team_minimap.py can read it. Positions are pixels.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.profile_teams import MODES, OfflineTeams, profile_probabilities  # noqa: E402
from app.team_color_profile import load_profile  # noqa: E402
from app.team_role_features import FEATURE_NAMES  # noqa: E402
from app.team_role_infer import load_model, predict  # noqa: E402
from app.track_pipeline import backfill_births, finalize_tracks  # noqa: E402
from app.track_vote import TRACKER_SETTINGS  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('cache')
    parser.add_argument('classifier')
    parser.add_argument('output')
    parser.add_argument('--confidence', type=float, default=0.10)
    parser.add_argument('--start-threshold', type=float, default=0.12)
    parser.add_argument('--min-track-length', type=int, default=10)
    parser.add_argument('--fill-gaps', type=int, default=25, help='gaps up to this many frames inside a track are filled by interpolation (marked); above 8 the double rows and the team size are checked again afterwards')
    parser.add_argument('--label-window', type=int, default=8, help='frames on each side used to label every row (0 = one label per track)')
    parser.add_argument('--team-size', type=int, default=11, help='no frame may show more players of one team than this (0 = no limit)')
    parser.add_argument('--backfill', type=int, default=3, help='frames before the first reported row of a track in which its birth detection is added back (0 = off)')
    parser.add_argument('--stitch-gap', type=int, default=25, help='longest gap (frames) between two track pieces that may still be joined as one person')
    parser.add_argument('--track-buffer', type=int, help='frames a lost track is kept alive by the tracker (default: the setting of app/track_vote.py)')
    parser.add_argument('--stitch-overlap', type=int, default=0, help='frames two track pieces may overlap and still be joined (the births added back by --backfill make 1 to 3)')
    parser.add_argument('--team-profile', help='team_profile.json of /team-select: the own team (letter B) and the opponent (letter A) follow the colours the coach chose; the shirt colour is the mean colour kept in the cache, which is less exact than the picture')
    parser.add_argument('--profile-mode', choices=MODES, default='fallback', help='with --team-profile: fallback = the profile first, the trained model only where the profile is unclear (default, safe in other clothes); profile = profile only; model = the model first (best in the match it was trained on, 5.5 percent wrong with an own team in orange vests, see wiki/team-select.md)')
    parser.add_argument('--guarded-stitch', action='store_true', help='require unambiguous mutual candidates; evaluate before promoting')
    parser.add_argument('--from-second', type=float)
    parser.add_argument('--to-second', type=float)
    args = parser.parse_args()
    import numpy as np
    from ultralytics.engine.results import Boxes
    from ultralytics.trackers.byte_tracker import BYTETracker
    from ultralytics.utils import IterableSimpleNamespace, YAML
    from ultralytics.utils.checks import check_yaml

    files = sorted(Path(args.cache).glob('chunk_*.npz'))
    if not files:
        raise SystemExit('No chunk_*.npz files in the cache folder')
    classifier = load_model(args.classifier)
    profile = load_profile(args.team_profile) if args.team_profile else None
    if args.team_profile and profile is None:
        raise SystemExit(f'Team profile file not found: {args.team_profile}. Choose the own team on /team-select first, or run without --team-profile.')
    teams = OfflineTeams(profile) if profile else None
    mode = args.profile_mode

    def probabilities_of(rows):
        probabilities = predict(classifier, np.asarray(rows))
        if teams is None:
            return probabilities
        return np.array([profile_probabilities(teams, row, classifier['classes'], p, mode) for row, p in zip(rows, probabilities)])
    config = IterableSimpleNamespace(**YAML.load(check_yaml('bytetrack.yaml')))
    for key, value in TRACKER_SETTINGS.items():
        setattr(config, key, value)
    if args.track_buffer:
        config.track_buffer = args.track_buffer
    config.track_high_thresh = config.new_track_thresh = args.start_threshold
    config.track_low_thresh = min(config.track_low_thresh, args.start_threshold / 2)
    tracker = BYTETracker(args=config)
    neon_index = list(FEATURE_NAMES).index('neon')
    first = float(np.load(files[0])['start']) if args.from_second is None else args.from_second
    fps = float(np.load(files[0])['fps'])
    camera = str(np.load(files[0])['camera'])
    tracks, class_scores, neon_shares = {}, {}, {}
    detections = {}
    total = 0
    for path in files:
        data = np.load(path)
        offset = int(round((float(data['start']) - first) * fps))
        count = int(data['frame_count'])
        if args.to_second is not None and float(data['start']) >= args.to_second:
            break
        if offset + count <= 0:
            continue
        keep = data['scores'] >= args.confidence
        frames, boxes, scores, feats = data['frames'][keep], data['boxes'][keep], data['scores'][keep], data['feats'][keep]
        for local in range(count):
            index = offset + local
            if index < 0:
                continue
            pick = np.where(frames == local)[0]
            array = np.concatenate([boxes[pick], scores[pick, None], np.zeros((len(pick), 1), np.float32)], axis=1).astype(np.float32).reshape(-1, 6)
            detections[index] = [(box, feat) for box, feat in zip(boxes[pick].tolist(), feats[pick])]
            tracked = tracker.update(Boxes(array, (1080, 1920)), None)
            if len(tracked):
                probabilities = probabilities_of(feats[pick][[int(r[7]) for r in tracked]])
                for k, row in enumerate(tracked):
                    tid = int(row[4])
                    tracks.setdefault(tid, []).append((index, [float(v) for v in row[:4]]))
                    class_scores.setdefault(tid, []).append(probabilities[k])
                    neon_shares.setdefault(tid, []).append(0.0 if teams is not None else float(feats[pick][int(row[7])][neon_index]))
            total = max(total, index + 1)
    added = backfill_births(tracks, class_scores, neon_shares, detections, lambda rows: probabilities_of(np.array(rows)), lambda row: 0.0 if teams is not None else float(row[neon_index]), args.backfill) if args.backfill else 0
    result = finalize_tracks(tracks, class_scores, neon_shares, classifier['classes'], total, args.label_window, args.min_track_length, args.fill_gaps, args.team_size or None, args.stitch_gap, args.stitch_overlap, guarded_stitch=args.guarded_stitch)
    output = {'clip': Path(args.cache).name, 'camera': camera, 'frames': total, 'settings': TRACKER_SETTINGS, 'summary': result['summary'],
              'joins': result['joins'], 'interpolated_rows': result['interpolated_rows'], 'rows_capped_by_team_size': result['rows_capped_by_team_size'], 'backfilled_rows': added, 'first_second': first, 'fps': fps,
              'team_profile': {'file': Path(args.team_profile).name, 'created': profile['created'], 'mode': mode, 'letters': 'B = own team, A = opponent'} if profile else None,
              'note': 'tracked from cached detections; team label = classifier probabilities' + (f' decided by the team profile (mode {mode})' if profile else '') + '; pixel coordinates; unverified',
              'tracks': {str(tid): rows for tid, rows in result['tracks'].items()}}
    Path(args.output).write_text(json.dumps(output, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(result['summary'], ensure_ascii=False), '| joins', result['joins'], '| backfilled', added, '| frames', total)


if __name__ == '__main__':
    main()
