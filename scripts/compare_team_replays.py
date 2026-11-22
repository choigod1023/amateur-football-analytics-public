"""Compare paired fresh-inference logs; consistency is not ground-truth accuracy."""
import argparse
from collections import Counter
import json
from pathlib import Path
from statistics import median


def summarise(rows):
    previous={};switches=0;ids=set();gaps=0;last_seen={}
    for row in rows:
        now={str(tid):team for team,items in row['raw_positions'].items() for tid,_,_ in items}
        switches+=sum(previous[k]!=v for k,v in now.items() if k in previous)
        for ident in now:
            if ident in last_seen and row['time']-last_seen[ident]>.21:gaps+=1
            last_seen[ident]=row['time']
        ids.update(now);previous=now
    return {'frames':len(rows),'median_positions':median(len(r['players']) for r in rows),
        'eligible_track_ids':len(ids),'same_id_team_changes':switches,'reappearance_gaps':gaps,
        'over_capacity_frames':sum(any(sum(p['team']==team for p in r['players'])>11 for team in ('home','away')) for r in rows),
        'rejected_positions':sum(r['position_rejected'] for r in rows),
        'processing_ms_median':median(r['processing_ms'] for r in rows),
        'alert_counts':dict(Counter(a['kind'] for r in rows for a in r['alerts']))}


def main():
    p=argparse.ArgumentParser();p.add_argument('directory',type=Path);a=p.parse_args()
    logs={name:[json.loads(line) for line in (a.directory/(name+'-observations.jsonl')).read_text(encoding='utf-8').splitlines()] for name in ('old','new')}
    assert len(logs['old'])==len(logs['new'])==300
    assert [r['time'] for r in logs['old']]==[r['time'] for r in logs['new']]
    results={k:summarise(v) for k,v in logs.items()}
    results['same_detection_tracking_counts']=all((x['detected'],x['tracked'])==(y['detected'],y['tracked']) for x,y in zip(logs['old'],logs['new']))
    results['limitations']='Same 60s development replay. No human ID/position/event ground truth; fewer changes need not be more accurate.'
    with (a.directory/'replay-comparison.json').open('x',encoding='utf-8') as f:json.dump(results,f,ensure_ascii=False,indent=2)
    print(json.dumps(results))


if __name__=='__main__':main()
