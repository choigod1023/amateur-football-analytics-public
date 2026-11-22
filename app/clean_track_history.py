"""Shared occlusion gate for temporal identity evidence; no ID-specific rules."""
from .identity_guard import _overlap


def crowded_ids(current, threshold=.35):
    items = list(current.items())
    crowded = set()
    for i, (a, box_a) in enumerate(items):
        for b, box_b in items[i + 1:]:
            if _overlap(box_a[:4], box_b[:4]) >= threshold:
                crowded.update((a, b))
    return crowded


def invalidate_crowded_history(state, time):
    # Do not join pre/post-occlusion observations under a possibly swapped raw ID.
    state['history'] = []
    state['last'] = time
    # This birth has already appeared publicly: never relabel it after a late wait.
    state['decided'] = True
