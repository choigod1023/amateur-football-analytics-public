"""Verify unchanged tracker/coaching observations plus explicitly added display points."""
import argparse
import json
from pathlib import Path
from compare_motion_replay import measure


def compare(before, after):
    assert len(before)==len(after) and len(before)>0
    assert [r['time'] for r in before]==[r['time'] for r in after]
    invariants={k:all(a[k]==b[k] for a,b in zip(before,after))
                for k in ('source_tracks','players','raw_positions','identity_events','alerts')}
    added=[]; removed=[]; changed=[]
    for a,b in zip(before,after):
        old={p['id']:p for p in a['display_players']}
        new={p['id']:p for p in b['display_players']}
        added.extend({'time':b['time'],**new[k]} for k in new.keys()-old.keys())
        removed.extend({'time':b['time'],**old[k]} for k in old.keys()-new.keys())
        changed.extend({'time':b['time'],'id':k} for k in old.keys()&new.keys() if old[k]!=new[k])
    return {'frames':len(before),'unchanged':invariants,'before':measure(before,'display_players'),
            'after':measure(after,'display_players'),'added':added,'removed':removed,'changed_existing':changed,
            'all_additions_marked':all(p.get('observation_kind')=='low_confidence_recovery' for p in added),
            'limitations':'Exact baseline invariance is not ground-truth accuracy. Added boxes require video review; no independent full-scene ID or position labels.'}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('before',type=Path);p.add_argument('after',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    load=lambda p:[json.loads(s) for s in p.read_text(encoding='utf-8').splitlines()]
    result=compare(load(a.before),load(a.after))
    with a.output.open('x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2)
    print(json.dumps({k:v for k,v in result.items() if k not in ('added','removed','changed_existing')}))
    if not all(result['unchanged'].values()) or result['removed'] or result['changed_existing'] or not result['all_additions_marked']:
        raise SystemExit('Baseline invariance failed; do not promote recovery.')
