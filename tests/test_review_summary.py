import json
from app.difference_review import DifferenceReview, fingerprint


def test_preferences_are_not_accuracy_and_stale_answers_are_excluded(tmp_path):
    root = tmp_path / 'differences'
    (root / 'answers').mkdir(parents=True)
    rows = [{'id': f'd{i:04d}', 'kind': 'coaching', 'before': 'old', 'after': 'new'} for i in range(1, 7)]
    (root / 'queue.json').write_text(json.dumps({'items': rows}))
    review = DifferenceReview(tmp_path)
    for row, verdict in zip(rows, ['after', 'unclear', 'after', 'before', 'after', 'before']):
        review.answer(row['id'], verdict)
    summary = review.listing()['review_summary']
    assert summary['judged'] == 5 and summary['after_preference_rate'] == .6
    assert summary['is_accuracy'] is False
    rows[0]['after'] = 'changed'
    (root / 'queue.json').write_text(json.dumps({'items': rows}))
    result = review.listing()
    assert result['completed'] == 5 and result['review_summary']['invalid_or_stale'] == 1
    assert result['review_summary']['after_preference_rate'] == .5
