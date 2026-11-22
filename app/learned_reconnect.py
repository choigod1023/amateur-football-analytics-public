"""Small supervised same-person scorer and causal, abstaining tracklet linker.

Features contain no video, person, question or raw-track identifiers. A score is
not a calibrated probability of identity. Geometry and ambiguity gates remain.
"""
import math
import cv2
import numpy as np

FEATURES=['upper_h','upper_s','upper_v','lower_h','lower_s','lower_v','height_change','motion_per_second','gap_log']


def validate_eval_group(model,group):
    if not group or group in model['train_video_groups']:
        raise ValueError('Evaluation video group was used for training or is missing')


def descriptor(frame,box):
    h,w=frame.shape[:2];x1,y1,x2,y2=map(float,box[:4]);bw,bh=x2-x1,y2-y1
    if not np.isfinite(box[:4]).all() or min(bw,bh)<=0:return None
    out=[]
    for top,bottom in ((.15,.5),(.5,.9)):
        crop=frame[max(0,int(y1+top*bh)):min(h,int(y1+bottom*bh)+1),max(0,int(x1+.15*bw)):min(w,int(x2-.15*bw)+1)]
        if crop.size<18:return None
        hsv=cv2.cvtColor(crop,cv2.COLOR_BGR2HSV)
        for channel,bins,high in ((0,12,180),(1,8,256),(2,8,256)):
            hist=np.histogram(hsv[:,:,channel],bins=bins,range=(0,high))[0].astype(float)+.01
            out.append(hist/hist.sum())
    return out


def pair_features(a,b,box_a,box_b,gap):
    if a is None or b is None:return None
    distances=[math.sqrt(max(0.,1-float(np.sqrt(x*y).sum()))) for x,y in zip(a,b)]
    ha=max(1.,box_a[3]-box_a[1]);hb=max(1.,box_b[3]-box_b[1]);height=(ha+hb)/2
    displacement=math.hypot((box_b[0]+box_b[2]-box_a[0]-box_a[2])/2,box_b[3]-box_a[3])/height
    return np.array(distances+[abs(math.log(hb/ha)),displacement/(1+max(0,gap)),math.log1p(max(0,gap))])


def fit_scorer(x,y):
    x=np.asarray(x,float);y=np.asarray(y,float)
    if len(x)<4 or set(y)!={0.,1.}:raise ValueError('At least four labelled pairs and both classes required')
    mean=x.mean(axis=0);scale=np.maximum(x.std(axis=0),.1);z=(x-mean)/scale
    weights=np.zeros(x.shape[1]);bias=0.
    for _ in range(1200):
        probability=1/(1+np.exp(-np.clip(z@weights+bias,-30,30)));error=probability-y
        weights-=.05*(z.T@error/len(y)+.15*weights);bias-=.05*error.mean()
    return {'features':FEATURES,'mean':mean.tolist(),'scale':scale.tolist(),'weights':weights.tolist(),'bias':float(bias),
            'threshold':.90,'ambiguity_margin':.15,'training_pairs':len(y),'regularization':.15}


def score(model,features):
    if features is None:return 0.
    if model['features']!=FEATURES:raise ValueError('Incompatible feature schema')
    z=(np.asarray(features)-model['mean'])/model['scale']
    logit=float(z@np.asarray(model['weights'])+model['bias'])
    return 1/(1+math.exp(-max(-30,min(30,logit))))


class LearnedLinker:
    def __init__(self,model=None,max_gap=2.5):
        self.model=model;self.max_gap=max_gap;self.memory={};self.previous_time=None

    def update(self,t,frame,tracks):
        if self.previous_time is not None and t<=self.previous_time:self.memory={}
        self.previous_time=t
        current={str(int(row[4])):row for row in tracks}
        self.memory={k:v for k,v in self.memory.items() if t-v['time']<=10}
        groups={}
        for raw in current:
            if raw in self.memory:groups.setdefault(self.memory[raw]['canonical'],[]).append(raw)
        for members in groups.values():
            if len(members)>1:
                for raw in members:self.memory[raw]['canonical']=raw
        reserved={self.memory[k]['canonical'] for k in current if k in self.memory}
        proposals=[];observations={};events=[]
        for raw,row in current.items():
            desc=descriptor(frame,row[:4]);observations[raw]=desc
            if raw in self.memory:continue
            choices=[]
            for old,previous in self.memory.items():
                gap=t-previous['time']
                if old in current or previous['canonical'] in reserved or previous['n']<3 or not 0<gap<=self.max_gap:continue
                a=previous['box'];b=row[:4];ha=max(1,a[3]-a[1]);hb=max(1,b[3]-b[1])
                if not .5<=hb/ha<=2:continue
                distance=math.hypot((b[0]+b[2]-a[0]-a[2])/2,b[3]-a[3])/((ha+hb)/2)
                allowed=min(3.,.8+2.5*gap)
                if distance>=allowed:continue
                features=pair_features(previous['descriptor'],desc,a,b,gap)
                value=float(score(self.model,features) if self.model else 1-distance/allowed)
                choices.append((value,old,previous['canonical']))
            choices.sort(reverse=True)
            threshold=self.model['threshold'] if self.model else .5
            margin=self.model['ambiguity_margin'] if self.model else .15
            if choices and choices[0][0]>=threshold and (len(choices)==1 or choices[0][0]-choices[1][0]>=margin):
                proposals.append((raw,*choices[0]))
        # Mutual exclusivity: do not resolve competing births by arbitrary order.
        target_counts={canonical:sum(p[3]==canonical for p in proposals) for _,_,_,canonical in proposals}
        accepted={raw:(old,canonical,value) for raw,value,old,canonical in proposals if target_counts[canonical]==1}
        aliases={}
        for raw,row in current.items():
            prior=self.memory.get(raw);canonical=prior['canonical'] if prior else raw
            if raw in accepted:
                old,canonical,value=accepted[raw];events.append({'time':t,'raw':raw,'previous_raw':old,'canonical':canonical,'score':value})
            # A previously lost raw ID returning beside its alias is a collision.
            if canonical in aliases.values():canonical=raw
            aliases[raw]=canonical
            self.memory[raw]={'time':t,'box':list(map(float,row[:4])),'descriptor':observations[raw],
                              'canonical':canonical,'n':prior['n']+1 if prior else 1}
        return aliases,events
