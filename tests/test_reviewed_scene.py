import json,hashlib
from pathlib import Path
import pytest
from app.reviewed_scene import postprocess,reviewed_scene
from app.track_stitch import drop_duplicates


def test_explicit_distinct_pair_survives_identical_geometry():
    rows={k:[{'frame':0,'team':None,'box':[0,0,10,40]}] for k in ['29','31']}
    assert drop_duplicates(rows)[1]==1
    result=postprocess(rows,[['29','31']])
    assert result['dropped']==0 and set(result['tracks'])=={'29','31'}


def test_source_fingerprint_and_interval_are_enforced(tmp_path):
    video=tmp_path/'v.mp4';video.write_bytes(b'test')
    trace=tmp_path/'t.jsonl';trace.write_text('\n'.join(json.dumps({'time':t,'source_tracks':[[0,0,10,40,29],[0,0,10,40,31]]}) for t in (0,1,2)))
    answer={'verdict':'different_people','pair':['29','31'],'scope':{'start_s':1,'end_s':1,'trace_sha256':hashlib.sha256(trace.read_bytes()).hexdigest(),'video_sha256':hashlib.sha256(video.read_bytes()).hexdigest()}}
    result=reviewed_scene(trace,video,answer)
    assert result['before']['dropped']==1 and result['after']['dropped']==0
    assert all(r['time']==1 for rows in result['after']['tracks'].values() for r in rows)
    video.write_bytes(b'other')
    with pytest.raises(ValueError,match='fingerprint'):reviewed_scene(trace,video,answer)


def test_negative_survives_other_safe_component_join():
    def row(f,x,team):return {'frame':f,'team':team,'box':[x,0,x+10,40]}
    tracks={'1':[row(0,0,'A'),row(1,1,'A')],'29':[row(3,3,'A'),row(4,4,'A')],'31':[row(3,3,'B'),row(4,4,'B')]}
    result=postprocess(tracks,[['29','31']])
    assert result['membership']['29']=='1'
    assert set(result['tracks'])=={'1','31'} and result['dropped']==0
