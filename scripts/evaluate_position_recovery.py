"""Replay fixed observed pitch coordinates; never claim measured position accuracy."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.live_feedback import LiveAnalyzer
from app.position_guard import PositionGuard, DisplayPositionGuard


class LegacyPositionGuard:
    """Frozen pre-fix behavior, including replacing the anchor with rejected input."""
    def __init__(self, max_speed=12., max_gap=.6):
        self.previous={};self.max_speed=max_speed;self.max_gap=max_gap

    def filter(self,t,teams):
        current={};output={};rejected=0
        for team,rows in teams.items():
            kept=[]
            for tid,x,y in rows:
                key=(team,tid)
                if not all(math.isfinite(v) for v in (t,x,y)):
                    rejected+=1;continue
                current[key]=(t,x,y);prior=self.previous.get(key)
                if prior and 0<t-prior[0]<=self.max_gap and math.hypot(x-prior[1],y-prior[2])/(t-prior[0])>self.max_speed:
                    rejected+=1;continue
                kept.append((tid,x,y))
            output[team]=kept
        self.previous=current
        return output,rejected


class LegacyDisplayPositionGuard:
    def __init__(self,max_speed=12.,max_gap=.6):
        self.previous={};self.max_speed=max_speed;self.max_gap=max_gap

    def filter(self,t,raw,proposed):
        current={};result={};fallbacks=dropped=0
        lookup={(team,tid):(x,y) for team,rows in raw.items() for tid,x,y in rows}
        for team,rows in proposed.items():
            kept=[]
            for tid,x,y in rows:
                key=(team,tid)
                if key not in lookup:continue
                old=self.previous.get(key)
                if old and 0<t-old[0]<=self.max_gap:
                    limit=self.max_speed*(t-old[0])
                    if math.hypot(x-old[1],y-old[2])>limit:
                        x,y=lookup[key];fallbacks+=1
                        if math.hypot(x-old[1],y-old[2])>limit:
                            dropped+=1;continue
                kept.append((tid,x,y));current[key]=(t,x,y)
            result[team]=kept
        self.previous=current
        return result,{'raw_fallbacks':fallbacks,'omitted':dropped}


def flattened(teams):
    return {(team,str(tid)):(float(x),float(y)) for team,rows in teams.items() for tid,x,y in rows}


def evaluate(rows,guard_class=PositionGuard,display_guard_class=DisplayPositionGuard):
    guard=guard_class();display=display_guard_class();analyzer=LiveAnalyzer(1,pitch_width=60,fps=5)
    result={'frames':len(rows),'input_observations':0,'retained':0,'rejected':0,'display_retained':0,
            'display_omitted':0,'display_raw_fallbacks':0,'accepted_short_gap_speed_violations':0,
            'display_short_gap_speed_violations':0,'accepted_short_gap_comparisons':0,
            'display_short_gap_comparisons':0,'output_coordinates_not_in_input':0,
            'adjacent_visible_pairs':0,'alerts':[],'position_error_m':None,'identity_error':None}
    history={'accepted':{},'display':{}};frames=[];previous_keys=set()
    for row in rows:
        t=row['time'];raw=row['raw_positions'];input_points=flattened(raw)
        guarded,rejected=guard.filter(t,raw)
        result['input_observations']+=sum(map(len,raw.values()))
        result['retained']+=sum(map(len,guarded.values()));result['rejected']+=rejected
        foot={str(item['id']):item['display'] for item in row.get('foot_filter',[])}
        proposed={team:[(tid,*foot.get(str(tid),(x,y))) for tid,x,y in people] for team,people in guarded.items()}
        shown,checks=display.filter(t,guarded,proposed)
        result['display_retained']+=sum(map(len,shown.values()))
        result['display_omitted']+=checks['omitted'];result['display_raw_fallbacks']+=checks['raw_fallbacks']
        current_keys=set(flattened(shown));result['adjacent_visible_pairs']+=len(previous_keys & current_keys);previous_keys=current_keys
        for kind,values in [('accepted',guarded),('display',shown)]:
            points=flattened(values)
            for key,(x,y) in points.items():
                old=history[kind].get(key)
                if old and 0<t-old[0]<=.6+1e-9:
                    result[kind+'_short_gap_comparisons']+=1
                    result[kind+'_short_gap_speed_violations']+=int(math.hypot(x-old[1],y-old[2])/(t-old[0])>12+1e-9)
                history[kind][key]=(t,x,y)
                if kind=='accepted' and input_points.get(key)!=(x,y):result['output_coordinates_not_in_input']+=1
        ready=row.get('camera_ready',True) and all(len(guarded.get(team,[]))<=11 for team in ('home','away'))
        if ready:alerts=analyzer.update(t,guarded.get('home',[]),guarded.get('away',[]))
        else:analyzer.interrupt_observations(t);alerts=[]
        result['alerts'] += [{'time':a['time'],'kind':a['kind']} for a in alerts]
        frames.append({'time':t,'accepted':guarded,'display':shown,'rejected':rejected,'alerts':alerts})
    return {'metrics':result,'frames':frames}


def run(trace,output):
    trace,output=Path(trace),Path(output);output.mkdir(parents=True,exist_ok=False)
    rows=[json.loads(line) for line in trace.read_text(encoding='utf-8').splitlines()]
    before=evaluate(rows,LegacyPositionGuard,LegacyDisplayPositionGuard);after=evaluate(rows)
    result={'source':str(trace.resolve()),'source_sha256':hashlib.sha256(trace.read_bytes()).hexdigest(),
            'before':before['metrics'],'after':after['metrics'],
            'limits':['Fixed model-estimated coordinates; no true player-foot ground truth.',
                      'No detector or identity tracker rerun. Position guard does not repair ID switches.',
                      'No recovery/interpolation of missing players. Input points only.',
                      'Coaching replay uses camera readiness and team-count gates, not complete production state.']}
    for name,arm in [('before',before),('after',after)]:
        (output/(name+'-frames.json')).write_text(json.dumps(arm['frames'],ensure_ascii=False),encoding='utf-8')
    (output/'comparison.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('trace');p.add_argument('output');a=p.parse_args();run(a.trace,a.output)
