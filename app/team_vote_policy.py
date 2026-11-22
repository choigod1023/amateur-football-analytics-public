"""Experimental causal abstention policy, not validated team identity recovery."""
from collections import Counter, deque
import numpy as np


def confident(prob):
    p=np.sort(np.asarray(prob,dtype=float))
    return bool(len(p)>=2 and np.isfinite(p).all() and p[-1]>=.5 and p[-1]-p[-2]>=.1)


class WindowVote:
    def __init__(self):
        self.rows={}

    def update(self, tid, letter):
        q=self.rows.setdefault(tid,deque(maxlen=15))
        q.append(letter)
        # Never show stale certainty on a currently uncertain/overlapping crop.
        if letter is None:
            return None
        counts=Counter(x for x in q if x is not None)
        ranking=counts.most_common()
        if not ranking:
            return None
        best,n=ranking[0]
        if len(ranking)>1 and ranking[1][1]==n:
            return None
        # Referee/spectator votes remain in the denominator and can win.
        return best if n>=3 and n/len(q)>=2/3 and best in ('A','B') and best==letter else None
