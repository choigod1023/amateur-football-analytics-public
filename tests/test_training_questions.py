import json
import cv2
import numpy as np
import pytest
from scripts import run_training_questions as q
from app.training_labels import TrainingLabels


def test_train_only_provenance_and_crop_answer(tmp_path, monkeypatch):
    image_dir=tmp_path/'images'/'train'; label_dir=tmp_path/'labels'/'train'
    image_dir.mkdir(parents=True);label_dir.mkdir(parents=True)
    monkeypatch.setattr(q,'IMAGE_DIR',image_dir);monkeypatch.setattr(q,'LABEL_DIR',label_dir)
    image=image_dir/'game1_0.jpg';label=label_dir/'game1_0.txt'
    assert cv2.imwrite(str(image),np.zeros((50,100,3),np.uint8))
    label.write_text('0 0.5 0.5 0.4 0.4\n')
    frame, boxes, provenance=q.load_sample(image,label)
    assert provenance['split']=='train' and provenance['game_id']=='1' and len(provenance['image_sha256'])==64
    assert boxes[0][0]==pytest.approx([30,15,70,35])
    store=TrainingLabels(tmp_path/'out');store.publish(frame,boxes,'now','aihub_train',provenance=provenance)
    snap=store.freeze();ident=store.save(snap['token'],'1','unknown','unknown','unknown')
    saved=json.loads((tmp_path/'out'/f'{ident}.json').read_text(encoding='utf-8'))
    assert saved['source_provenance']==provenance and saved['team']=='unknown'
    with pytest.raises(ValueError):q.load_sample(image,tmp_path/'other.txt')
    bad=image_dir/'game318_0.jpg';bad.write_bytes(image.read_bytes())
    bad_label=label_dir/'game318_0.txt';bad_label.write_text(label.read_text())
    with pytest.raises(ValueError):q.load_sample(bad,bad_label)
