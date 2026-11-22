import importlib.util
import json
from pathlib import Path

import pytest

spec=importlib.util.spec_from_file_location('dropout_publish',Path(__file__).parents[1]/'scripts/publish_dropout_review.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def fixture(tmp_path):
    store=tmp_path/'store';root=store/'differences';root.mkdir(parents=True)
    old={'items':[{'id':'d0001','kind':'tracking','title':'unchanged'}]}
    (root/'queue.json').write_text(json.dumps(old))
    (store/'human.json').write_text('{"answer":"preserve"}')
    staged=tmp_path/'staged';staged.mkdir()
    (staged/'d0002.mp4').write_bytes(b'fixture-video')
    row={'id':'d0002','kind':'tracking','review_scope':'occlusion-reappearance','video':'d0002.mp4','images':[]}
    manifest={'queue_sha256':module.sha(root/'queue.json'),'items':[row],
        'store_json_sha256':{str(p.resolve()):module.sha(p) for p in store.rglob('*.json')},
        'media_sha256':{'d0002.mp4':module.sha(staged/'d0002.mp4')}}
    (staged/'staged-publication.json').write_text(json.dumps(manifest))
    return store,staged,old


def test_dry_run_does_not_mutate_and_publish_preserves_answers(tmp_path):
    store,staged,old=fixture(tmp_path);root=store/'differences'
    before=(root/'queue.json').read_bytes();answer=(store/'human.json').read_bytes()
    assert module.publish(staged,store)['published']==[]
    assert (root/'queue.json').read_bytes()==before and not (root/'d0002.mp4').exists()
    report=module.publish(staged,store,apply=True)
    assert report['published']==['d0002']
    assert json.loads((root/'queue.json').read_text())['items'][0]==old['items'][0]
    assert Path(report['backup']).read_bytes()==before
    assert (store/'human.json').read_bytes()==answer
    assert not (root/'dropout-publication.lock').exists()
    with pytest.raises(ValueError):module.publish(staged,store,apply=True)


@pytest.mark.parametrize('changed',['queue','answer','media','destination'])
def test_changed_input_or_existing_destination_never_overwritten(tmp_path,changed):
    store,staged,_=fixture(tmp_path);root=store/'differences'
    if changed=='queue':(root/'queue.json').write_text('{"items":[]}')
    elif changed=='answer':(store/'human.json').write_text('new human answer')
    elif changed=='media':(staged/'d0002.mp4').write_bytes(b'changed')
    else:(root/'d0002.mp4').write_bytes(b'old media')
    current=(root/'queue.json').read_bytes()
    with pytest.raises(ValueError):module.publish(staged,store,apply=True)
    assert (root/'queue.json').read_bytes()==current


def test_concurrent_publication_lock_prevents_mutation(tmp_path):
    store,staged,_=fixture(tmp_path);root=store/'differences'
    (root/'dropout-publication.lock').write_text('other publisher')
    with pytest.raises(ValueError):module.publish(staged,store,apply=True)
    assert (root/'dropout-publication.lock').read_text()=='other publisher'
    assert not (root/'d0002.mp4').exists()
