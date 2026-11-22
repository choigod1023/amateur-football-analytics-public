"""Ground-truth audit used only after inference; never used for association."""


def audit_join_boundaries(events, traces, windows):
    results = []
    for event in events:
        birth = event.get('birth_time', event['time'])
        start = next(a for a, b in windows if a <= event['time'] < b)
        old_frames = [r for r in traces if start <= r['time'] < birth
                      and event['previous_raw'] in r['aliases']['raw']]
        old_gt = None
        if old_frames:
            old_gt = next((gt for gt, raw in old_frames[-1]['matches']
                           if raw == event['previous_raw']), None)
        new_frames = [r for r in traces if birth - 1e-6 <= r['time'] <= event['time'] + 1e-6
                      and event['raw'] in r['aliases']['raw']]
        new_gts = [next((gt for gt, raw in r['matches'] if raw == event['raw']), None)
                   for r in new_frames]
        known = {gt for gt in new_gts if gt is not None}
        if len(known) > 1 or (old_gt is not None and any(gt != old_gt for gt in known)):
            verdict = 'wrong'
        elif old_gt is None or not new_gts or any(gt is None for gt in new_gts):
            verdict = 'unresolved'
        else:
            verdict = 'correct'
        results.append({**event, 'boundary_verdict': verdict, 'endpoint_old_gt': old_gt,
                        'confirmation_gts': new_gts})
    return results
