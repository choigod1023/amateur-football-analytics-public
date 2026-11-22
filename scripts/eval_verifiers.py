"""Join the verifier scores (scripts/score_verifiers.py) with the human judgements and report AUC and the precision of an accept rule (research only).

python scripts/eval_verifiers.py <crops folder> <scores.json>

AUC of every model on all 120 judged boxes, on the 'in scope' boxes of the auto-labeller judge (found by one detector, score 0.35 to 0.45), and the detection-score baseline.
Accept rule: the lowest score threshold at which at least 95 % of the accepted boxes were people, with the number accepted, the 95 % Wilson lower bound and the number of boxes rejected
at a threshold where at least 90 % of the rejected were not people. Thresholds are chosen on the same boxes they are measured on, so the numbers are optimistic; they only say which model is worth a nested test.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.auto_labeller import auc, wilson_lower, in_scope  # noqa: E402


def best_accept(scores, labels, target=0.95):
    order = sorted(set(scores), reverse=True)
    best = None
    for t in order:
        chosen = [l for s, l in zip(scores, labels) if s >= t]
        if len(chosen) >= 5 and sum(chosen) / len(chosen) >= target:
            best = (t, sum(chosen), len(chosen))
    return best


def best_reject(scores, labels, target=0.90):
    best = None
    for t in sorted(set(scores)):
        chosen = [1 - l for s, l in zip(scores, labels) if s <= t]
        if len(chosen) >= 5 and sum(chosen) / len(chosen) >= target:
            best = (t, sum(chosen), len(chosen))
    return best


def main():
    folder, scores_path = Path(sys.argv[1]), Path(sys.argv[2])
    manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
    scores = {int(k): v for k, v in json.loads(scores_path.read_text(encoding='utf-8')).items()}
    rows = [dict(m, **scores[m['n']]) for m in manifest if m['n'] in scores]
    models = sorted({k for r in rows for k in r if k in ('gdino', 'owl', 'siglip')})
    for scope_name, keep in (('전체', lambda r: True), ('판정기 적용 범위(점수 0.35~0.45, 한쪽 모델만)', lambda r: in_scope(r['score'], r['found_by'])), ('범위 밖', lambda r: not in_scope(r['score'], r['found_by']))):
        sub = [r for r in rows if keep(r)]
        label = [1 if r['label'] == 'ok' else 0 for r in sub]
        print(f'\n[{scope_name}] {len(sub)}개 (사람 {sum(label)}개)')
        print(f'  검출 점수만 (기준선)  AUC {auc([r["score"] for r in sub], label):.2f}')
        for name in models:
            s = [r[name] for r in sub]
            a, rj = best_accept(s, label), best_reject(s, label)
            acc = f'수락 {a[1]}/{a[2]} (하한 {wilson_lower(a[1], a[2]):.0%}, 문턱 {a[0]:.2f})' if a else '수락 불가'
            rej = f'기각 {rj[1]}/{rj[2]}' if rj else '기각 불가'
            print(f'  {name:7s} AUC {auc(s, label):.2f} | {acc} | {rej}')


if __name__ == '__main__':
    main()
