import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from build_auto_dataset import split_boxes, tile_rows  # noqa: E402


def det(x, y, w=20, h=50, score=0.9):
    return [x, y, x + w, y + h, score]


def test_two_detectors_agreeing_is_a_person_and_a_weak_single_one_is_unclear():
    a = [det(100, 100, score=0.4), det(300, 100, score=0.3)]
    b = [det(102, 101, score=0.5)]
    people, unclear = split_boxes(a, b, [])
    assert len(people) == 1 and people[0][0] == 100
    assert len(unclear) == 1 and unclear[0][0] == 300


def test_accepted_box_is_a_person_and_not_unclear():
    b = [det(300, 100, score=0.4)]
    people, unclear = split_boxes([], b, [[300.0, 100.0, 320.0, 150.0]])
    assert len(people) == 1 and unclear == []


def test_a_sure_single_detection_counts():
    people, unclear = split_boxes([det(50, 50, score=0.7)], [], [])
    assert len(people) == 1 and unclear == []


def test_tile_with_an_unclear_box_is_dropped_and_other_tile_keeps_its_rows():
    people = [[10.0, 10.0, 30.0, 60.0]]
    unclear = [[500.0, 10.0, 520.0, 60.0]]
    assert tile_rows(people, unclear, 0, 0) == tile_rows(people, [], 0, 0)
    assert len(tile_rows(people, unclear, 0, 0)) == 1
    assert tile_rows(people, unclear, 400, 0) is None


def test_box_mostly_outside_the_tile_is_not_a_row():
    assert tile_rows([[380.0, 10.0, 420.0, 60.0]], [], 0, 0) == []
