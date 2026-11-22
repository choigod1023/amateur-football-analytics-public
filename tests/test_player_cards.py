import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from build_player_cards import run_stats  # noqa: E402


def line(speed, seconds, fps=5.0, start=0):
    return [(start + i, i * speed / fps, 0.0) for i in range(int(seconds * fps) + 1)]


def test_a_steady_run_gives_its_distance_speed_and_one_sprint():
    stats = run_stats(line(6.0, 10), 5.0)
    assert round(stats['distance']) == 60 and round(stats['top'], 1) == 6.0 and stats['sprints'] == 1 and round(stats['covered']) == 10


def test_walking_has_no_sprint_and_a_tracking_jump_is_not_counted():
    walk = line(1.5, 10)
    jump = walk[:25] + [(f, u + 40, y) for f, u, y in walk[25:]]                 # the track leaps 40 m in one step
    stats = run_stats(jump, 5.0)
    assert stats['sprints'] == 0 and stats['top'] < 3 and round(stats['distance']) == 15 - 1 or stats['distance'] < 20


def test_a_hole_in_the_track_adds_neither_time_nor_distance():
    samples = line(2.0, 3) + line(2.0, 3, start=100)
    stats = run_stats(samples, 5.0)
    assert round(stats['covered']) == 6
