"""Audit pair agreement using explicit membership, without promoting it to identity accuracy."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.track_stitch import stitch_tracks, _observed_endpoint, _cost


def pair_agreement(labels, membership):
    result = {}
    for relation in ('same', 'different'):
        cases = []
        for a, b in labels.get(relation, []):
            mapped = a in membership and b in membership
            cases.append({'a': a, 'b': b, 'status': 'mapped' if mapped else 'missing_source',
                          'joined': membership[a] == membership[b] if mapped else None})
        result[relation] = {'total': len(cases), 'mapped': sum(c['status'] == 'mapped' for c in cases),
                            'joined': sum(c['joined'] is True for c in cases),
                            'unresolved': sum(c['joined'] is None for c in cases), 'cases': cases}
    return result


def audit(snapshot):
    report = {'halves': {}, 'input_sha256': {}, 'metric': 'agreement_with_existing_whole_track_answers',
              'is_identity_accuracy': False,
              'limitations': ['Existing answers and tracks informed development; not an independent evaluation.',
                             'Whole-track answers may refer to a different time than a candidate splice.',
                             'A mismatch is not proven identity error without frame-scoped ground truth.']}
    for half, name in [('h1', 'h1_v3.json'), ('h2', 'h2_ov3.json')]:
        track_path = snapshot / name
        label_path = snapshot / f'snapshot/players/links/{half}.json'
        for path in (track_path, label_path):
            report['input_sha256'][str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
        data = json.loads(track_path.read_text(encoding='utf-8'))
        labels = json.loads(label_path.read_text(encoding='utf-8'))
        tracks = {t: rs for t, rs in data['tracks'].items() if any(r['team'] in ('A', 'B') for r in rs)}
        origins = {id(row): t for t, rs in tracks.items() for row in rs}
        membership = {}
        output, joins = stitch_tracks(tracks, 8, 3, require_mutual=True, endpoint_evidence=True,
                                      endpoint_team_guard=True, membership=membership)
        legacy = {origins[id(row)]: t for t, rs in output.items() for row in rs}
        report['halves'][half] = {'joins': joins, 'nonempty_sources': len(tracks),
            'membership_count': len(membership), 'surviving_row_mapping_count': len(legacy),
            'swallowed_sources': sorted(set(membership)-set(legacy)),
            'explicit_membership': pair_agreement(labels, membership),
            'surviving_rows_only': pair_agreement(labels, legacy)}
        if half == 'h1':
            a, b = _observed_endpoint(tracks['5574']), _observed_endpoint(tracks['6182'], True)
            report['remaining_negative_pair'] = {
                'a': '5574', 'b': '6182', 'gap_frames': b[0]['frame'] - a[-1]['frame'],
                'end_time': data['first_second'] + a[-1]['frame']/data['fps'],
                'start_time': data['first_second'] + b[0]['frame']/data['fps'],
                'end_box': a[-1]['box'], 'start_box': b[0]['box'],
                'normalized_cost': _cost(a, b, 8, 3),
                'visual_review': 'The boundary images show a fluorescent-shirt person at nearly the same location. This supports geometric continuity, not verified individual identity over both whole tracks.',
                'action': 'Preserve the different answer; do not tune a threshold to reject this splice solely to fit that answer.',
                'required_ground_truth': 'Frame-scoped identity continuity through the original pieces, especially overlaps with other people.'}
    report['inputs_unchanged'] = all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == sha for p, sha in report['input_sha256'].items())
    return report


def main():
    p = argparse.ArgumentParser()
    p.add_argument('snapshot', type=Path)
    p.add_argument('output', type=Path)
    args = p.parse_args()
    result = audit(args.snapshot)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
    print(json.dumps({h: {'sources': r['membership_count'], 'swallowed': len(r['swallowed_sources']),
                         'same_joined': r['explicit_membership']['same']['joined'],
                         'different_joined': r['explicit_membership']['different']['joined']} for h, r in result['halves'].items()}))


if __name__ == '__main__':
    main()
