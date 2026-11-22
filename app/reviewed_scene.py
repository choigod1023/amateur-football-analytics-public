"""Exact-source, bounded-scene postprocessing of a human different-person answer."""
import hashlib
import json
from pathlib import Path
from .track_stitch import stitch_tracks, drop_duplicates


def postprocess(tracks, different_pairs=()):
    membership={}
    joined,joins=stitch_tracks(tracks,different_pairs=different_pairs,
                              require_mutual=True,endpoint_evidence=True,membership=membership)
    # Preserve negatives after safe joins change a component's representative ID.
    mapped=[(membership[a],membership[b]) for a,b in different_pairs if a in membership and b in membership]
    kept,dropped=drop_duplicates(joined,different_pairs=mapped)
    return {'tracks':kept,'joins':joins,'dropped':dropped,'membership':membership}


def reviewed_scene(trace,video,answer):
    trace,video=Path(trace),Path(video)
    scope=answer['scope']
    if answer.get('verdict')!='different_people':
        raise ValueError('Only explicit different-person answers supported')
    if hashlib.sha256(trace.read_bytes()).hexdigest()!=scope['trace_sha256'] or hashlib.sha256(video.read_bytes()).hexdigest()!=scope['video_sha256']:
        raise ValueError('Review source fingerprint mismatch')
    start,end=float(scope['start_s']),float(scope['end_s'])
    if not 0<=start<=end:
        raise ValueError('Invalid review interval')
    pair=list(map(str,answer['pair']))
    if len(pair)!=2 or len(set(pair))!=2:raise ValueError('Two distinct IDs required')
    tracks={}
    for frame,row in enumerate(map(json.loads,trace.read_text(encoding='utf-8').splitlines())):
        if start-1e-8<=row['time']<=end+1e-8:
            for box in row['source_tracks']:
                tid=str(int(box[4]));tracks.setdefault(tid,[]).append({'frame':frame,'time':row['time'],'box':box[:4],'team':None})
    if not all(tid in tracks for tid in pair):raise ValueError('Reviewed people missing from scene')
    return {'scope':scope,'different_pairs':[pair],'before':postprocess(tracks),
            'after':postprocess(tracks,[pair]),'identity_after_crossing':None,'training_applied':False}
