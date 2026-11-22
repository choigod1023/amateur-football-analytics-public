from scripts.evaluate_wide_tracking import MissedReappearanceAudit


def test_gap_return_separates_retained_and_switched_identity():
    audit = MissedReappearanceAudit()
    targets = [('p1', [0, 0, 10, 10]), ('p2', [20, 0, 30, 10])]
    audit.update(targets, [('p1', '100'), ('p2', '200')])
    audit.update(targets, [])
    audit.update(targets, [('p1', '100')])
    audit.update(targets, [('p1', '101'), ('p2', '201')])
    assert audit.summary()['gap_returns'] == 2
    assert audit.summary()['reappeared_same_id'] == 1
    assert audit.summary()['reappeared_changed_id'] == 1
    assert audit.summary()['gap_lengths_scored_observations'] == [1, 2]


def test_absent_annotation_terminates_evaluation_history():
    audit = MissedReappearanceAudit()
    audit.update([('p1', [])], [('p1', '1')])
    audit.update([], [])
    audit.update([('p1', [])], [('p1', '2')])
    assert audit.summary()['gap_returns'] == 0
