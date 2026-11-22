"""Compare actual replays, separating confirmed identity corrections from detection."""
import argparse,hashlib,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.reviewed_reconnect import ReviewedReconnector


def original(players):
    return sorted((p.get('source_id',p['id']),p['team'],p['x'],p['y'],p.get('observation_kind')) for p in players)


def compare(before,after,decisions):
    assert len(before)==len(after)==300
    assert [r['time'] for r in before]==[r['time'] for r in after]
    replay=ReviewedReconnector(decisions)
    assert all(replay.update(r['time'],r['source_tracks'])[0]==r['identity_aliases'] for r in after)
    identical={key:all(a[key]==b[key] for a,b in zip(before,after)) for key in ('source_tracks','raw_positions','identity_events','alerts')}
    identical['display_geometry_and_team']=all(original(a['display_players'])==original(b['display_players']) for a,b in zip(before,after))
    identical['measurement_geometry_and_team']=all(original(a['players'])==original(b['players']) for a,b in zip(before,after))
    changed=[{'time':r['time'],'source_id':p['source_id'],'id':p['id']} for r in after for p in r['display_players'] if 'source_id' in p]
    allowed={tuple(reversed(list(map(str,p['pair'])))) for p in decisions['approved']}
    assert all((p['source_id'],p['id']) in allowed for p in changed)
    assert all(len({p['id'] for p in r['display_players']})==len(r['display_players']) for r in after)
    events=[e for r in after for e in r['reconnect_events']]
    result={'frames':300,'unchanged':identical,'events':events,'changed_display_observations':len(changed),
        'changed_by_pair':{f'{a}->{b}':sum(p['source_id']==a and p['id']==b for p in changed) for a,b in sorted(allowed)},
        'display_ids_before':len({p['id'] for r in before for p in r['display_players']}),
        'display_ids_after':len({p['id'] for r in after for p in r['display_players']}),
        'blocked_pairs':decisions['blocked'],'duplicate_display_ids':0,
        'limits':'Human-answer compliance on the reviewed recording, not an independent identity-accuracy estimate. No missing positions are synthesized.'}
    assert all(identical.values())
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('before',type=Path);p.add_argument('after',type=Path);p.add_argument('decisions',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    load=lambda path:[json.loads(s) for s in path.read_text(encoding='utf-8').splitlines()]
    result=compare(load(a.before),load(a.after),json.loads(a.decisions.read_text()))
    with a.output.open('x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2)
    print(json.dumps(result,ensure_ascii=False))
