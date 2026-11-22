"""Separate role-model changes from position-guard changes on identical tracks."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from evaluate_position_recovery import evaluate, LegacyPositionGuard, LegacyDisplayPositionGuard


def compare(baseline, candidate):
    if not baseline or len(baseline) != len(candidate):
        raise ValueError('Complete paired traces with the same frame count required')
    for a, b in zip(baseline, candidate):
        if a['time'] != b['time'] or a['source_tracks'] != b['source_tracks']:
            raise ValueError('Time or detector/tracker outputs differ; role-only comparison invalid')
    results = {}
    for model, rows in [('baseline_role', baseline), ('candidate_role', candidate)]:
        results[model] = {
            'old_position_guard': evaluate(rows, LegacyPositionGuard, LegacyDisplayPositionGuard)['metrics'],
            'fixed_position_guard': evaluate(rows)['metrics'],
        }
    return {'identical_raw_tracking': True, 'frames': len(baseline), 'results': results,
            'identity_accuracy': None, 'true_position_error_m': None,
            'production_approved': False,
            'limits': ['Raw tracks are identical; role classifier does not improve identity association.',
                       'Speed violations measure continuity constraints, not ground-truth location error.',
                       'A missing observation is never filled by this evaluation.',
                       'Coaching replay does not establish tactical correctness.']}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('baseline', type=Path)
    parser.add_argument('candidate', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    contents = [p.read_bytes() for p in (args.baseline, args.candidate)]
    rows = [[json.loads(line) for line in raw.decode('utf-8').splitlines()] for raw in contents]
    result = compare(*rows)
    result['source_sha256'] = [hashlib.sha256(raw).hexdigest() for raw in contents]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
    print(json.dumps({'frames': result['frames'], 'identical_raw_tracking': True}))


if __name__ == '__main__':
    main()
