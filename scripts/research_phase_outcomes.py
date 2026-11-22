"""Which way of attacking led to a shot against which defensive block? (research, read only, SkillCorner open data)

python scripts/research_phase_outcomes.py <skillcorner data folder> [--out result.json]

Every row of <match>_phases_of_play.csv is one possession phase with the type of the attacking phase (build_up, create, finish, direct, quick_break, transition, ...),
the block the other team defended in (low_block, medium_block, high_block, ...), and whether the phase led to a shot or a goal.
Tables: shot rate per attacking type, per defensive block, and per type x block, each with a 95 % Wilson interval and the number of matches in which the type beat the overall rate.
Reading: this describes what happened in 10 professional matches; it is not a causal claim (a quick break is also a better chance to begin with). Cells with fewer than 30 phases are marked.
"""
import argparse
import collections
import csv
import json
from math import sqrt
from pathlib import Path


def wilson(k, n, z=1.96):
    if n == 0:
        return 0.0, 0.0
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    a = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (c - a) / d, (c + a) / d


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('folder')
    parser.add_argument('--out')
    args = parser.parse_args()
    rows = []
    for path in sorted((Path(args.folder) / 'data' / 'matches').glob('*/*_phases_of_play.csv')):
        with open(path, encoding='utf-8') as f:
            for r in csv.DictReader(f):
                r['match'] = path.parent.name
                rows.append(r)
    shot = lambda r: r['team_possession_lead_to_shot'] == 'True'
    goal = lambda r: r['team_possession_lead_to_goal'] == 'True'
    total = len(rows)
    base = sum(shot(r) for r in rows) / total
    print(f'{total} phases, {len(set(r["match"] for r in rows))} matches, shot rate {base:.1%}, goals {sum(goal(r) for r in rows)}')
    result = {}
    for title, key in (('attacking type', lambda r: r['team_in_possession_phase_type']), ('defensive block', lambda r: r['team_out_of_possession_phase_type']),
                       ('type x block', lambda r: r['team_in_possession_phase_type'] + ' vs ' + r['team_out_of_possession_phase_type'])):
        groups = collections.defaultdict(list)
        for r in rows:
            groups[key(r)].append(r)
        print(f'\n{title}:')
        table = []
        for name, g in sorted(groups.items(), key=lambda kv: -len(kv[1])):
            n, k = len(g), sum(shot(r) for r in g)
            lo, hi = wilson(k, n)
            per = collections.defaultdict(lambda: [0, 0])
            for r in g:
                per[r['match']][0] += 1
                per[r['match']][1] += shot(r)
            above = sum(1 for a, b in per.values() if b / a > base)
            table.append({'name': name, 'phases': n, 'shots': k, 'rate': k / n, 'lo': lo, 'hi': hi, 'goals': sum(goal(r) for r in g), 'matches_above': above, 'matches': len(per)})
            print(f'  {name:42s} phases {n:5d}  shot {k:4d} ({k / n:5.1%}, 95% {lo:.1%}-{hi:.1%})  goals {sum(goal(r) for r in g):3d}  matches above overall {above}/{len(per)}{"  <30 phases" if n < 30 else ""}')
        result[title] = table
    if args.out:
        Path(args.out).write_text(json.dumps({'overall_rate': base, 'phases': total, 'tables': result}, indent=1), encoding='utf-8')


if __name__ == '__main__':
    main()
