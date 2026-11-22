"""Conservative, auditable tracking comparison gate; never deploys a model.

Unmatched boxes are a regression proxy, NOT verified false positives. Missing
identity truth cannot be converted into zero errors or a successful comparison.
"""
import math


def role_gate(baseline, candidate, classes):
    """Do not hide spectator-to-player regressions behind overall accuracy."""
    required = {'referee', 'spectator', 'team_a', 'team_b'}
    old, new = baseline.get('confusion'), candidate.get('confusion')
    valid = (len(classes) == 4 and set(classes) == required
             and all(isinstance(matrix, list) and len(matrix) == 4
                     and all(isinstance(row, list) and len(row) == 4 and all(count(x) for x in row) for row in matrix)
                     for matrix in (old, new)))
    if not valid or any(sum(a) != sum(b) for a, b in zip(old, new)):
        return {'status': 'needs_validation', 'production_approved': False,
                'reason': 'Comparable confusion matrices and class definitions required'}
    players = [classes.index(name) for name in ('team_a', 'team_b')]
    regressions = []
    for name in ('referee', 'spectator'):
        i = classes.index(name)
        a, b = sum(old[i][j] for j in players), sum(new[i][j] for j in players)
        if b > a:
            regressions.append({'metric': name + '_as_player', 'before': a, 'after': b})
    a, b = sum(old[i][i] for i in range(4)), sum(new[i][i] for i in range(4))
    if b < a:
        regressions.append({'metric': 'correct', 'before': a, 'after': b})
    return {'status': 'regression' if regressions else 'needs_validation',
            'production_approved': False, 'regressions': regressions,
            'correct_before': a, 'correct_after': b,
            'limits': ['Role classification alone cannot approve tracking, minimap or coaching deployment.']}


def count(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0


def tracking_gate(groups, *, independent=False, own_identity_verified=False):
    regressions, missing, improvements = [], [], []
    evaluated = 0
    for name, group in groups.items():
        if not isinstance(group, dict) or 'baseline' not in group or 'candidate' not in group:
            continue
        evaluated += 1
        baseline, candidate = group['baseline'], group['candidate']
        for field, higher in [('matched', True), ('unmatched_detection', False), ('duplicate_gt_claims', False)]:
            old, new = baseline.get(field), candidate.get(field)
            key = f'{name}.{field}'
            if not count(old) or not count(new):
                missing.append(key)
                continue
            if (new < old) if higher else (new > old):
                regressions.append({'metric': key, 'before': old, 'after': new})
            elif old != new:
                improvements.append({'metric': key, 'before': old, 'after': new})
        paired = group.get('paired_output_changes', {})
        denominator = paired.get('shared_consecutive_comparisons')
        old, new = paired.get('baseline_shared_switches'), paired.get('candidate_shared_switches')
        if not all(count(v) for v in (denominator, old, new)) or denominator == 0 or max(old, new) > denominator:
            missing.append(f'{name}.shared_identity_comparison')
        elif new > old:
            regressions.append({'metric': f'{name}.shared_identity_switches', 'before': old, 'after': new, 'denominator': denominator})
        elif new < old:
            improvements.append({'metric': f'{name}.shared_identity_switches', 'before': old, 'after': new, 'denominator': denominator})
    if not evaluated:
        missing.append('comparison_groups')
    if not independent:
        missing.append('independent_evaluation')
    if not own_identity_verified:
        missing.append('own_video_identity_truth')
    status = 'regression' if regressions else ('needs_validation' if missing or not improvements else 'eligible_for_shadow_test')
    return {'status': status, 'production_approved': False, 'regressions': regressions,
            'missing_evidence': missing, 'improvements': improvements,
            'limits': ['Unmatched output is only a diagnostic proxy, not verified false positives.',
                       'Eligibility for shadow testing is not deployment approval.',
                       'Team, pitch position, coaching and latency require separate evidence.']}
