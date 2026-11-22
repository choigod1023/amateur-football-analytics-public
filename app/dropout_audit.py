"""Stage evidence for minimap losses; absence is not a confirmed missed player."""
from collections import Counter
import math


def overlap(a, b):
    ix=max(0.,min(a[2],b[2])-max(a[0],b[0]))
    iy=max(0.,min(a[3],b[3])-max(a[1],b[1]))
    aa=max(0.,a[2]-a[0])*max(0.,a[3]-a[1])
    ab=max(0.,b[2]-b[0])*max(0.,b[3]-b[1])
    return ix*iy/max(aa+ab-ix*iy,1e-9)


def visible(rows):
    return {str(p['id']): p for p in rows if isinstance(p.get('x'), (int, float))
            and isinstance(p.get('y'), (int, float)) and math.isfinite(p['x'])
            and math.isfinite(p['y']) and 0 <= p['x'] <= 1 and 0 <= p['y'] <= 1}


def analyse(frames):
    counts, stages, events = Counter(), Counter(), []
    raw_segment, previous, source_of = {}, {}, {}
    previous_t = None
    for frame in frames:
        t = float(frame['time'])
        if previous_t is not None and t <= previous_t:
            raise ValueError('Strictly increasing source times required')
        previous_t = t
        raw_boxes = {str(int(r[4])): r[:4] for r in frame['source_tracks']}
        for raw in raw_boxes:
            raw_segment.setdefault(raw, raw)
        for event in frame.get('identity_events', []):
            if event.get('action') == 'split':
                raw_segment[str(event['raw_id'])] = str(event['new_segment'])
        segment_raw = {raw_segment[r]: r for r in raw_boxes}
        aliases = {str(k): str(v) for k, v in frame.get('identity_aliases', {}).items()}
        raw_positions = {str(r[0]): team for team, rows in frame['raw_positions'].items() for r in rows}
        unlinked = {str(r['id']): r for r in frame.get('unlinked_players', frame['players'])}
        displayed = visible(frame['display_players'])
        outcomes = {str(r['id']): r for r in frame.get('track_outcomes', [])}
        for ident, old in previous.items():
            if ident in displayed:
                continue
            raw, segment = source_of.get(ident, (None, None))
            reason = 'low_confidence_recovery_expired' if old.get('recovered') else 'unmapped_display_observation'
            if raw is not None:
                current_segment = raw_segment.get(raw, raw)
                if raw not in raw_boxes:
                    reason = 'raw_tracker_observation_absent'
                elif current_segment != segment:
                    reason = 'identity_guard_segment_changed'
                elif aliases.get(segment, segment) != ident:
                    reason = 'reviewed_alias_changed'
                elif segment not in raw_positions:
                    outcome = outcomes.get(segment, {})
                    status = outcome.get('projection_status')
                    reason = {'team_excluded': 'team_vote_excluded',
                              'projection_rejected': 'pitch_projection_rejected'}.get(status, 'team_or_projection_unresolved')
                elif segment not in unlinked:
                    reason = 'position_guard_rejected'
                elif segment not in visible(list(unlinked.values())):
                    reason = 'dashboard_coordinate_outside_pitch'
                else:
                    reason = 'display_filter_or_coordinate_rejected'
            counts[reason] += 1
            evidence = None
            if reason == 'raw_tracker_observation_absent' and old.get('box') is not None and 'tracking_detections' in frame:
                best=max((overlap(old['box'],r[:4]) for r in frame['tracking_detections']), default=0.)
                tracked=max((overlap(old['box'],r) for r in raw_boxes.values()),default=0.)
                evidence={'detector_previous_box_max_iou':best,'tracker_previous_box_max_iou':tracked,
                          'nearby_detection':best>=.3,'nearby_other_track':tracked>=.3,
                          'identity_verified':False,
                          'limitation':'Previous-box overlap is a clue, not ground-truth detection recall or identity.'}
            events.append({'time': t, 'last_visible_time': old['time'], 'display_id': ident,
                           'raw_id': raw, 'segment_id': segment, 'reason': reason,
                           'before_box': old.get('box'), 'after_box': raw_boxes.get(raw),
                           'detection_evidence':evidence,
                           'identity_ground_truth': False})
        source_of = {}
        previous = {}
        for ident, player in displayed.items():
            segment = str(player.get('source_id', ident))
            if segment not in segment_raw:
                keys = [key for key, target in aliases.items() if target == ident]
                if len(keys) == 1:
                    segment = keys[0]
            raw = segment_raw.get(segment)
            source_of[ident] = (raw, segment)
            previous[ident] = {'time': t, 'box': raw_boxes.get(raw),
                               'recovered':player.get('observation_kind')=='low_confidence_recovery'}
        stages['frames'] += 1
        stages['source_track_observations'] += len(raw_boxes)
        stages['raw_position_observations'] += len(raw_positions)
        stages['position_guard_rejections'] += frame.get('position_rejected', 0)
        stages['display_observations'] += len(displayed)
        stages['coaching_capacity_blocked_frames'] += any(sum(p['team'] == team for p in unlinked.values()) > 11 for team in ('home', 'away'))
        stages['calibration_not_ready_frames'] += not frame.get('camera_ready', False)
        stages['diagnostic_outcome_frames'] += bool(frame.get('track_outcomes'))
    clues=Counter()
    for e in events:
        if e['detection_evidence'] is not None:
            d=e['detection_evidence']
            clues['with_nearby_detection' if d['nearby_detection'] else 'without_nearby_detection']+=1
            clues['with_nearby_other_track' if d['nearby_other_track'] else 'without_nearby_other_track']+=1
    return {'stage_totals': dict(stages), 'display_loss_events': len(events),
            'raw_absence_detection_clues':dict(clues),
            'reason_counts': dict(counts), 'events': events,
            'limits': ['Source tracker absence does not distinguish missed detection, association loss, occlusion, or leaving view.',
                       'Role/team and pixel position ground truth are not supplied by these logs.',
                       'Capacity blocks coaching, not the minimap. Counts are observation events, not unique people.',
                       'Browser display-only hold/interpolation is not included.']}


def reconnect_candidates(frames, limit=4):
    """Rank short geometry-compatible raw-ID boundaries; never label identity."""
    tracks, eligible = {}, {}
    for f in frames:
        t = float(f['time'])
        team = {str(r[0]): k for k, rows in f['raw_positions'].items() for r in rows}
        for r in f['source_tracks']:
            raw = str(int(r[4]))
            tracks.setdefault(raw, []).append({'time': t, 'box': list(r[:4])})
            if raw in team:
                eligible.setdefault(raw, []).append((t, team[raw]))
    candidates = []
    for a, before in tracks.items():
        if len(before) < 5 or a not in eligible:
            continue
        end, ba = before[-1]['time'], before[-1]['box']
        if end > frames[-1]['time'] - .4:
            continue
        for b, after in tracks.items():
            if a == b or len(after) < 5 or b not in eligible:
                continue
            start, bb = after[0]['time'], after[0]['box']
            gap = start - end
            if not 0 < gap <= 2.5:
                continue
            height = min(ba[3]-ba[1], bb[3]-bb[1])
            if height <= 0:
                continue
            distance = math.hypot((ba[0]+ba[2]-bb[0]-bb[2])/2, ba[3]-bb[3])/height
            if distance > 2.5:
                continue
            candidates.append({'a': a, 'b': b, 'end': end, 'start': start, 'before_box': ba,
                               'after_box': bb, 'gap_s': gap, 'foot_distance_heights': distance,
                               'before_team': eligible[a][-1][1], 'after_team': eligible[b][0][1],
                               'before_sequence': before[-5:], 'after_sequence': after[:5],
                               'reason': 'short_gap_geometry_candidate_identity_unverified'})
    candidates.sort(key=lambda r: (r['foot_distance_heights'] + r['gap_s']*.2))
    return candidates[:limit] if limit is not None else candidates
