import json
import numpy as np
import pytest
from scripts.train_team_role import scene_splits, training_mask, validate_image_split
from scripts.evaluate_own_role_split import temporal_partition
from scripts.retrain_reviewed_team import partition, HELD, NEW


def test_only_explicit_consistent_train_metadata_can_train(tmp_path):
    for i,(name,split) in enumerate([('a','train'),('b','eval'),('c','buffer_excluded'),('d',None),('e','train'),('e','eval')]):
        row={'image':name,'bbox_image_norm':[0,0,1,1]}
        if split:row['source_provenance']={'split':split}
        (tmp_path/f'{i}.json').write_text(json.dumps(row))
    assert training_mask(tmp_path,['a','b','c','d','e']).tolist()==[True,False,False,False,False]
    assert scene_splits(tmp_path)['e']=='conflicting'


def test_temporal_buffer_duplicates_and_missing_provenance_excluded():
    metadata={name:{'split':split,'time':t,'clip':'same'} for name,split,t in
              [('eval','eval',100),('near','train',80),('far','train',0),('copy','train',0),('unknown','train',None)]}
    names=list(metadata);hashes={n:n for n in names};hashes['copy']='eval'
    train,held=temporal_partition(names,metadata,hashes)
    assert train.tolist()==[False,False,True,False,False]
    assert held.tolist()==[True,False,False,False,False]


def test_retraining_does_not_consume_nonfixed_eval_images():
    names=['source_eval.jpg','train.jpg',next(iter(NEW)),next(iter(HELD))]
    old,new,test=partition(names,[False,True,True,False])
    assert old.tolist()==[False,True,False,False]
    assert new.tolist()==[False,True,True,False]
    assert not (new&test).any()


def test_renamed_evaluation_image_is_not_allowed_in_training(tmp_path):
    for name in ('a.jpg','b.jpg'):(tmp_path/name).write_bytes(b'same-image')
    with pytest.raises(ValueError,match='Duplicate image'):
        validate_image_split(tmp_path,['a.jpg','b.jpg'],np.array([True,False]),np.array([False,True]))


def test_unknown_evaluation_time_cannot_claim_temporal_separation():
    with pytest.raises(ValueError,match='provenance'):
        temporal_partition(['a'],{'a':{'split':'eval','time':None,'clip':'same'}},{'a':'a'})
