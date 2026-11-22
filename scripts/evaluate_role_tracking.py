"""Compare two role models in the same frozen, actual recorded-video pipeline."""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import subprocess
import time
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.difference_review import fingerprint


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def load_rows(path):
    return [json.loads(line) for line in Path(path).read_text(encoding='utf-8').splitlines()]


def summarize(rows):
    result = Counter()
    previous, display_previous = {}, {}
    last_time = None
    speeds = []
    alerts = []
    for row in rows:
        t = row['time']
        dt = t-last_time if last_time is not None else 0
        current = {str(x['id']): x for x in row['track_outcomes']}
        displayed = {str(x['id']): x for x in row['display_players']}
        result['frames'] += 1
        result['raw_track_observations'] += len(row['source_tracks'])
        result['excluded_role_or_unknown'] += sum(x['team'] is None for x in current.values())
        result['projected_observations'] += sum(x['projection_status'] == 'projected' for x in current.values())
        result['projection_rejected'] += sum(x['projection_status'] == 'projection_rejected' for x in current.values())
        result['position_rejected'] += row['position_rejected']
        result['display_observations'] += len(displayed)
        result['over_capacity_frames'] += any(sum(x['team'] == team for x in row['players']) > 11 for team in ('home', 'away'))
        if 0 < dt <= .25:
            for ident in previous.keys() & current.keys():
                a, b = previous[ident], current[ident]
                result['adjacent_track_comparisons'] += 1
                if a['team'] in ('A', 'B') and b['team'] in ('A', 'B'):
                    result['adjacent_known_team_comparisons'] += 1
                    result['team_flips'] += a['team'] != b['team']
                result['disappeared_from_map_while_still_tracked'] += ident in display_previous and ident not in displayed
                result['appeared_on_map_while_already_tracked'] += ident not in display_previous and ident in displayed
                if (a['position_status'] == b['position_status'] == 'retained'
                        and a['team'] == b['team'] and a['point_m'] and b['point_m']):
                    speeds.append(math.dist(a['point_m'], b['point_m'])/dt)
        alerts.extend({'kind': a['kind'], 'time': a['time']} for a in row['alerts'])
        previous, display_previous, last_time = current, displayed, t
    result = dict(result)
    result['adjacent_retained_speed_over_12mps'] = sum(v > 12+1e-8 for v in speeds)
    result['identity_accuracy'] = result['position_error_m'] = None
    result['alerts'] = alerts
    return result


def iou(a, b):
    area = max(0, min(a[2], b[2])-max(a[0], b[0]))*max(0, min(a[3], b[3])-max(a[1], b[1]))
    union = (a[2]-a[0])*(a[3]-a[1])+(b[2]-b[0])*(b[3]-b[1])-area
    return area/union if union > 0 else 0


def reviewed_pairs(rows, store, video_sha):
    directory = Path(store)/'differences'
    queue = json.loads((directory/'queue.json').read_text(encoding='utf-8'))
    by_time = {round(r['time'], 4): r for r in rows}
    results = []
    for item in queue['items']:
        answer_file = directory/'answers'/f"{item['id']}.json"
        if item.get('kind') != 'tracking' or item.get('source_sha256') != video_sha or not item.get('boundary') or not answer_file.exists():
            continue
        answer = json.loads(answer_file.read_text(encoding='utf-8'))
        if (answer.get('id') != item['id'] or answer.get('source') != 'human' or answer.get('fingerprint') != fingerprint(item)
                or answer.get('verdict') not in ('same', 'different')):
            continue
        ids = []
        for time_key, box_key in (('end', 'before_box'), ('start', 'after_box')):
            frame = by_time.get(round(item['boundary'][time_key], 4), {})
            matches = [(iou(r[:4], item['boundary'][box_key]), str(int(r[4])))
                       for r in frame.get('observed_tracks', [])]
            matches.sort(reverse=True)
            # Unambiguous geometry correspondence; never force the historical ID.
            ids.append(matches[0][1] if matches and matches[0][0] >= .5
                       and (len(matches) == 1 or matches[0][0]-matches[1][0] >= .1) else None)
        predicted = ('same' if ids[0] == ids[1] else 'different') if all(ids) else None
        results.append({'review_id': item['id'], 'human': answer['verdict'], 'endpoint_ids': ids,
                        'prediction': predicted, 'correct': predicted == answer['verdict'] if predicted else None})
    return results


def run(root, output, summarize_only=False):
    root, output = Path(root).resolve(), Path(output).resolve()
    frozen = root/'outputs/football-own-match-benchmark-1115'
    code = [frozen/'scripts/run_live_feedback.py', frozen/'app/position_guard.py',
            frozen/'app/team_vote_policy.py', frozen/'app/identity_guard.py', frozen/'app/foot_stability.py']
    code_sha = {str(p): sha(p) for p in code}
    command = json.loads((root/'work/own-match-benchmark-20261115/shadow-smoke/clean_baseline/command.json').read_text())
    video_sha = sha(command[2])
    output.mkdir(parents=True, exist_ok=True)
    models = root/'work/own-match-benchmark-20261115/role-final'
    if not summarize_only:
        for mode in ('clean_baseline', 'clean_candidate'):
            target = output/mode
            target.mkdir(exist_ok=False)
            cmd = command.copy()
            cmd[cmd.index('--classifier')+1] = str(models/f'{mode}.pt')
            cmd[cmd.index('--seconds')+1] = '60'
            for key, name in (('--alerts', 'alerts.jsonl'), ('--observations', 'observations.jsonl'), ('--publish-dir', 'live')):
                cmd[cmd.index(key)+1] = str(target/name)
            (target/'command.json').write_text(json.dumps(cmd, indent=2), encoding='utf-8')
            started = time.perf_counter()
            with (target/'run.log').open('w', encoding='utf-8') as log:
                result = subprocess.run(cmd, cwd=frozen, stdout=log, stderr=subprocess.STDOUT)
            (target/'execution.json').write_text(json.dumps({'exit_code': result.returncode,
                'wall_s': time.perf_counter()-started, 'model_sha256': sha(models/f'{mode}.pt')}), encoding='utf-8')
            if result.returncode:
                raise RuntimeError(f'{mode} failed; see run.log')
            if any(sha(p) != digest for p, digest in code_sha.items()):
                raise RuntimeError('Frozen runtime code changed during comparison')
            print(mode, 'completed', flush=True)
        (output/'runtime-manifest.json').write_text(json.dumps({'runtime_code': code_sha, 'video_sha256': video_sha}, indent=2), encoding='utf-8')
    old = load_rows(output/'clean_baseline/observations.jsonl')
    new = load_rows(output/'clean_candidate/observations.jsonl')
    if len(old) != len(new) or any(a['time'] != b['time'] for a, b in zip(old, new)):
        raise ValueError('Frame schedules differ')
    result = {'baseline': summarize(old), 'candidate': summarize(new),
              'raw_tracks_identical': all(a['source_tracks'] == b['source_tracks'] for a, b in zip(old, new)),
              'observed_tracks_identical': all(a['observed_tracks'] == b['observed_tracks'] for a, b in zip(old, new)),
              'video_sha256': video_sha,
              'reviewed_baseline': reviewed_pairs(old, root/'work/human-labels/public-own-match-review-20261111', video_sha),
              'reviewed_candidate': reviewed_pairs(new, root/'work/human-labels/public-own-match-review-20261111', video_sha),
              'limits': ['Display continuity and team flips are not identity accuracy.',
                         'No dense identity or real foot-point truth; accuracy/error remain null.',
                         'Historical reviewed pairs were used in prior training; not independent evaluation.',
                         'Role-model comparison uses frozen pre-position-fix code, not a combined treatment.',
                         'No server restart, model replacement or production publication.']}
    (output/'comparison.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: result[k] for k in ('baseline', 'candidate', 'raw_tracks_identical', 'observed_tracks_identical')}, ensure_ascii=False))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('root', type=Path); parser.add_argument('output', type=Path)
    parser.add_argument('--summarize-only', action='store_true')
    args = parser.parse_args()
    run(args.root, args.output, args.summarize_only)
