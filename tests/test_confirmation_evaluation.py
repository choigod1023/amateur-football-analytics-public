import sys
from pathlib import Path
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from evaluate_confirmation_fix import duplicate_pairs, replay, paired_output_changes
from app.confirmation_tracker import ConfirmingBYTETracker


def test_duplicate_counts_all_pairs_not_one_per_box():
    assert duplicate_pairs(np.array([[0,0,10,10]]*3)) == 3


def test_window_boundary_resets_identity_history():
    rows=[{'frame':i,'window':i,'shape':[100,100],
           'detections':[[0,0,10,20,.9,0]],'targets':[(str(i),[0,0,10,20])]} for i in range(2)]
    metrics,_=replay(rows,ConfirmingBYTETracker)
    assert metrics['matched']==2
    assert metrics['identity_comparisons']==0
    assert metrics['consecutive_comparisons']==0


def test_gt_identity_never_changes_tracker_output():
    row={'frame':0,'window':0,'shape':[100,100],'detections':[[0,0,10,20,.9,0]]}
    _,a=replay([{**row,'targets':[('first',[0,0,10,20])]}],ConfirmingBYTETracker)
    _,b=replay([{**row,'targets':[('other',[0,0,10,20])]}],ConfirmingBYTETracker)
    assert a[0]['tracks']==b[0]['tracks']


def test_paired_changes_use_detection_indices_not_unstable_track_ids():
    old={'tracks':[[0,0,10,20,1,.9,0,0]],'matches':[('gt','1')]}
    new={'tracks':[[0,0,10,20,9,.9,0,0],[30,0,40,20,10,.9,0,1]],'matches':[('gt','9')]}
    result=paired_output_changes([{'targets':[('gt',[0,0,10,20])]}],[old],[new])
    assert result['added_outputs']==1
    assert result['added_gt_unmatched']==1
    assert result['removed_outputs']==0


def test_shared_identity_changes_require_both_modes_at_both_endpoints():
    rows=[{'targets':[], 'window':0}]*2
    old=[{'tracks':[],'matches':[('a','1'),('b','2')]}, {'tracks':[],'matches':[('a','3'),('b','4')]}]
    new=[{'tracks':[],'matches':[('a','9')]}, {'tracks':[],'matches':[('a','9'),('b','10')]}]
    result=paired_output_changes(rows,old,new)
    assert result['shared_consecutive_comparisons']==1
    assert result['baseline_shared_switches']==1
    assert result['candidate_shared_switches']==0
