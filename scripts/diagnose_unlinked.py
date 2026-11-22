"""Read-only diagnosis of labelled pairs and endpoint-evidence experiment.

All existing labels are development data, not an untouched accuracy test.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.track_stitch import stitch_tracks, _cost, _centre, _height, _observed_endpoint


def diagnose(snapshot):
    report = {'halves': {}, 'questions': [], 'limitations': ['Existing labels informed diagnosis; retrospective development evaluation, not blind accuracy.', 'Second-pass stitching cannot repair earlier within-track identity switches.']}
    hashes = {}
    for half, name in [('h1', 'h1_v3.json'), ('h2', 'h2_ov3.json')]:
        paths = [snapshot / name, snapshot / f'snapshot/players/links/{half}.json']
        for p in paths:
            hashes[str(p)] = hashlib.sha256(p.read_bytes()).hexdigest()
        data = json.loads(paths[0].read_text(encoding='utf-8'))
        labels = json.loads(paths[1].read_text(encoding='utf-8'))
        tracks = {k: v for k, v in data['tracks'].items() if any(r['team'] in ('A', 'B') for r in v)}
        outputs = {}
        for mode in ['baseline', 'endpoint_evidence']:
            mapping = {}
            merged, joins = stitch_tracks(tracks, 8, 3, require_mutual=True, endpoint_evidence=mode != 'baseline', membership=mapping)
            outputs[mode] = {'joins': joins, 'pairs': {}}
            for relation, pairs in labels.items():
                eligible = [(a, b) for a, b in pairs if a in mapping and b in mapping]
                outputs[mode]['pairs'][relation] = {'total': len(pairs), 'eligible': len(eligible), 'joined': sum(mapping[a] == mapping[b] for a, b in eligible)}
        diagnoses = []
        for a, b in labels['same']:
            if a not in tracks or b not in tracks:
                diagnoses.append({'a': a, 'b': b, 'reason': 'missing_track'})
                continue
            if tracks[a][0]['frame'] > tracks[b][0]['frame']:
                a, b = b, a
            aa, bb = tracks[a], tracks[b]
            observed_a = {r['frame']: r for r in aa if not r.get('interpolated')}
            observed_b = {r['frame']: r for r in bb if not r.get('interpolated')}
            common = sorted(observed_a.keys() & observed_b.keys())
            distances = [(f, math.dist(_centre(observed_a[f]['box']), _centre(observed_b[f]['box'])) /
                          ((_height(observed_a[f]['box']) + _height(observed_b[f]['box'])) / 2)) for f in common]
            gap = bb[0]['frame'] - aa[-1]['frame']
            collapsed = len(_observed_endpoint(aa)) < len(observed_a)
            reason = ('simultaneous_separate_observations' if common and statistics.median(d for _, d in distances) > .5 else
                      'overlapping_track_intervals' if gap <= 0 else
                      'collapsed_terminal_box' if collapsed else 'gap_exceeds_limit' if gap > 8 else 'candidate_geometry_or_competition')
            item = {'a': a, 'b': b, 'reason': reason, 'gap_frames': gap, 'common_observed_frames': len(common),
                    'median_distance_body_heights': statistics.median(d for _, d in distances) if distances else None,
                    'before_end': data['first_second'] + aa[-1]['frame'] / data['fps'],
                    'after_start': data['first_second'] + bb[0]['frame'] / data['fps'],
                    'before_box': aa[-1]['box'], 'after_box': bb[0]['box']}
            diagnoses.append(item)
            # Do not repeat the existing same/different question. Ask about a
            # concrete conflicting frame inside a long previously linked piece.
            if len(common) > 30 and item['median_distance_body_heights'] > 2 and not any(q['half'] == half for q in report['questions']):
                f, _ = distances[len(distances) // 2]
                report['questions'].append({'half': half, 'kind': 'within_track_conflict', 'a': a, 'b': b,
                    'time': data['first_second'] + f / data['fps'], 'boxes': [observed_a[f]['box'], observed_b[f]['box']],
                    'prompt': '이전의 같은 사람 답은 유지합니다. 이 특정 순간에는 두 상자가 서로 다른 위치에 있습니다. 각각 선수를 따라가고 있나요, 한쪽이 관중·심판·오탐인가요?',
                    'reason': reason})
        report['halves'][half] = {'evaluation': outputs, 'same_pair_diagnoses': diagnoses}
        known = {frozenset((a, b)) for pairs in labels.values() for a, b in pairs}
        possibilities = []
        for a, aa in tracks.items():
            if len(aa) < 30 or aa[-1]['team'] != 'B':
                continue
            nearby = []
            for b, bb in tracks.items():
                if a == b or len(bb) < 30 or bb[0]['team'] != 'B' or frozenset((a, b)) in known:
                    continue
                cost = _cost(aa, bb, 8, 3)
                if cost is not None:
                    nearby.append((cost, b))
            nearby.sort()
            if len(nearby) >= 2 and nearby[1][0] - nearby[0][0] <= .15:
                possibilities.append((nearby[1][0] - nearby[0][0], a, nearby[:2]))
        if possibilities:
            margin, a, choices = sorted(possibilities)[0]
            b = choices[0][1]
            aa, bb = tracks[a], tracks[b]
            report['questions'].append({'half': half, 'kind': 'ambiguous_successor', 'a': a, 'b': b,
                'time': data['first_second'] + bb[0]['frame'] / data['fps'],
                'before_end': data['first_second'] + aa[-1]['frame'] / data['fps'],
                'after_start': data['first_second'] + bb[0]['frame'] / data['fps'],
                'boxes': [aa[-1]['box'], bb[0]['box']], 'alternative': choices[1][1], 'cost_margin': margin,
                'prompt': '앞 장면의 선수가 뒤 장면의 첫 번째 후보로 이어지나요? 다른 후보도 비슷해 자동 연결을 보류했습니다.',
                'reason': 'two_nearly_equal_successors'})
    report['input_sha256'] = hashes
    report['inputs_unchanged'] = all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == sha for p, sha in hashes.items())
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('snapshot', type=Path)
    p.add_argument('output', type=Path)
    args = p.parse_args()
    if args.output.resolve().is_relative_to(args.snapshot.resolve()):
        p.error('Write outside the frozen snapshot.')
    report = diagnose(args.snapshot)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({h: v['evaluation'] for h, v in report['halves'].items()}))


if __name__ == '__main__':
    main()
