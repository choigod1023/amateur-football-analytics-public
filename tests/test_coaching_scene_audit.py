from scripts.audit_coaching_scenes import box_members, interval_frames, evidence


def test_box_count_excludes_outside_endline_and_preserves_ids():
    rows=[(1,30,0),(2,45,0),(3,30,22)]
    assert box_members(rows)==['1']
    assert box_members([(1,-30,0)],direction=-1)==['1']


def test_frame_interval_does_not_add_missing_samples():
    frames={0:{},1:{},5:{}}
    assert [t for t,_ in interval_frames(frames,0,1)]==[0,.2]


def test_audit_never_marks_model_positions_as_ground_truth():
    analyzer=type('Analyzer',(),{'frames':{i:{'team':[(1,30,0)],'other':[]} for i in range(10)},'length':89,'direction':1})()
    result=evidence(analyzer,{'kind':'box_attack','time':2},None,None)
    assert result['sample_count']==10
    assert result['minimum_box_count']==1
    assert result['ground_truth_verdict'] is None


def test_gap_audit_records_actual_supported_sample_aggregation():
    analyzer=type('Analyzer',(),{'frames':{},'gap_series':{4:{'support_samples':3,'median_gap_m':35}},
                               'direction':1,'minimum':3})()
    result=evidence(analyzer,{'kind':'gap_wide','time':5},None,None)
    assert result['trigger_aggregation']=='supported_samples_per_second'
    assert result['trigger_seconds']==[{'second':4,'support_samples':3,'median_gap_m':35}]
    assert result['ground_truth_verdict'] is None
