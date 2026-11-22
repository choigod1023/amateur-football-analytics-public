"""Measure display jitter and observed coaching separately; no ground truth is invented."""
import argparse
from collections import Counter
import json
import math
from pathlib import Path
import numpy as np


def positions(row, key):
    return {(p['id'],p['team']):np.array([p['x']*89,p['y']*60]) for p in row[key] if p['x'] is not None and p['y'] is not None}


def measure(rows,key):
    prev={};last_velocity={};speed=[];acceleration=[];ids=set();counts=[];gaps=0;last_seen={}
    for row in rows:
        current=positions(row,key);ids.update(current);counts.append(len(current));velocity={}
        for ident,point in current.items():
            if ident in last_seen and row['time']-last_seen[ident]>.21:gaps+=1
            last_seen[ident]=row['time']
            if ident in prev:
                dt=row['time']-prev[ident][0]
                if 0<dt<=.21:
                    v=(point-prev[ident][1])/dt;velocity[ident]=v;speed.append(float(np.linalg.norm(v)))
                    if ident in last_velocity:acceleration.append(float(np.linalg.norm(v-last_velocity[ident])/dt))
        prev={k:(row['time'],v) for k,v in current.items()};last_velocity=velocity
    percentile=lambda values: {str(q):float(np.percentile(values,q)) for q in (50,95,100)} if values else {}
    return {'position_count_median':float(np.median(counts)),'eligible_ids_and_teams':len(ids),'gaps':gaps,
            'speed_mps':percentile(speed),'acceleration_mps2':percentile(acceleration),
            'speed_gt12':sum(s>12 for s in speed),'pairs':len(speed)}


def main():
    p=argparse.ArgumentParser();p.add_argument('directory',type=Path);a=p.parse_args()
    rows={name:[json.loads(x) for x in (a.directory/f'{name}-observations.jsonl').read_text(encoding='utf-8').splitlines()] for name in ('before','after')}
    assert len(rows['before'])==len(rows['after'])==300
    assert [r['time'] for r in rows['before']]==[r['time'] for r in rows['after']]
    report={name:{'raw_guarded':measure(data,'players'),'display':measure(data,'display_players'),
        'alerts':[{'time':v['time'],'kind':v['kind']} for r in data for v in r['alerts']],
        'splits':[v for r in data for v in r['identity_events'] if v.get('action','split')=='split'],
        'review_candidates':[v for r in data for v in r['identity_events'] if v.get('action')=='review'],
        'rejected_positions':sum(r['position_rejected'] for r in data)} for name,data in rows.items()}
    changes=[]
    for r in rows['after']:
        raw=positions(r,'players');display=positions(r,'display_players')
        for ident in raw.keys()&display.keys():changes.append(float(np.linalg.norm(raw[ident]-display[ident])))
    report['display_change_m']={'max':max(changes,default=0),'median':float(np.median(changes)),'adjusted':sum(v>1e-6 for v in changes),'samples':len(changes)}
    report['limitations']='Display smoothing only. Raw guarded coordinates feed coaching. No independent metre or ID ground truth. Acceleration reduction is not location accuracy.'
    with (a.directory/'comparison.json').open('x',encoding='utf-8') as f:json.dump(report,f,ensure_ascii=False,indent=2)
    print(json.dumps(report))


if __name__=='__main__':main()
