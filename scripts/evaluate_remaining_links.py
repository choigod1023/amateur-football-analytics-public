"""Evaluate remaining links without modifying data or treating pair answers as stitch constraints."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.track_stitch import stitch_tracks, _observed_endpoint, _local_team


def evaluate(snapshot):
    hashes = {}
    results = {}
    for half, filename in [('h1', 'h1_v3.json'), ('h2', 'h2_ov3.json')]:
        track_file = snapshot / filename
        labels_file = snapshot / f'snapshot/players/links/{half}.json'
        for p in (track_file, labels_file):
            hashes[str(p)] = hashlib.sha256(p.read_bytes()).hexdigest()
        data = json.loads(track_file.read_text(encoding='utf-8'))
        labels = json.loads(labels_file.read_text(encoding='utf-8'))
        tracks = {t: rs for t, rs in data['tracks'].items() if any(r['team'] in ('A', 'B') for r in rs)}
        modes = {}
        for mode, gap, guard in [('prior_endpoint', 8, False), ('local_team_guard', 8, True),
                                 ('gap10_experiment', 10, False), ('gap10_with_team_guard', 10, True),
                                 ('gap25_experiment', 25, False)]:
            mapping = {}
            output, joins = stitch_tracks(tracks, gap, 3, require_mutual=True, endpoint_evidence=True, endpoint_team_guard=guard, membership=mapping)
            pairs = {}
            for relation, rows in labels.items():
                eligible = [(a, b) for a, b in rows if a in mapping and b in mapping]
                joined = [[a, b] for a, b in eligible if mapping[a] == mapping[b]]
                pairs[relation] = {'total': len(rows), 'eligible': len(eligible), 'joined': len(joined), 'joined_pairs': joined}
            modes[mode] = {'joins': joins, 'pairs': pairs}
        remaining = []
        prior_joined = {frozenset(p) for p in modes['prior_endpoint']['pairs']['same']['joined_pairs']}
        for a, b in labels['same']:
            if frozenset((a, b)) in prior_joined or a not in tracks or b not in tracks:
                continue
            first, second = tracks[a], tracks[b]
            if first[0]['frame'] > second[0]['frame']:
                a, b, first, second = b, a, second, first
            first, second = _observed_endpoint(first), _observed_endpoint(second, True)
            gap = second[0]['frame']-first[-1]['frame']
            ta, tb = _local_team(first[-5:]), _local_team(second[:5])
            remaining.append({'a': a, 'b': b, 'gap_frames': gap, 'end_team': ta, 'start_team': tb,
                'reason': 'overlapping_intervals_need_segment_identity' if gap <= 0 else
                          'endpoint_team_conflict' if ta and tb and ta != tb else
                          'gap_or_geometry_requires_new_evidence'})
        results[half] = {'modes': modes, 'remaining': remaining}
    unchanged = all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == value for p, value in hashes.items())
    return {'halves': results, 'input_sha256': hashes, 'inputs_unchanged': unchanged,
            'limitations': ['Development labels previously inspected; no independent accuracy claim.',
                           'Increasing gap recovered one labelled same pair with contradictory endpoint team votes; not promoted.',
                           'Endpoint team votes can be wrong; guard abstains instead of reassigning identities.',
                           'Local guard reduced unverified cross-team joins, but measured same/different accuracy did not improve.']}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('snapshot', type=Path)
    p.add_argument('output', type=Path)
    args = p.parse_args()
    result = evaluate(args.snapshot)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
    print(json.dumps({h: {m: {'joins':v['joins'], 'same':v['pairs']['same']['joined'], 'different':v['pairs']['different']['joined']} for m,v in r['modes'].items()} for h,r in result['halves'].items()}))


if __name__ == '__main__':
    main()
