import pytest
from scripts.retrain_capacity_answers import HELD, partition


def test_whole_image_split_preserves_duplicate_training_images():
    held=next(iter(HELD))
    scenes=[held,'old.jpg','new1.jpg','new2.jpg']
    hashes={held:'held','old.jpg':'old','new1.jpg':'same','new2.jpg':'same'}
    base,candidate,test,new=partition(scenes,{'new1.jpg','new2.jpg'},hashes)
    assert base.tolist()==[False,True,False,False]
    assert candidate.tolist()==[False,True,True,True]
    assert test.tolist()==[True,False,False,False]
    assert new.tolist()==[False,False,True,True]


def test_duplicate_holdout_image_is_rejected_even_under_another_name():
    held=next(iter(HELD))
    with pytest.raises(ValueError,match='Duplicate image'):
        partition([held,'new.jpg'],{'new.jpg'},{held:'same','new.jpg':'same'})


def test_cannot_treat_a_heldout_image_as_a_new_training_answer():
    held=next(iter(HELD))
    with pytest.raises(ValueError,match='overlap'):
        partition([held,'old.jpg'],{held},{held:'a','old.jpg':'b'})
