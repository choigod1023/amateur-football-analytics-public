import importlib.util
from pathlib import Path

spec=importlib.util.spec_from_file_location('experiment',Path(__file__).parents[1]/'scripts/retrain_reviewed_team.py')
experiment=importlib.util.module_from_spec(spec);spec.loader.exec_module(experiment)


def test_recent_scene_only_changes_training_not_holdout():
    old,new,held=experiment.partition(['older.jpg',next(iter(experiment.NEW)),next(iter(experiment.HELD))])
    assert old.tolist()==[True,False,False]
    assert new.tolist()==[True,True,False]
    assert held.tolist()==[False,False,True]
    assert not (new&held).any()
