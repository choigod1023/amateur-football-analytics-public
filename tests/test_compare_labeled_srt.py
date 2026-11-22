import pytest
from scripts.compare_labeled_srt import compare


def row(frame, pairs):
    return {'source_frame':frame,'gt':1,'predicted':len(pairs),'matched':len(pairs),'gt_track_pairs':pairs}


def test_only_common_frames_are_compared_and_gaps_are_counted():
    truth={n:[('p',[])] for n in range(5)}
    first={'frame_results':[row(0,[['p','1']]),row(1,[]),row(2,[['p','2']]),row(4,[['p','3']])]}
    second={'frame_results':[row(0,[['p','4']]),row(1,[]),row(2,[['p','4']]),row(3,[['p','4']])]}
    result=compare(first,second,truth)
    assert result['common_frames']==[0,1,2]
    assert result['models']['first']['gap_reappearance']['reappeared_changed_id']==1
    assert result['models']['second']['gap_reappearance']['reappeared_same_id']==1
    assert result['models']['first']['matched']==2
    assert result['paired_frames']['equal_matches']==3
    assert result['paired_frames']['equal_unmatched_predictions']==3


def test_framewise_tradeoff_counts_matched_and_unmatched_separately():
    truth={1:[('p',[])],2:[('p',[])]}
    first={'frame_results':[row(1,[['p','a']]),row(2,[])]}
    one=row(1,[['p','b']]); one['predicted']=2
    two=row(2,[['p','b']]); two['predicted']=3
    result=compare(first,{'frame_results':[one,two]},truth)['paired_frames']
    assert result['second_more_matches']==1 and result['equal_matches']==1
    assert result['second_more_unmatched_predictions']==2
    assert result['matched_difference']==1 and result['unmatched_prediction_difference']==3


def test_duplicate_source_frame_is_rejected():
    data={'frame_results':[row(1,[]),row(1,[])]}
    with pytest.raises(ValueError): compare(data,{'frame_results':[row(1,[])]},{1:[]})
