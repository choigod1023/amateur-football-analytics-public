"""Isolate rule defects with exact synthetic inputs; audit real evidence separately."""
import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.live_feedback import LiveAnalyzer
from app.position_quality import calibration_diagnostics


def synthetic(mode, direction=1):
    analyzer = LiveAnalyzer(direction, fps=5)
    alerts = []
    for frame in range(16):
        if mode == 'missing_sample' and frame == 4:
            continue
        if mode == 'timestamp_gap' and frame < 10 and frame not in (0, 5):
            continue
        inside = mode != 'brief_spikes' or frame % 5 == 0
        team = [(i, direction * (35 if inside else 10), (i-1)*5) for i in range(3)]
        alerts.extend(analyzer.update(frame/5, team, []))
    return [{'kind': a['kind'], 'time': a['time']} for a in alerts]


def replay(rows):
    analyzer = LiveAnalyzer(1, pitch_width=60, fps=5)
    alerts = []
    for row in rows:
        # Frozen model positions isolate rule changes, not end-to-end deployment.
        p = row['raw_positions']
        if not row.get('camera_ready') or max(len(p['home']), len(p['away'])) > 11:
            analyzer.interrupt_observations(row['time'])
            continue
        alerts.extend(analyzer.update(row['time'], p['home'], p['away']))
    return [{'kind': a['kind'], 'time': a['time']} for a in alerts]


def run(root):
    labels = root/'work/human-labels/public-own-match-review-20261111'
    observation = root/'work/reviewed-reconnect-live-20261113/run-73-observations.jsonl'
    paths = sorted(labels.rglob('*.json'))
    hashes = {str(p.relative_to(labels)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    rows = [json.loads(line) for line in observation.read_text(encoding='utf-8').splitlines()]
    calibrations = json.loads((labels/'calibration/calibrations.json').read_text(encoding='utf-8'))
    tokens = {'1da78e7532195a1410c61e3b1cd20a80.jpg', '426e7046c075a96dc56a46690aae291b.jpg',
              '63ed34ffc224e22c5cf4839ab2521bd6.jpg', '29402e4af63885b062ea6ab06b6a315a.jpg'}
    reviewed = []
    for p in labels.glob('*.json'):
        d = json.loads(p.read_text(encoding='utf-8'))
        if isinstance(d, dict) and d.get('image') in tokens:
            reviewed.append({k: d.get(k) for k in ('image', 'track_id', 'role', 'team_group', 'source_provenance')})
    corrected = copy.deepcopy(rows)
    role_changes = []
    for label in reviewed:
        provenance = label['source_provenance']
        if provenance.get('source_sha256') != '7e61e4610472d49172984cbd8ba971c72efc294ee30eb15dc6f551a8788acf59':
            continue
        row = next((r for r in corrected if abs(r['time'] - provenance['source_time_sec']) < .00001), None)
        tid = int(label['track_id'])
        if row is None or not any(int(b[-1]) == tid for b in row['source_tracks']):
            continue
        positions = row['raw_positions']
        found = [(side, p) for side in ('home', 'away') for p in positions[side] if int(p[0]) == tid]
        if len(found) != 1:
            role_changes.append({'time': row['time'], 'id': tid, 'status': 'no_unique_existing_position'})
            continue
        before, point = found[0]
        after = None if label['role'] == 'spectator' else {'team_a': 'away', 'team_b': 'home'}.get(label['team_group'])
        positions[before].remove(point)
        if after:
            positions[after].append(point)
        role_changes.append({'time': row['time'], 'id': tid, 'before': before, 'after': after,
                             'status': 'exact_frame_only_estimated_position_preserved'})
    return {'synthetic_exact_positions': {m: synthetic(m) for m in ('sustained', 'brief_spikes', 'missing_sample', 'timestamp_gap')},
            'real_frozen_position_replay': replay(rows), 'real_frames': len(rows),
            'observation_sha256': hashlib.sha256(observation.read_bytes()).hexdigest(),
            'calibration': calibration_diagnostics(calibrations['cam3']), 'human_role_observations': reviewed,
            'partial_role_oracle_changes': role_changes, 'partial_role_oracle_alerts': replay(corrected),
            'human_answers_unchanged': all(hashlib.sha256((labels/p).read_bytes()).hexdigest() == h for p,h in hashes.items()),
            'limitations': ['Synthetic inputs test rule correctness, not real tactical accuracy.',
              'Real positions remain model estimates; replay bypasses deployment position guard to isolate rules.',
              'Clicked landmarks are not surveyed pitch or player-foot ground truth.',
              'Five role answers do not provide a complete team/foot/identity oracle; no such accuracy is claimed.']}


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    result = run(args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('human_role_observations', 'limitations', 'calibration')}, ensure_ascii=False))
