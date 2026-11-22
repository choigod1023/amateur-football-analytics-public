"""Optional short candidate continuity; this is not confirmed team identity."""
import time


class CandidateContinuity:
    def __init__(self, min_votes=3, max_unknown=2):
        self.min_votes = min_votes
        self.max_unknown = max_unknown
        self.state = {}

    def reset(self):
        self.state.clear()

    def update(self, candidates, timestamp=None, holdable=None):
        # Inputs must correspond to IDs actually detected on this frame. An ID
        # missing even once is cleared: ByteTrack IDs are not physical identity.
        now = time.monotonic() if timestamp is None else timestamp
        self.state = {key: value for key, value in self.state.items() if key in candidates and 0 < now-value['last'] <= 1.0}
        result = {}
        for tid, candidate in candidates.items():
            if candidate is not None and (type(candidate) is not int or candidate not in (0, 1)):
                self.state.pop(tid, None); result[tid] = None; continue
            state = self.state.setdefault(tid, {'group': None, 'votes': 0, 'unknown': 0, 'last':now})
            state['last'] = now
            if candidate is None:
                state['unknown'] += 1
                allowed = holdable is None or tid in holdable
                result[tid] = state['group'] if allowed and state['votes'] >= self.min_votes and state['unknown'] <= self.max_unknown else None
            else:
                state['unknown'] = 0
                if candidate == state['group']:
                    state['votes'] += 1
                    result[tid] = candidate
                elif state['group'] is None or state['votes'] < self.min_votes:
                    state.update(group=candidate, votes=1)
                    result[tid] = candidate
                else:
                    # Conflicting evidence invalidates rather than silently
                    # preserving a possibly switched player's team.
                    state.update(group=None, votes=0)
                    result[tid] = None
        return result
