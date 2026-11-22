"""Apply human-confirmed boundaries only after reproducing their exact observations.

No synthetic observations, classifier edits, or global raw-ID aliases. Source
fingerprinting is enforced by the caller. Each alias expires after a new loss.
"""
from .low_confidence_recovery import iou


class ReviewedReconnector:
    def __init__(self, decisions, max_gap=.6):
        negatives={frozenset(map(str,p)) for p in decisions.get('blocked',[])}
        self.plans=[dict(p, validated=False, active=False, retired=False, last=None)
                    for p in decisions.get('approved',[])
                    if frozenset(map(str,p['pair'])) not in negatives]
        self.max_gap=max_gap
        self.last_time=None
        self.seen={}

    def update(self,t,tracked):
        rows={str(int(r[4])):r for r in tracked}
        events=[]
        if self.last_time is not None and t<=self.last_time:
            for p in self.plans:p['retired']=True;p['active']=False
        self.last_time=t
        aliases={}
        for p in self.plans:
            a,b=map(str,p['pair']);boundary=p['boundary'];end,start=boundary['end'],boundary['start']
            if p['retired']:continue
            if abs(t-end)<1e-5:
                p['validated']=a in rows and iou(rows[a],boundary['before_box'])>=.9
            if not p['active'] and abs(t-start)<1e-5:
                valid=(p['validated'] and b in rows and a not in rows and b not in self.seen
                       and abs(self.seen.get(a,float('-inf'))-end)<1e-5
                       and iou(rows[b],boundary['after_box'])>=.9)
                if not valid:
                    p['retired']=True
                    events.append({'question':p['question'],'action':'rejected','reason':'reviewed_boundary_not_reproduced'})
                    continue
                p['active']=True;p['last']=t
                events.append({'question':p['question'],'action':'linked','from':b,'to':a,'time':t})
            if not p['active']:
                continue
            if a in rows or t-p['last']>self.max_gap+1e-8:
                p['retired']=True;p['active']=False
                events.append({'question':p['question'],'action':'retired','reason':'collision_or_new_loss'})
                continue
            if b in rows:
                p['last']=t
            aliases[b]=a
        duplicate_targets={target for target in aliases.values() if list(aliases.values()).count(target)>1}
        if duplicate_targets:
            for p in self.plans:
                if str(p['pair'][0]) in duplicate_targets:
                    p['retired']=True;p['active']=False
                    events.append({'question':p['question'],'action':'retired','reason':'simultaneous_review_alias_conflict'})
            aliases={key:value for key,value in aliases.items() if value not in duplicate_targets}
        self.seen.update({k:t for k in rows})
        return aliases,events


def alias_teams(teams, aliases):
    return {team:[(int(aliases.get(str(tid),str(tid))),x,y) for tid,x,y in rows] for team,rows in teams.items()}


def alias_players(players, aliases):
    return [{**p,'id':aliases[p['id']],'source_id':p['id'],'identity_basis':'human_reviewed_boundary'}
            if p['id'] in aliases else dict(p) for p in players]


def alias_boxes(boxes, aliases):
    """Coaching's rendered lane endpoints must use the same IDs as its inputs."""
    return {int(aliases.get(str(tid),str(tid))):box for tid,box in boxes.items()}
