from scripts.evaluate_wide_team_detected import iou, match


def test_iou_and_one_to_one_matching_with_missing_annotations():
    assert iou([0, 0, 10, 10], [0, 0, 10, 10]) == 1
    assert iou([0, 0, 1, 1], [5, 5, 6, 6]) == 0
    tracks = [([0, 0, 10, 10], 1), ([0, 0, 10, 10], 2), ([30, 30, 40, 40], 3)]
    truth_boxes = [([0, 0, 10, 10], 'a'), ([20, 20, 25, 25], 'b')]
    assigned, unmatched = match(tracks, truth_boxes, {'a': 0, 'b': 1})
    assert len(assigned) == 1 and list(assigned.values()) == [0]
    assert unmatched == 1
