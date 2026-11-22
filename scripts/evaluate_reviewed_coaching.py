"""Respect human scene preferences; never turn a preferred bundle into event labels."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from app.difference_review import fingerprint
from app.live_feedback import LiveAnalyzer
from app.pitch_map import fit
from build_tactical_report import metre_rows
from build_team_minimap import parse_schedule


def evaluate(work):
    source = work / 'human-labels/public-own-match-review-20261111/differences'
    queue = json.loads((source / 'queue.json').read_text(encoding='utf-8'))
    files = [source / 'queue.json', *sorted((source / 'answers').glob('*.json'))]
    hashes = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    valid, rejected = [], []
    for item in queue['items']:
        p = source / 'answers' / f"{item['id']}.json"
        if not p.exists():
            continue
        answer = json.loads(p.read_text(encoding='utf-8'))
        if answer.get('fingerprint') != fingerprint(item) or answer.get('source') != 'human':
            rejected.append(item['id'])
            continue
        valid.append((item, answer))
    snapshot = work / 'evidence-policy-eval-20261113'
    data = json.loads((snapshot / 'h2_ov3.json').read_text(encoding='utf-8'))
    calibration = json.loads((snapshot / 'snapshot/calibration/calibrations.json').read_text(encoding='utf-8'))['cam3']
    fitted = fit(calibration)
    frames, _ = metre_rows(data['tracks'], fitted, parse_schedule('0:-1.8,6.8;1950:0.3,0.3'),
                           (1.003087, -.001614, -7.41, 5.61), 0, data['frames'])
    analyzer = LiveAnalyzer(1, fitted['pitch']['length'], fitted['pitch']['width'], data['fps'])
    alerts = []
    for f in range(data['frames']):
        teams = frames.get(f, {})
        alerts += analyzer.update(data['first_second'] + f / data['fps'], teams.get('B', []), teams.get('A', []))
    scenes = []
    for item, answer in valid:
        latest = [a for a in alerts if abs(a['time'] - item['time']) <= 5]
        preferred = item.get(answer['verdict'] + '_events') if answer['verdict'] in ('before', 'after') else None
        match = set(a['kind'] for a in latest) == set(a['kind'] for a in preferred) if preferred is not None else None
        scenes.append({'id': item['id'], 'time': item['time'], 'verdict': answer['verdict'],
                       'preferred_events': preferred, 'candidate_events': latest,
                       'candidate_kind_set_matches_preferred': match,
                       'requires_new_text_review': any(a['kind'] == 'line_drop' and not a['evidence'].get('retreat_supported') for a in latest)})
    counts = Counter(a['verdict'] for _, a in valid)
    decisive = counts['before'] + counts['after']
    return {'valid_answers': len(valid), 'rejected_stale_answers': rejected, 'preferences': dict(counts),
            'after_preference_share_among_decisive': counts['after'] / decisive if decisive else None,
            'interpretation': 'Scene bundle preference, not per-event precision. Used for development, not independent evaluation.',
            'candidate_alert_count': len(alerts), 'scenes': scenes,
            'answer_sha256': hashes, 'answers_unchanged': all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == h for p, h in hashes.items())}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--work', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    result = evaluate(args.work)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
    print(json.dumps({k: result[k] for k in ['valid_answers', 'preferences', 'candidate_alert_count', 'answers_unchanged']}))


if __name__ == '__main__':
    main()
