"""Discontinuity policy for the fixed four-clip, local research playlist only."""


def reset_required(previous_segment, current_segment):
    """0-30,30-60,60-90 are continuous; 90-120 is missing.

    The final clip is 120-150 seconds and loops back to zero. Segment numbers
    must derive from the same monotonic 25fps output timeline, not wall clock.
    """
    if type(previous_segment) is not int or type(current_segment) is not int:
        raise ValueError('segment indexes must be integers')
    if previous_segment < 0 or current_segment < 0:
        raise ValueError('segment indexes must be nonnegative')
    if current_segment < previous_segment:
        return True  # New timeline or decoder restart.
    if current_segment - previous_segment >= 4:
        return True  # At least one jump or loop was crossed.
    return any(index % 4 in (0, 3) for index in range(previous_segment + 1, current_segment + 1))
