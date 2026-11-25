"""--team-vote-switch (TeamVotes.switch_streak): a track number that moved to a player of the other team takes the new letter after N readings in a row."""
import random
import sys
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))


@pytest.fixture()
def votes_class():
    pytest.importorskip('ultralytics')
    from run_live_feedback import TeamVotes

    class Stored(TeamVotes):
        """the 'box' is the reading itself: 'A', 'B' or None (unclear or unread)"""

        def letter_of(self, frame, box):
            return box
    return Stored


def feed(votes, tid, readings):
    labels = []
    for r in readings:
        votes.observe(tid, None, r)
        labels.append(votes.label(tid))
    return labels


def test_default_is_the_cumulative_vote(votes_class):
    votes = votes_class(minimum=2)
    assert votes.switch_streak == 0
    feed(votes, 1, ['B'] * 10 + ['A'] * 8)
    assert votes.votes[1] == Counter({'B': 10, 'A': 8}) and votes.label(1) == 'B' and votes.switches == 0


def test_default_matches_a_plain_counter_on_random_readings(votes_class):
    rng = random.Random(1123)
    votes = votes_class(minimum=2)
    plain = {}
    for _ in range(3000):
        tid, r = rng.randrange(6), rng.choice(['A', 'B', None, None])
        votes.observe(tid, None, r)
        if r:
            plain.setdefault(tid, Counter())[r] += 1
        c = plain.get(tid)
        want = None
        if c:
            letter, n = c.most_common(1)[0]
            want = letter if n >= 2 else None
        assert votes.label(tid) == want
    assert votes.votes == plain and votes.against == {}


def test_switch_after_n_readings_in_a_row(votes_class):
    votes = votes_class(minimum=2, switch_streak=3)
    labels = feed(votes, 7, ['B'] * 20 + ['A', 'A', 'A', 'A'])
    assert labels[19:] == ['B', 'B', 'B', 'A', 'A']
    assert votes.votes[7] == Counter({'A': 4}) and votes.switches == 1


def test_unclear_and_unread_neither_count_nor_break_the_run(votes_class):
    votes = votes_class(minimum=2, switch_streak=3)
    feed(votes, 7, ['B'] * 5)
    assert feed(votes, 7, ['A', None, None, 'A', None, 'A']) == ['B', 'B', 'B', 'B', 'B', 'A']


def test_a_reading_of_the_current_letter_breaks_the_run(votes_class):
    votes = votes_class(minimum=2, switch_streak=3)
    feed(votes, 7, ['B'] * 5)
    assert feed(votes, 7, ['A', 'A', 'B', 'A', 'A']) == ['B'] * 5
    assert votes.switches == 0 and votes.votes[7] == Counter({'B': 6, 'A': 4})


def test_no_switch_rule_before_a_track_has_a_letter_and_tracks_are_separate(votes_class):
    votes = votes_class(minimum=2, switch_streak=3)
    assert feed(votes, 1, ['A', 'B', 'B', 'B', 'B']) == [None, None, 'B', 'B', 'B']
    feed(votes, 2, ['A'] * 4)
    feed(votes, 1, ['A', 'A'])
    assert votes.label(1) == 'B' and votes.label(2) == 'A' and votes.against == {1: 2}
    feed(votes, 1, ['A'])
    assert votes.label(1) == 'A' and votes.label(2) == 'A'


def test_cli_option_is_off_by_default_and_checked():
    src = (ROOT / 'scripts' / 'run_live_feedback.py').read_text(encoding='utf-8')
    assert "'--team-vote-switch', type=int, default=0" in src
    assert 'must be 0 or at least --vote-min' in src
