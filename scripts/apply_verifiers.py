"""Turn verifier scores into accept / reject / ask for the auto-labeller candidates (research only; machine labels, never mixed with human labels).

python scripts/apply_verifiers.py <judged crops folder> <judged scores.json> <candidate crops folder> <candidate scores.json> <output folder> [--accept-target 0.98]

A logistic model on the two verifier scores (owl, gdino) is fitted on the 120 boxes a human judged; its accept and reject thresholds come from out-of-fold probabilities (time blocks of 120 s,
the same procedure as scripts/auto_labeller.py). The model is applied to the candidates and every row is written to <output>/decisions.jsonl with origin 'verifier_owl_gdino' and the old
auto-labeller decision next to it, so the two judges can be compared. <output>/judge.json keeps the model and thresholds, <output>/summary.json the counts.
Only candidates in the judged score range carry a validated decision; anything else would be copied with decision 'ask'.
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.auto_labeller import Ridge, decide, oof_probabilities, pick_thresholds, time_groups  # noqa: E402

MODELS = ('owl', 'gdino')
ORIGIN = 'verifier_owl_gdino'


def features(manifest, scores):
    return np.array([[scores[str(m['n'])][k] for k in MODELS] for m in manifest], dtype=float)


def main():
    parser = argparse.ArgumentParser()
    for name in ('judged', 'judged_scores', 'candidates', 'candidate_scores', 'output'):
        parser.add_argument(name)
    parser.add_argument('--accept-target', type=float, default=0.98)
    parser.add_argument('--reject-target', type=float, default=0.90)
    parser.add_argument('--lam', type=float, default=1.0)
    parser.add_argument('--accept-p', type=float, help='fixed accept probability instead of the threshold found by pick_thresholds (a wider ask band is safer on new data)')
    parser.add_argument('--reject-p', type=float, help='fixed reject probability, see --accept-p')
    args = parser.parse_args()
    judged = json.loads((Path(args.judged) / 'manifest.json').read_text(encoding='utf-8'))
    candidates = json.loads((Path(args.candidates) / 'manifest.json').read_text(encoding='utf-8'))
    x = features(judged, json.loads(Path(args.judged_scores).read_text(encoding='utf-8')))
    y = np.array([1.0 if m['label'] == 'ok' else 0.0 for m in judged])
    groups = time_groups([m['time'] for m in judged])
    oof = oof_probabilities(x, y, groups, args.lam, folds=4)
    hi, lo = pick_thresholds(oof, y, accept_target=args.accept_target, reject_target=args.reject_target)
    if args.accept_p is not None:
        hi = args.accept_p
    if args.reject_p is not None:
        lo = args.reject_p
    model = Ridge(args.lam).fit(x, y)
    xc = features(candidates, json.loads(Path(args.candidate_scores).read_text(encoding='utf-8')))
    p = model.predict(xc)
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    rows, counts = [], Counter()
    for m, pi, s in zip(candidates, p, xc):
        decision = decide(float(pi), hi, lo) if m['in_scope'] else 'ask'
        counts[(m['source'], decision)] += 1
        rows.append({'source': m['source'], 'frame': m['frame'], 'time': m['time'], 'camera': m['camera'], 'box': m['box'], 'score': m['score'], 'found_by': m['found_by'],
                     'in_scope': m['in_scope'], 'p_person': round(float(pi), 4), 'owl': round(float(s[0]), 4), 'gdino': round(float(s[1]), 4), 'decision': decision,
                     'old_decision': m['old_decision'], 'origin': ORIGIN})
    (out / 'decisions.jsonl').write_text('\n'.join(json.dumps(r) for r in rows) + '\n', encoding='utf-8')
    (out / 'judge.json').write_text(json.dumps({'models': MODELS, 'ridge': model.to_json(), 'accept': hi, 'reject': lo, 'accept_target': args.accept_target, 'reject_target': args.reject_target,
                                                 'trained_on': len(judged)}), encoding='utf-8')
    summary = {f'{src}/{dec}': n for (src, dec), n in sorted(counts.items())}
    agree = Counter((r['old_decision'], r['decision']) for r in rows)
    summary['old_vs_new'] = {f'{a}->{b}': n for (a, b), n in sorted(agree.items())}
    (out / 'summary.json').write_text(json.dumps(summary, indent=1), encoding='utf-8')
    print(json.dumps(summary, indent=1), '\nthresholds accept', hi, 'reject', lo)


if __name__ == '__main__':
    main()
