"""Offline paired replay; immutable local snapshot, no model training or production writes.

Alert counts are sensitivity measurements, NOT accuracy without human event labels.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from app.live_feedback import LiveAnalyzer
from app.pitch_map import fit
from build_tactical_report import metre_rows
from build_team_minimap import parse_schedule


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def replay(data, fitted, bg, schedule, direction, estimates):
    evidence = {}
    frames, _ = metre_rows(data['tracks'], fitted, schedule, bg, 0, data['frames'],
                           include_estimates=estimates, evidence=evidence)
    analyzer = LiveAnalyzer(direction, fitted['pitch']['length'], fitted['pitch']['width'], data['fps'])
    alerts = []
    for frame in range(data['frames']):
        teams = frames.get(frame, {})
        alerts.extend(analyzer.update(data['first_second'] + frame / data['fps'], teams.get('B', []), teams.get('A', [])))
    return {'count': len(alerts), 'kinds': dict(Counter(a['kind'] for a in alerts)),
            'events': [{'time': a['time'], 'kind': a['kind']} for a in alerts], 'input_evidence': evidence}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('work', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    # Never overwrite an earlier frozen evaluation.
    args.output.mkdir(parents=True, exist_ok=False)
    store = args.work / 'human-labels/public-own-match-review-20261111'
    sources = sorted(store.rglob('*.json')) + sorted(store.rglob('*.jsonl'))
    manifest = {}
    for p in sources:
        relative = p.relative_to(store)
        target = args.output / 'snapshot' / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        content = p.read_bytes()
        target.write_bytes(content)
        manifest[str(relative)] = hashlib.sha256(content).hexdigest()
    (args.output / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    calibrations = json.loads((args.output / 'snapshot/calibration/calibrations.json').read_text(encoding='utf-8'))
    results = {'interpretation': 'Paired sensitivity audit, not independent accuracy. Direction h1 unconfirmed.', 'halves': {}}
    for half, filename, cam, direction, bg, schedule in [
        ('h1', 'h1_v3.json', 'cam1', -1, (1.000657, .000035, -.67, -.47), '0:0.0,-0.2'),
        ('h2', 'h2_ov3.json', 'cam3', 1, (1.003087, -.001614, -7.41, 5.61), '0:-1.8,6.8;1950:0.3,0.3')]:
        source = args.work / 'tracks-ov3-20261113' / filename
        content = source.read_bytes()
        (args.output / filename).write_bytes(content)
        data = json.loads(content)
        record = calibrations[cam]
        old_fit = fit({**record, 'pitch': {**record['pitch'], 'length': 89, 'width': 62}})
        saved_fit = fit(record)
        sched = parse_schedule(schedule)
        results['halves'][half] = {'track_sha256': hashlib.sha256(content).hexdigest(),
            'legacy': replay(data, old_fit, bg, sched, direction, True),
            'observed_only_same_calibration': replay(data, old_fit, bg, sched, direction, False),
            'observed_only_saved_calibration': replay(data, saved_fit, bg, sched, direction, False)}
    results['source_labels_unchanged'] = all(digest(store / p) == sha for p, sha in manifest.items())
    results['snapshot_files'] = len(manifest)
    (args.output / 'comparison.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'labels_unchanged': results['source_labels_unchanged'], 'snapshot_files': len(manifest),
        'halves': {h: {k: v['count'] for k, v in r.items() if isinstance(v, dict)} for h, r in results['halves'].items()}}))


if __name__ == '__main__':
    main()
