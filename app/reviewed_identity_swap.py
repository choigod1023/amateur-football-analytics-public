"""Retrospective, source-scoped ID correction; preserve every measured box."""
import hashlib,json
from pathlib import Path


def correct_frame(t,tracked,answer):
    result=[list(r) for r in tracked]
    scope=answer['scope']
    if answer.get('verdict')!='identity_swapped':raise ValueError('Explicit swap confirmation required')
    pair=list(map(str,answer['pair']))
    if len(pair)!=2 or len(set(pair))!=2:raise ValueError('Two IDs required')
    if not scope['start_s']-1e-8<=t<=scope['end_s']+1e-8:return result,False
    ids=[str(int(r[4])) for r in result]
    if any(ids.count(k)!=1 for k in pair):return result,False
    mapping={pair[0]:int(pair[1]),pair[1]:int(pair[0])}
    for row in result:row[4]=mapping.get(str(int(row[4])),row[4])
    return result,True


def apply_reviewed_swap(trace,video,answer):
    trace,video=Path(trace),Path(video)
    scope=answer['scope']
    if hashlib.sha256(trace.read_bytes()).hexdigest()!=scope['trace_sha256'] or hashlib.sha256(video.read_bytes()).hexdigest()!=scope['video_sha256']:
        raise ValueError('Review source fingerprint mismatch')
    frames=[];changed=0
    for r in map(json.loads,trace.read_text(encoding='utf-8').splitlines()):
        corrected,applied=correct_frame(r['time'],r['source_tracks'],answer)
        frames.append({'time':r['time'],'source_tracks':corrected,'review_applied':applied})
        changed+=applied
    return {'frames':frames,'changed_frames':changed,'review_scope':scope,'retrospective':True,
            'positions_changed':False,'team_labels_changed':False,'training_applied':False,
            'note':'ID-only offline artifact. Not a complete live analysis snapshot.'}
