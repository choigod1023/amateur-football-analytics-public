"""Apply local human identity boundaries to a copy; never infer team or smooth positions."""
from copy import deepcopy


def split_reviewed_tracks(data, boundaries):
    result = deepcopy(data)
    next_id = max([int(k) for k in data['tracks'] if str(k).isdigit()] + [0]) + 1
    applied = []
    for tid, decisions in boundaries.items():
        if tid not in data['tracks']:
            raise ValueError('Unknown source track')
        cuts = sorted(set(int(d['frame']) for d in decisions if d['verdict'] == 'different'))
        rows = data['tracks'][tid]
        observed = {r['frame'] for r in rows if not any(r.get(k) for k in ('interpolated','predicted','estimated'))}
        if any(c not in observed or c-1 not in observed for c in cuts):
            raise ValueError('Boundary must have adjacent real observations')
        if not cuts:
            continue
        buckets = [[] for _ in range(len(cuts)+1)]
        for row in rows:
            buckets[sum(row['frame'] >= cut for cut in cuts)].append(deepcopy(row))
        result['tracks'][tid] = buckets[0]
        for cut, tail in zip(cuts, buckets[1:]):
            new_id = str(next_id); next_id += 1
            result['tracks'][new_id] = tail
            applied.append({'source_track':tid, 'frame':cut, 'new_track':new_id})
    return result, applied
