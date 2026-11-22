import unittest
import itertools
import random
from app.global_reconnect import Candidate as C, assign_candidates as assign
from app.global_reconnect import _assignment


def edge(s,t,score):
    return C(s,t,score,0.,.2,.6)


class GlobalAssignmentTests(unittest.TestCase):
    def test_solver_matches_exhaustive_small_graphs(self):
        rng=random.Random(42)
        for n in range(1,5):
            for _ in range(20):
                costs=[[rng.uniform(-1,1) for _ in range(n+2)] for _ in range(n)]
                got=sum(costs[i][j] for i,j in _assignment(costs))
                exact=min(sum(costs[i][j] for i,j in enumerate(cols)) for cols in itertools.permutations(range(n+2),n))
                self.assertAlmostEqual(got,exact)

    def test_global_beats_conflicting_greedy(self):
        rows = [edge('a','x',.99), edge('b','x',.91), edge('a','y',.98)]
        result = assign(rows, now=.6, ambiguity_margin=.01)
        self.assertEqual({(r['source'],r['target']) for r in result['accepted']}, {('b','x'),('a','y')})

    def test_ties_abstain(self):
        result = assign([edge(s,t,.99) for s in ('a','b') for t in ('x','y')],now=.6)
        self.assertEqual(result['accepted'], [])

    def test_unmatched_and_causal(self):
        self.assertEqual(assign([edge('a','x',.3)],now=.6)['accepted'], [])
        self.assertEqual(assign([edge('a','x',.99)],now=.5)['accepted'], [])
        self.assertEqual(assign([edge('a','x',.99)],now=1.)['accepted'], [])

    def test_duplicate_rejected(self):
        with self.assertRaises(ValueError):
            assign([edge('a','x',.99)]*2,now=.6)

    def test_crossing_appearance_does_not_force_identity(self):
        # Each person's appearance score nearly ties with the other player.
        result=assign([edge('a','x',.98),edge('b','y',.98),edge('b','x',.97),edge('a','y',.97)],now=.6)
        self.assertEqual(result['accepted'],[])

    def test_one_source_not_two_people(self):
        result=assign([edge('a','x',.99),edge('a','y',.92)],now=.6,ambiguity_margin=.01)
        self.assertEqual(len(result['accepted']),1)

    def test_overlap_and_nan(self):
        self.assertEqual(assign([C('a','x',.99,1.,.2,.6)],now=.6)['accepted'],[])
        with self.assertRaises(ValueError):
            assign([edge('a','x',float('nan'))],now=.6)


if __name__ == '__main__':
    unittest.main()
