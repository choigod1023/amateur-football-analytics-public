"""Read-only sensitivity audit of recorded boxes; no accuracy claims without ground truth."""
import argparse
import json
from collections import Counter
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.pitch_map import fit
from app.position_quality import calibration_diagnostics, position_quality


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--project-root', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    work = args.project_root / 'work'
    read = lambda p: json.loads(p.read_text(encoding='utf-8'))
    record = read(work/'human-labels/public-own-match-review-20261111/calibration/calibrations.json')['cam3']
    fitted = fit(record)
    if 'error' in fitted:
        raise ValueError(fitted['error'])
    projection = dict(width=1920, height=1080, shift=(-1.8, 6.8), bg=(1.003087,-.001614,-7.41,5.61))
    frames = [json.loads(line) for line in (work/'reviewed-reconnect-live-20261113/run-73-observations.jsonl').read_text(encoding='utf-8').splitlines()]
    observations = []
    segments = {}
    eligible_total = 0
    for frame in frames:
        for event in frame.get('identity_events', []):
            if 'new_segment' in event:
                segments[str(int(event['raw_id']))] = str(int(event['new_segment']))
        eligible = {str(int(p[0])) for team in frame.get('raw_positions', {}).values() for p in team}
        eligible_total += len(eligible)
        for track in frame['source_tracks']:
            quality = position_quality(fitted, track[:4], **projection)
            raw_id = str(int(track[4]))
            observations.append({'time': frame['time'], 'raw_id': raw_id,
                                 'eligible_raw_position': segments.get(raw_id, raw_id) in eligible, **quality})
    valid = [r for r in observations if r['valid']]
    radii = [r['foot_envelope_radius_m'] for r in valid]
    eligible_rows = [r for r in observations if r['eligible_raw_position']]
    eligible_valid = [r for r in eligible_rows if r['valid']]
    known = [{'raw_id': c['raw_id'], **position_quality(fitted, c['box'], **projection)}
             for c in read(work/'capacity-audit-20261113/human-review-candidates.json')]
    summary = {'frames': len(frames), 'raw_person_track_observations': len(observations),
               'valid_projection_observations': len(valid),
               'boundary_counts': dict(Counter(r['boundary'] for r in valid)),
               'foot_envelope_radius_m_percentiles': dict(zip(['p50','p90','p95','max'], np.percentile(radii,[50,90,95,100]).tolist())),
               'fails_1m_foot_gate': sum(not r['tactical_foot_gate'] for r in observations),
               'eligible_raw_position_audit': {
                   'logged_team_position_observations': eligible_total,
                   'matched_source_observations': len(eligible_rows),
                   'boundary_counts': dict(Counter(r['boundary'] for r in eligible_valid)),
                   'fails_1m_foot_gate': sum(not r['tactical_foot_gate'] for r in eligible_rows),
                   'foot_envelope_radius_m_percentiles': dict(zip(['p50','p90','p95','max'],np.percentile([r['foot_envelope_radius_m'] for r in eligible_valid],[50,90,95,100]).tolist())) if eligible_valid else {},
                   'scope': 'Recorded raw_positions team eligibility, before position guard/alias/display. Not independently verified player ground truth.'},
               'calibration': calibration_diagnostics(record), 'known_five': known,
               'projection_assumptions': projection,
               'limitations': ['All raw person tracks include spectators, not only eligible players.',
                               'Reuses recorded cam3 transform; camera drift is not independently validated.',
                               'Plus/minus 3 px in each axis is an explicit scenario, not measured uncertainty or 95% confidence.',
                               'Estimated 89x60m dimensions and calibration residuals exclude survey accuracy.',
                               'No position ground truth: no claim of lower true metric error. No production changes.']}
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output/'summary.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding='utf-8')
    (args.output/'observations.jsonl').write_text('\n'.join(json.dumps(row) for row in observations)+'\n', encoding='utf-8')
    print(json.dumps({k:v for k,v in summary.items() if k not in ('known_five','calibration')},indent=2))


if __name__ == '__main__':
    main()
