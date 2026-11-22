import json
import pytest
from app.difference_review import DifferenceReview


def test_superseded_questions_are_not_answers_and_original_rows_survive(tmp_path):
    root=tmp_path/'differences'
    root.mkdir()
    queue=root/'queue.json'
    queue.write_text(json.dumps({'items':[{'id':'d0104','kind':'coaching'}]}))
    original=queue.read_bytes()
    (root/'inactive.json').write_text(json.dumps({'d0104':'Replaced by a corrected algorithm'}))
    review=DifferenceReview(tmp_path)
    result=review.listing()
    assert result['remaining']==0 and result['completed']==0 and result['retired']==1
    assert review.listing(True)['items'][0]['retired_reason']
    with pytest.raises(ValueError):review.answer('d0104','after')
    assert queue.read_bytes()==original
