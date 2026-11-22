from scripts.compare_capacity_coaching import evaluate


def test_unlocated_candidates_still_block_team_capacity():
    people=[{'id':str(i),'team':'home','x':None,'y':None} for i in range(12)]
    report=evaluate([{'time':0,'people':people}], 'people')
    assert report['capacity_blocked_frames']==1
    assert report['alerts']==[]


def test_empty_input_never_fabricates_feedback():
    report=evaluate([{'time':i/5,'people':[]} for i in range(100)],'people')
    assert report['visible_alert_frames']==0
    assert report['alerts']==[]
