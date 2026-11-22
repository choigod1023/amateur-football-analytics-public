"""Opt-in, bounded assignment of observed tracklets; never invents positions.

Edges must use canonical source identities scoped to one video/window. Scores
are ranking utilities, not calibrated probabilities. No public IDs are revised.
"""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class Candidate:
    source: str
    target: str
    score: float
    source_end: float
    target_start: float
    available_at: float  # timestamp of last frame used by the scorer


def _assignment(cost):
    """Rectangular Hungarian algorithm, rows <= columns; no new dependency."""
    n, m = len(cost), len(cost[0])
    u, v, p, way = [0.] * (n + 1), [0.] * (m + 1), [0] * (m + 1), [0] * (m + 1)
    for i in range(1, n + 1):
        p[0], j0 = i, 0
        minimum, used = [float('inf')] * (m + 1), [False] * (m + 1)
        while True:
            used[j0] = True
            i0, delta, j1 = p[j0], float('inf'), 0
            for j in range(1, m + 1):
                if not used[j]:
                    cur = cost[i0 - 1][j - 1] - u[i0] - v[j]
                    if cur < minimum[j]:
                        minimum[j], way[j] = cur, j0
                    if minimum[j] < delta:
                        delta, j1 = minimum[j], j
            for j in range(m + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minimum[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while True:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
            if j0 == 0:
                break
    return [(p[j] - 1, j - 1) for j in range(1, m + 1) if p[j]]


def assign_candidates(candidates, *, now, threshold=.9, unmatched_score=.5,
                      ambiguity_margin=.15, max_gap=2.5, max_lag=.6,
                      max_nodes=64, max_edges=512):
    """Maximize additive utility; reject edges lacking global exclusion margin.

    Removing each selected edge and solving again measures how much the whole
    assignment depends on it. Ambiguous edges remain unmatched; no second pass
    silently forces their competitors. Caller must provide all competing edges.
    available_at <= now prevents future leakage; max_lag bounds delayed births.
    """
    if not all(math.isfinite(x) for x in (now, threshold, unmatched_score, ambiguity_margin, max_gap, max_lag)):
        raise ValueError('Non-finite configuration')
    if not 0 <= unmatched_score < threshold <= 1 or ambiguity_margin < 0 or max_gap <= 0 or max_lag < 0:
        raise ValueError('Invalid assignment policy')
    candidates = list(candidates)
    if len(candidates) > max_edges:
        raise ValueError('Candidate bound exceeded; split independent windows')
    all_targets = sorted({edge.target for edge in candidates})
    edges, rejected = {}, []
    for edge in candidates:
        key = (edge.source, edge.target)
        if key in edges:
            raise ValueError('Duplicate source-target edge')
        if not all(math.isfinite(x) for x in (edge.score, edge.source_end, edge.target_start, edge.available_at)):
            raise ValueError('Non-finite candidate')
        reason = None
        if not 0 <= edge.score <= 1:
            raise ValueError('Score outside ranking range')
        if edge.source == edge.target or not 0 < edge.target_start - edge.source_end <= max_gap:
            reason = 'invalid_gap'
        elif not edge.target_start <= edge.available_at <= now:
            reason = 'unavailable_evidence'
        elif now - edge.target_start > max_lag + 1e-9:
            reason = 'confirmation_deadline'
        if reason:
            rejected.append({'source': edge.source, 'target': edge.target, 'reason': reason})
        else:
            edges[key] = edge
    sources = sorted({k[0] for k in edges})
    targets = sorted({k[1] for k in edges})
    if max(len(sources), len(targets)) > max_nodes:
        raise ValueError('Node bound exceeded')
    if not edges:
        return {'accepted': [], 'rejected': rejected, 'objective': 0., 'unmatched_targets': all_targets}
    cost = [[-(edges[(s,t)].score - unmatched_score) if (s,t) in edges else 1e6
             for s in sources] + [0.] * len(targets) for t in targets]
    def solve(block=None):
        matrix = [row[:] for row in cost]
        if block is not None:
            matrix[block[0]][block[1]] = 1e6
        pairs = _assignment(matrix)
        return pairs, -sum(matrix[i][j] for i,j in pairs)
    selected, objective = solve()
    accepted = []
    for i,j in selected:
        if j >= len(sources) or cost[i][j] >= 0:
            continue
        edge = edges[(sources[j], targets[i])]
        _, alternative = solve((i,j))
        margin = max(0., objective - alternative)
        row = {'source': edge.source, 'target': edge.target, 'score': edge.score, 'global_margin': margin}
        if edge.score >= threshold and margin + 1e-12 >= ambiguity_margin:
            accepted.append(row)
        else:
            rejected.append(dict(row, reason='low_score' if edge.score < threshold else 'ambiguous_assignment'))
    return {'accepted': accepted, 'rejected': rejected, 'objective': objective,
            'unmatched_targets': [t for t in all_targets if t not in {e['target'] for e in accepted}]}
