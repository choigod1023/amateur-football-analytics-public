"""Helpers for player tracks on short, low frame rate clips.

A colour guess made on a single frame flips often (shadows, partial occlusion). Within one track the guess is
therefore replaced by the majority of the track, and the summary reports how unstable the tracks still are.
Nothing here is checked against human labels: the numbers describe track length and colour agreement only.
"""
from collections import Counter

# Settings found by comparing six combinations on two 10 s clips (cam1 b03, cam3 b09); fewer, longer tracks than the
# defaults, but still more tracks than the roughly 20 people on the pitch.
TRACKER_SETTINGS = {'track_buffer': 50, 'match_thresh': 0.98, 'track_high_thresh': 0.3, 'track_low_thresh': 0.05}
SPECTATOR = 'S'


def majority_label(labels, minimum_share=0.5):
    """Most common team label of one track, or None when no label reaches the share (ties count as unclear)."""
    counts = Counter(label for label in labels if label != SPECTATOR and label is not None)
    if not counts:
        return None
    ranked = counts.most_common(2)
    if len(ranked) > 1 and ranked[0][1] == ranked[1][1]:
        return None
    label, count = ranked[0]
    return label if count / sum(counts.values()) >= minimum_share else None


def is_person_track(labels):
    """A track belongs to a person on the pitch when at least half of its frames were not judged to be spectators."""
    labels = list(labels)
    return bool(labels) and sum(1 for label in labels if label != SPECTATOR) >= len(labels) / 2


def summarise_tracks(tracks, clip_frames):
    """tracks: {track id: [(frame index, label), ...]}. Returns counts that show how fragmented the tracks are."""
    people = {tid: rows for tid, rows in tracks.items() if is_person_track(label for _, label in rows)}
    lengths = sorted(len(rows) for rows in people.values())
    changed = 0
    agreement = []
    for rows in people.values():
        counts = Counter(label for _, label in rows if label != SPECTATOR)
        if len(counts) > 1:
            changed += 1
        if counts:
            agreement.append(max(counts.values()) / sum(counts.values()))
    middle = lengths[len(lengths) // 2] if lengths else 0
    return {'person_tracks': len(people), 'long_tracks': sum(1 for n in lengths if n >= clip_frames / 2),
            'median_length': middle, 'tracks_with_colour_change': changed,
            'mean_colour_agreement': round(sum(agreement) / len(agreement), 3) if agreement else None}


def vote_tracks(tracks):
    """Replace the per-frame team label by the majority of its track. Unclear tracks get None, never a guess."""
    voted = {}
    for tid, rows in tracks.items():
        label = majority_label(label for _, label in rows)
        voted[tid] = [(frame, SPECTATOR if original == SPECTATOR else label) for frame, original in rows]
    return voted


def drop_short_tracks(tracks, minimum_frames):
    """Keep only tracks with at least `minimum_frames` rows. tracks: {id: [rows]}. Short tracks are mostly detector flicker
    (shadows, lines, objects at the edge); a real player stays in view for a second or more."""
    return {tid: rows for tid, rows in tracks.items() if len(rows) >= minimum_frames}
