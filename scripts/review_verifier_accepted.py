"""Put a random sample of the verifier-accepted boxes into /alerts as a human check (research only).

python scripts/review_verifier_accepted.py <decisions.jsonl> <video> <review store> <session name> [--count 30] [--seed 33]

The accepted boxes (origin verifier_owl_gdino) are the machine labels that may go into training only if at least 30 sampled ones are people at 95 % or better (CLAUDE.md).
Uses the same session writer as scripts/auto_labeller.py review-accepted; an existing session is never overwritten. Nothing is written to the human labels.
"""
import importlib.util
import json
import random
import sys
from pathlib import Path


def main():
    args = [a for a in sys.argv[1:]]
    count, seed = 30, 33
    if '--count' in args:
        i = args.index('--count'); count = int(args[i + 1]); del args[i:i + 2]
    if '--seed' in args:
        i = args.index('--seed'); seed = int(args[i + 1]); del args[i:i + 2]
    if len(args) != 4:
        raise SystemExit(__doc__)
    decisions, video, store, session = args
    spec = importlib.util.spec_from_file_location('auto_labeller_script', Path(__file__).resolve().parent / 'auto_labeller.py')
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    spec.loader.exec_module(module)
    import cv2
    rows = [json.loads(x) for x in Path(decisions).read_text(encoding='utf-8').splitlines() if x.strip()]
    accepted = [r for r in rows if r['decision'] == 'accept']
    sample = sorted(random.Random(seed).sample(accepted, min(count, len(accepted))), key=lambda r: r['time'])
    module.put_session(cv2, cv2.VideoCapture(video), Path(store), session, sample, note='(외부 검증 모델 OWLv2와 Grounding DINO가 사람이라고 자동 수락한 상자의 표본 검수입니다: 사람이 아니라고 판정하면 그 상자는 학습에 쓰지 않습니다)')


if __name__ == '__main__':
    main()
