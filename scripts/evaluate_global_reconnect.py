"""Read-only candidate feasibility audit. Training pairs are NOT held-out GT."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
import cv2
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.global_reconnect import Candidate, assign_candidates
from app.learned_reconnect import descriptor
from app.temporal_reconnect import sequence_features, temporal_score


def main():
    p=argparse.ArgumentParser()
    p.add_argument('work',type=Path)
    p.add_argument('output',type=Path)
    a=p.parse_args()
    root=a.work/'temporal-reconnect-20261113'
    manifest=json.loads((root/'train-sequences.json').read_text())
    model=json.loads((root/'model.json').read_text())
    sequences=[]
    for pair in manifest['pairs']:
        answer=Path(pair['answer_path'])
        if hashlib.sha256(answer.read_bytes()).hexdigest()!=pair['answer_sha256']:
            raise ValueError('Human answer changed; regenerate manifest')
        sides=[]
        for side in ('before','after'):
            rows=pair[side][-5:] if side=='before' else pair[side][:3]
            seq=[]
            for row in rows:
                path=Path(row['frame_path'])
                if hashlib.sha256(path.read_bytes()).hexdigest()!=row['frame_sha256']:
                    raise ValueError('Source image changed')
                frame=cv2.imread(str(path))
                if frame is None:
                    raise ValueError('Decode failed')
                seq.append({'time':row['time'],'box':row['box_xyxy'],'descriptor':descriptor(frame,row['box_xyxy'])})
            sides.append(seq)
        sequences.append((pair,*sides))
    outcomes=[]
    started=time.perf_counter()
    for target,_,after in sequences:
        edges=[]
        for source,before,_ in sequences:
            if source['video_group']!=target['video_group']:
                continue
            gap=after[0]['time']-before[-1]['time']
            if not 0<gap<=2.5:
                continue
            x=sequence_features(before,after)
            if x is None or max(x[9],x[10])>model['max_prediction_residual_heights']:
                continue
            edges.append(Candidate(str(source['before'][-1]['track_id']),str(target['after'][0]['track_id']),temporal_score(model,x),before[-1]['time'],after[0]['time'],after[-1]['time']))
        result=assign_candidates(edges,now=after[-1]['time'])
        choices=sorted([e for e in edges if e.source!=e.target], key=lambda e:e.score,reverse=True)
        baseline=bool(choices and choices[0].score>=.9 and (len(choices)==1 or choices[0].score-choices[1].score>=.15))
        outcomes.append({'target':target['id'],'human_pair_label':target['label'],
                         'known_source':str(target['before'][-1]['track_id']),
                         'known_target':str(target['after'][0]['track_id']),
                         'baseline_local_accepted':baseline,
                         'already_same_raw_id':str(target['before'][-1]['track_id'])==str(target['after'][0]['track_id']),
                         'candidates':[e.__dict__ for e in edges],**result})
    heldout=[]
    for folder in sorted(root.glob('eval-*')):
        events=json.loads((folder/'events.json').read_text())
        temporal=[r for r in events if r['mode']=='temporal']
        heldout.append({'clip':folder.name,'recorded_temporal_joins':len(temporal),
                        'classification_counts':{c:sum(r['classification']==c for r in temporal)
                         for c in ('correct_joins','wrong_joins','unresolved_joins')},
                        'replay_possible':False,'reason':'Logs contain accepted joins only, not competing candidates or observed endpoint timestamps. No invented edges.'})
    report={'operationally_approved':False,'evaluation_scope':'training-pair feasibility only; no heldout improvement claim',
            'accepted_known_positive':sum(e['source']==r['known_source'] and e['target']==r['known_target'] and r['human_pair_label']==1 for r in outcomes for e in r['accepted']),
            'accepted_known_negative':sum(e['source']==r['known_source'] and e['target']==r['known_target'] and r['human_pair_label']==0 for r in outcomes for e in r['accepted']),
            'accepted_unknown_pair':sum((e['source'],e['target'])!=(r['known_source'],r['known_target']) for r in outcomes for e in r['accepted']),
            'baseline_local_accepted':sum(r['baseline_local_accepted'] for r in outcomes),
            'pair_count':len(sequences),'feature_and_assignment_ms':(time.perf_counter()-started)*1000,
            'outcomes':outcomes,'heldout_log_audit':heldout,
            'policy':{'threshold':.9,'unmatched_score':.5,'global_margin':.15,'max_lag_s':.6,'max_gap_s':2.5}}
    a.output.mkdir(parents=True,exist_ok=True)
    (a.output/'comparison.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report))


if __name__=='__main__':
    main()
