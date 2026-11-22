"""Evaluate scene-specific answers, refusing a changed source or stale question."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys

sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parent)]
from app.difference_review import fingerprint
from app.reviewed_track_breaks import split_reviewed_tracks
from app.pitch_map import fit
from app.live_feedback import LiveAnalyzer
from build_tactical_report import metre_rows
from build_team_minimap import parse_schedule


def main():
    p=argparse.ArgumentParser();p.add_argument('work',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False)
    store=a.work/'human-labels/public-own-match-review-20261111'
    source=a.work/'evidence-policy-eval-20261113/h2_ov3.json'
    raw=source.read_bytes();sha=hashlib.sha256(raw).hexdigest()
    audit=json.loads((a.work/'live-dashboard-validation-20261113/track-audit.json').read_text(encoding='utf-8'))
    if sha!=audit['source_sha256']:raise ValueError('Source changed since review selection')
    originals={str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in store.rglob('*.json')}
    data=json.loads(raw);decisions={};reviews=[];corrections=[]
    queue=json.loads((store/'differences/queue.json').read_text(encoding='utf-8'))
    for item in queue['items']:
        match=re.fullmatch(r'jump-review-(\d+)-(\d+(?:\.\d+)?)',item.get('case_key',''))
        if not match:continue
        answer_path=store/'differences/answers'/f"{item['id']}.json"
        if not answer_path.exists():continue
        answer=json.loads(answer_path.read_text(encoding='utf-8'))
        if answer.get('fingerprint')!=fingerprint(item) or answer.get('source')!='human' or answer.get('id')!=item['id']:
            raise ValueError('Stale or invalid human answer')
        tid,t=match[1],float(match[2]);frame=round((t-data['first_second'])*data['fps'])
        confirmed=[]
        for token,expected in zip(item['review_tokens'],[frame-1,frame]):
            meta=json.loads((store/'pending'/f'{token}.json').read_text(encoding='utf-8'))
            row=next(r for r in data['tracks'][tid] if r['frame']==expected)
            box=meta['people'][0]['bbox'];normalized=[v/d for v,d in zip(row['box'],[1920,1080,1920,1080])]
            if any(abs(x-y)>1e-6 for x,y in zip(box,normalized)):raise ValueError('Reviewed box/source mismatch')
            label_path=store/(hashlib.sha256((token+':'+tid).encode()).hexdigest()[:32]+'.json')
            if label_path.exists():
                label=json.loads(label_path.read_text(encoding='utf-8'))
                team={'team_a':'A','team_b':'B'}.get(label.get('team_group')) if label.get('role')=='player' else None
                if team:
                    confirmed.append((expected,team))
                    corrections.append((tid,expected,team,'direct_human'))
        verdict=answer['verdict']
        if verdict not in ('same','different','unclear'):raise ValueError('Invalid verdict')
        if verdict=='same' and len(set(team for _,team in confirmed))==1:
            team=confirmed[0][1]
            for expected in (frame-1,frame):
                if expected not in [f for f,_ in confirmed]:corrections.append((tid,expected,team,'human_same_pair'))
        decisions.setdefault(tid,[]).append({'frame':frame,'verdict':verdict})
        reviews.append({'id':item['id'],'track':tid,'frame':frame,'verdict':verdict})
    revised,applied=split_reviewed_tracks(data,decisions)
    for tid,frame,team,basis in corrections:
        target=tid
        for split in applied:
            if split['source_track']==tid and frame>=split['frame']:target=split['new_track']
        row=next(r for r in revised['tracks'][target] if r['frame']==frame)
        row['team']=team
    calibration=json.loads((store/'calibration/calibrations.json').read_text(encoding='utf-8'))['cam3'];fitted=fit(calibration)
    outputs={}
    for name,value in [('before',data),('after',revised)]:
        frames,_=metre_rows(value['tracks'],fitted,parse_schedule('0:-1.8,6.8;1950:0.3,0.3'),(1.003087,-.001614,-7.41,5.61),0,value['frames'])
        engine=LiveAnalyzer(1,fitted['pitch']['length'],fitted['pitch']['width'],value['fps']);alerts=[]
        for f in range(value['frames']):
            teams=frames.get(f,{})
            alerts+=engine.update(value['first_second']+f/value['fps'],teams.get('B',[]),teams.get('A',[]))
        outputs[name]={'alerts':alerts,'counts':dict(Counter(x['kind'] for x in alerts)),'tracks':len(value['tracks'])}
    report={'source_sha256':sha,'reviews':reviews,'splits':applied,'team_corrections':corrections,'results':outputs,
            'answers_preserved':all(hashlib.sha256(Path(f).read_bytes()).hexdigest()==h for f,h in originals.items()),
            'scope':'Corrections on reviewed development frames and human-confirmed same-person pair only. Not independent accuracy or live-model training. Geometry unchanged.'}
    (a.output/'tracks.json').write_text(json.dumps(revised,ensure_ascii=False),encoding='utf-8')
    (a.output/'comparison.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'reviews':reviews,'splits':applied,'before':outputs['before']['counts'],'after':outputs['after']['counts'],'answers_preserved':report['answers_preserved']}))


if __name__=='__main__':main()
