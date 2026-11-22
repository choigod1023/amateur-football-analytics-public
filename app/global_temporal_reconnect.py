"""Offline opt-in adapter: same temporal features, global birth assignment."""
from .temporal_reconnect import TemporalLinker, sequence_features, temporal_score
from .learned_reconnect import descriptor
from .global_reconnect import Candidate, assign_candidates
from .clean_track_history import crowded_ids, invalidate_crowded_history


class GlobalTemporalLinker(TemporalLinker):
    def __init__(self,model):
        super().__init__(model)
        self.candidate_audit=[]

    def update(self,t,frame,tracks):
        if self.time is not None and t<=self.time:
            self.memory={}
        self.time=t
        self.memory={k:v for k,v in self.memory.items() if t-v['last']<=10}
        current={str(int(r[4])):r for r in tracks}
        crowded=crowded_ids(current)
        for raw,row in current.items():
            state=self.memory.setdefault(raw,{'first':t,'last':t,'canonical':raw,'history':[],'decided':False})
            if raw in crowded:
                invalidate_crowded_history(state,t)
                continue
            obs={'time':float(t),'box':list(map(float,row[:4])), 'descriptor':descriptor(frame,row[:4])}
            if state['history'] and t-state['last']>.25:
                state['decided']=True
            state['history']=[r for r in state['history'] if t-r['time']<=1.01]
            state['history']=(state['history']+[obs])[-5:]
            state['last']=t
        groups={}
        for raw in current:
            groups.setdefault(self.resolve(raw),[]).append(raw)
        for members in groups.values():
            if len(members)>1:
                for raw in members:
                    self.memory[raw]['canonical']=raw
        reserved={self.resolve(k) for k in current}
        unique={}
        for raw in current:
            state=self.memory[raw]
            if state['decided'] or len(state['history'])<3:
                continue
            state['decided']=True
            for old,previous in self.memory.items():
                gap=state['first']-previous['last']
                canonical=previous['canonical']
                if old in current or canonical in reserved or not 0<gap<=2.5:
                    continue
                x=sequence_features(previous['history'],state['history'])
                if x is None or max(x[9],x[10])>self.model['max_prediction_residual_heights']:
                    continue
                candidate=Candidate(canonical,raw,temporal_score(self.model,x),previous['last'],state['first'],t)
                key=(canonical,raw)
                if key not in unique or candidate.score>unique[key][0].score:
                    unique[key]=(candidate,old)
        try:
            decision=assign_candidates([e for e,_ in unique.values()],now=t,
                threshold=self.model['threshold'],ambiguity_margin=self.model['ambiguity_margin'])
        except ValueError as exc:
            # Bounded overflow fails closed; audit explains missed opportunities.
            decision={'accepted':[],'rejected':[],'error':str(exc)}
        self.candidate_audit.append({'time':float(t),'candidates':[dict(e.__dict__,previous_raw=old) for e,old in unique.values()], 'decision':decision})
        events=[]
        for item in decision['accepted']:
            raw,canonical=item['target'],item['source']
            candidate,old=unique[(canonical,raw)]
            self.memory[raw]['canonical']=canonical
            events.append({'time':float(t),'birth_time':self.memory[raw]['first'],'raw':raw,
                'previous_raw':old,'canonical':canonical,'score':candidate.score,'global_margin':item['global_margin']})
        return {raw:self.resolve(raw) for raw in current},events
