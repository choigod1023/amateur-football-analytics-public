"""Bounded causal image-space foot filtering for distant observed people.

This is a measurement filter, not a position detector or identity resolver. It
never emits a missing person, extrapolates, or asserts metre accuracy. Callers
must keep raw feet for diagnostics and mark filtered coordinates as estimates.
When overlap/identity evidence is ambiguous, pass ambiguous=True to bypass and
clear history rather than blend positions of potentially different people.
"""
import math


class FootStabilizer:
    def __init__(self, tau=.18, max_gap=.6, distant_height=80., max_shift=3.):
        if tau <= 0 or max_gap <= 0 or distant_height <= 0 or max_shift < 0:
            raise ValueError('Positive time/height limits and nonnegative shift required')
        self.tau = tau
        self.max_gap = max_gap
        self.distant_height = distant_height
        self.max_shift = max_shift
        self.previous = {}

    def reset(self, tid=None):
        if tid is None:
            self.previous.clear()
        else:
            self.previous.pop(str(tid), None)

    def update(self, t, tid, box, *, ambiguous=False):
        """Return one current observed box with its bottom centre stabilized.

        Width and height are preserved. ``pixel_shift`` bounds the difference
        from the CURRENT measured foot, not its previous position. Every reset
        returns the original box, so a large displacement is never hidden by
        this filter. A changed track/segment ID automatically gets fresh state.
        """
        tid = str(tid)
        values = [float(v) for v in box]
        if len(values) != 4 or not all(math.isfinite(v) for v in [t, *values]):
            self.reset(tid)
            raise ValueError('Finite timestamp and four box coordinates required')
        x1, y1, x2, y2 = values
        width, height = x2-x1, y2-y1
        if width <= 0 or height <= 0:
            self.reset(tid)
            raise ValueError('Box must have positive width and height')
        raw = ((x1+x2)/2, y2)
        prior = self.previous.get(tid)
        # Bound memory during long streams with increasing temporary IDs.
        self.previous = {k: v for k, v in self.previous.items() if 0 <= t-v['time'] <= self.max_gap}
        reason, foot = 'new_observation', raw
        if ambiguous:
            reason = 'ambiguous_identity_or_overlap'
        elif height > self.distant_height:
            reason = 'near_person_unfiltered'
        elif prior is not None:
            dt = t-prior['time']
            size_ratio = max(height/prior['height'], prior['height']/height,
                             width/prior['width'], prior['width']/width)
            jump = math.hypot(raw[0]-prior['raw'][0], raw[1]-prior['raw'][1])
            if not 0 < dt <= self.max_gap:
                reason = 'time_gap_or_rewind'
            elif size_ratio > 1.35:
                reason = 'box_shape_changed'
            elif jump > max(6., .35*min(height, prior['height'])):
                reason = 'large_observed_displacement'
            else:
                alpha = -math.expm1(-dt/self.tau)
                proposed = tuple(prior['foot'][i]+alpha*(raw[i]-prior['foot'][i]) for i in (0,1))
                dx, dy = proposed[0]-raw[0], proposed[1]-raw[1]
                shift = math.hypot(dx,dy)
                cap = min(self.max_shift, .15*height)
                scale = min(1., cap/shift) if shift else 1.
                foot = (raw[0]+dx*scale, raw[1]+dy*scale)
                reason = 'bounded_causal_filter'
        if ambiguous or height > self.distant_height:
            self.reset(tid)
        else:
            self.previous[tid] = {'time':t,'raw':raw,'foot':foot,'height':height,'width':width}
        dx, dy = foot[0]-raw[0], foot[1]-raw[1]
        shift = math.hypot(dx,dy)
        return {'box':[x1+dx,y1+dy,x2+dx,y2+dy], 'raw_foot':list(raw),
                'foot':list(foot), 'pixel_shift':shift,
                'kind':'smoothed_observation' if shift > 1e-9 else 'observed',
                'reason':reason, 'extrapolated':False}
