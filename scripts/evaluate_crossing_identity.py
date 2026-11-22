"""Compare motion-only versus multi-frame crossing hypotheses, GT only for scoring."""
import argparse,json,itertools,sys,hashlib
from pathlib import Path
import cv2,numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.identity_guard import _overlap
from app.learned_reconnect import descriptor
from app.crossing_identity import decide_crossing


def evaluate(trace,video,own=False):
    content=Path(trace).read_text(encoding='utf-8')
    data=[json.loads(x) for x in content.splitlines()] if own else json.loads(content)
    rows=[{'time':r['time'] if own else r['frame']/30,'window':r.get('window',0),
           'boxes':{str(int(b[4])):b[:4] for b in r['source_tracks' if own else 'tracks']},
           'gt':{} if own else {str(raw):str(gt) for gt,raw in r['matches']}} for r in data]
    def clean(i,ids):
        boxes=rows[i]['boxes']
        return all(k in boxes and all(other==k or _overlap(boxes[k],b)<.15 for other,b in boxes.items()) for k in ids)
    events=[];last={}
    for i,r in enumerate(rows):
        for pair in itertools.combinations(sorted(r['boxes']),2):
            if _overlap(*(r['boxes'][k] for k in pair))<.3:continue
            key=(r['window'],pair)
            if r['time']-last.get(key,-1e9)<3:continue
            before=[j for j in range(max(0,i-6),i) if rows[j]['window']==r['window'] and clean(j,pair)][-3:]
            after=[j for j in range(i+1,min(len(rows),i+9)) if rows[j]['window']==r['window'] and clean(j,pair)][:3]
            if len(before)!=3 or len(after)!=3:continue
            last[key]=r['time'];events.append({'time':r['time'],'ids':pair,'before':before,'after':after})
    cap=cv2.VideoCapture(str(video));features={}
    for index in sorted({j for e in events for j in e['before']+e['after']}):
        r=rows[index];cap.set(cv2.CAP_PROP_POS_MSEC,r['time']*1000);ok,frame=cap.read()
        if not ok:raise RuntimeError('Video decode failed')
        features[index]={tid:descriptor(frame,box) for tid,box in r['boxes'].items()}
    cap.release()
    def sequences(indices,pair):
        return [[{'time':rows[j]['time'],'box':rows[j]['boxes'][k],'descriptor':features[j][k]} for j in indices] for k in pair]
    def identity(indices,tid):
        v=[rows[j]['gt'].get(tid) for j in indices]
        return v[0] if len(set(v))==1 and v[0] is not None else None
    summary={name:{'keep':0,'swap':0,'review':0,'correct':0,'wrong':0,'unscored':0} for name in ['motion_only','multiframe']}
    for e in events:
        result=decide_crossing(sequences(e['before'],e['ids']),sequences(e['after'],e['ids']))
        m=result['motion_costs'];baseline='review' if m is None else 'swap' if m[1]<m[0] else 'keep'
        candidate={'keep_candidate':'keep','swap_candidate':'swap','review':'review'}[result['decision']]
        a=[identity(e['before'],k) for k in e['ids']];b=[identity(e['after'],k) for k in e['ids']]
        truth=None
        if None not in a+b and len(set(a))==len(set(b))==2:
            if a==b:truth='keep'
            elif a==b[::-1]:truth='swap'
        e.update(result=result,ground_truth=truth,baseline=baseline)
        for name,decision in [('motion_only',baseline),('multiframe',candidate)]:
            summary[name][decision]+=1
            if decision!='review':summary[name]['unscored' if truth is None else 'correct' if decision==truth else 'wrong']+=1
    return {'summary':summary,'events':events,'source_sha256':hashlib.sha256(Path(trace).read_bytes()).hexdigest(),
            'video_sha256':hashlib.sha256(Path(video).read_bytes()).hexdigest(),'note':'No training; candidate scoring only. GT from cached IoU matches, not exhaustive identity truth.'}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('trace');p.add_argument('video');p.add_argument('output');p.add_argument('--own',action='store_true');a=p.parse_args()
    result=evaluate(a.trace,a.video,a.own)
    with Path(a.output).open('x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2)
    print(result['summary'])
