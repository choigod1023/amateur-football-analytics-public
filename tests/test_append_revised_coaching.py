import json
import sys
from scripts.append_revised_coaching import main


def test_append_never_changes_original_item_or_answer_and_is_idempotent(tmp_path, monkeypatch):
    root = tmp_path / 'differences'
    (root / 'answers').mkdir(parents=True)
    original = {'id': 'd0001', 'kind': 'coaching', 'title': 'scene', 'time': 10,
                'before': 'old', 'after': 'previous', 'video': 'd0001.mp4'}
    (root / 'queue.json').write_text(json.dumps({'items': [original]}))
    answer = root / 'answers/d0001.json'
    answer.write_text('{"verdict":"after"}')
    before = answer.read_bytes()
    evaluation = tmp_path / 'evaluation.json'
    evaluation.write_text(json.dumps({'scenes': [{'id': 'd0001', 'verdict': 'after',
        'requires_new_text_review': True, 'candidate_events': [{'title': 'observed change', 'text': 'uncertain'}]}]}))
    monkeypatch.setattr(sys, 'argv', ['append', str(tmp_path), str(evaluation)])
    main()
    main()
    rows = json.loads((root / 'queue.json').read_text(encoding='utf-8'))['items']
    assert len(rows) == 2 and rows[0] == original
    assert rows[1]['parent_review'] == 'd0001' and rows[1]['id'] == 'd0101'
    assert answer.read_bytes() == before
