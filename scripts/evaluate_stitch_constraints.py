"""Read-only second-pass stitching audit; no detection or identity accuracy claim.

Example: python scripts/evaluate_stitch_constraints.py --tracks tracks.json --links links.json --output audit.json
The deterministic constraint/holdout split is by SHA-256 of each unordered pair.
It is a pair holdout, not a match holdout: tracks and players can be shared.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.track_stitch import stitch_tracks


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def split_pairs(pairs):
    unique = {tuple(sorted((str(a), str(b)))) for a, b in pairs}
    ordered = sorted(unique, key=lambda p: hashlib.sha256(json.dumps(p).encode()).hexdigest())
    return ordered[::2], ordered[1::2]


def run(tracks_file, links_file, max_gap=8, max_overlap=3, margin=0.15):
    before = {str(p): digest(p) for p in (tracks_file, links_file)}
    tracks = json.loads(Path(tracks_file).read_text(encoding='utf-8'))['tracks']
    tracks = {k: rs for k, rs in tracks.items() if any(r['team'] in ('A', 'B') for r in rs)}
    links = json.loads(Path(links_file).read_text(encoding='utf-8'))
    constraints, heldout = split_pairs(links.get('different', []))
    same = [(str(a), str(b)) for a, b in links.get('same', [])]
    outputs = {}
    modes = {
        'baseline': {},
        'mutual': {'require_mutual': True, 'ambiguity_margin': margin},
        'split_constraints': {'require_mutual': True, 'ambiguity_margin': margin, 'different_pairs': constraints},
        'all_constraints_compliance_only': {'require_mutual': True, 'ambiguity_margin': margin, 'different_pairs': links.get('different', [])},
    }
    for mode, options in modes.items():
        mapped = {}
        merged, joins = stitch_tracks(tracks, max_gap=max_gap, max_overlap=max_overlap, membership=mapped, **options)
        metrics = {}
        for label, pairs in [('same', same), ('constraint_different', constraints), ('heldout_different', heldout)]:
            eligible = [(a, b) for a, b in pairs if a in mapped and b in mapped]
            metrics[label] = {'total': len(pairs), 'eligible': len(eligible), 'unmapped': len(pairs) - len(eligible),
                              'joined': sum(mapped[a] == mapped[b] for a, b in eligible)}
        outputs[mode] = {'joins': joins, 'output_tracks': len(merged), 'pairs': metrics}
    after = {str(p): digest(p) for p in (tracks_file, links_file)}
    if before != after:
        raise RuntimeError('Input files changed during evaluation; discard comparison and retry with a snapshot.')
    return {'input_sha256': before, 'inputs_unchanged': True, 'input_tracks': len(tracks),
            'settings': {'max_gap': max_gap, 'max_overlap': max_overlap, 'ambiguity_margin': margin},
            'split': 'unordered pairs SHA256 sorted, alternating constraint/holdout; not match-independent',
            'limitations': ['Second-pass evaluation on already stitched tracks; cannot measure prior identity switches.',
                            'Same pairs are not forced, but prior development saw these annotations; not a fresh blind test.',
                            'All-constraints results measure compliance, not heldout accuracy.'],
            'results': outputs}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tracks', type=Path, required=True)
    parser.add_argument('--links', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--max-gap', type=int, default=8)
    parser.add_argument('--max-overlap', type=int, default=3)
    parser.add_argument('--margin', type=float, default=0.15)
    args = parser.parse_args()
    if args.output and args.output.resolve() in (args.tracks.resolve(), args.links.resolve()):
        parser.error('Output must not overwrite an input.')
    report = run(args.tracks, args.links, args.max_gap, args.max_overlap, args.margin)
    encoded = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + '\n', encoding='utf-8')
    print(encoded)


if __name__ == '__main__':
    main()
