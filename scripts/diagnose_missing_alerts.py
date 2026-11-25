"""Reproduce missing-alert causes against frozen positions; labels are development evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import types

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from app.live_feedback import LiveAnalyzer
from app.pitch_map import fit
from app.event_miner import smooth
from app.tactical_concepts import runs_in_behind
from app.report_scenes import second_metrics
from app.difference_review import fingerprint
from build_tactical_report import metre_rows
from build_team_minimap import parse_schedule

BASELINE_COMMIT = '6dc59a7'


def replay(cls, data, frames):
    trace, alerts = [], []
    class Traced(cls):
        def _check(self, t, second):
            record = None
            if 1970 <= t <= 1982 or 2084 <= t <= 2097:
                series = getattr(self, 'isolation_series', self.series['team'])
                recent = [series.get(s) for s in range(second-5, second+1)]
                back = smooth({s: m['opponent_back_line'] for s,m in self.series['team'].items()})
                paths = {tid: [(f,u,y) for f,u,y in p if f >= (second-6)*self.fps] for tid,p in self.paths['team'].items()}
                runs = runs_in_behind(paths, back, self.fps, window=4)
                record = {'time': t, 'closed_second': second,
                    'isolation_seconds': [{'second': s, 'metric': None if m is None else {k:m[k] for k in ('centre','leader_isolation','observed_samples','leader_ids') if k in m}}
                                          for s,m in zip(range(second-5,second+1),recent)],
                    'isolation_condition': bool(all(m and m['centre']>0 and m['leader_isolation']>12 for m in recent)),
                    'run_candidates': runs, 'last_actionable_time':self.last_any,
                    'kind_cooldowns':dict(self.last_alert)}
            result = super()._check(t,second)
            if record is not None:
                record['emitted'] = [{'time':a['time'],'kind':a['kind'],'polarity':a['polarity'],'evidence':a.get('evidence')} for a in result]
                trace.append(record)
            return result
    analyzer=Traced(1,89,60,data['fps'])
    for f in range(data['frames']):
        teams=frames.get(f,{})
        alerts += analyzer.update(data['first_second']+f/data['fps'],teams.get('B',[]),teams.get('A',[]))
    return {'alert_count':len(alerts),'alerts':[{'time':a['time'],'kind':a['kind'],'polarity':a['polarity'],'text':a['text'],'evidence':a.get('evidence')} for a in alerts], 'trace':trace}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    snapshot=args.work/'evidence-policy-eval-20261113'
    source=snapshot/'h2_ov3.json'
    before_hash=hashlib.sha256(source.read_bytes()).hexdigest()
    data=json.loads(source.read_text(encoding='utf-8'))
    fitted=fit(json.loads((snapshot/'snapshot/calibration/calibrations.json').read_text(encoding='utf-8'))['cam3'])
    schedule=parse_schedule('0:-1.8,6.8;1950:0.3,0.3')
    bg=(1.003087,-.001614,-7.41,5.61)
    observed,_=metre_rows(data['tracks'],fitted,schedule,bg,0,data['frames'])
    augmented,_=metre_rows(data['tracks'],fitted,schedule,bg,0,data['frames'],include_estimates=True)
    previous=types.ModuleType('previous_live_feedback')
    code=subprocess.check_output(['git','show',BASELINE_COMMIT+':app/live_feedback.py'],cwd=Path(__file__).resolve().parents[1]).decode('utf-8')
    exec(compile(code,'previous_live_feedback.py','exec'),previous.__dict__)
    results={'baseline_observed':replay(previous.LiveAnalyzer,data,observed),
             'candidate_observed':replay(LiveAnalyzer,data,observed),
             'interpolation_counterfactual':replay(previous.LiveAnalyzer,data,augmented)}
    # Count exact evidence in the 4 s window of the interpolated candidate.
    f0=round((2086-data['first_second'])*data['fps']);f1=f0+20
    rows={r['frame']:r for r in data['tracks']['5869'] if f0<=r['frame']<=f1}
    observed_frames=[f for f,r in rows.items() if not r.get('interpolated')]
    interpolated_frames=[f for f,r in rows.items() if r.get('interpolated')]
    report={'baseline_commit':BASELINE_COMMIT,'source_sha256':before_hash,'results':results,
        'run_evidence':{'track':'5869','start':2086,'end':2090,'expected_frames':21,
            'observed_frames':len(observed_frames),'interpolated_frames':len(interpolated_frames),
            'missing_frames':21-len(rows),'required_observed_frames':17,
            'interpolated_times':[data['first_second']+f/data['fps'] for f in interpolated_frames]},
        'isolation_cause':'Last-frame dropout discarded valid earlier observations; diagnostic line_drop also occupied actionable cooldown.',
        'run_cause':'The previously displayed crossing depends on interpolated positions; observed coverage does not reach the unchanged 80% requirement.',
        'limitations':['Development replay on reviewed scenes, not independent accuracy.','Isolation describes the leading position, not a verified continuous identity.','Newly emitted other alerts still require evaluation.']}
    queue_path=args.work/'human-labels/public-own-match-review-20261111/differences/queue.json'
    queue=json.loads(queue_path.read_text(encoding='utf-8'))
    reviewed=[]
    for item in queue['items']:
        if item['id'] not in [f'd{i:04d}' for i in range(1,7)]:continue
        answer_path=queue_path.parent/'answers'/f"{item['id']}.json"
        answer=json.loads(answer_path.read_text(encoding='utf-8'))
        if answer.get('fingerprint')!=fingerprint(item):continue
        reviewed.append({'id':item['id'],'verdict':answer['verdict'],
            'before_alerts':[a for a in results['baseline_observed']['alerts'] if abs(a['time']-item['time'])<=5],
            'after_alerts':[a for a in results['candidate_observed']['alerts'] if abs(a['time']-item['time'])<=5]})
    report['reviewed_scenes']=reviewed
    report['source_unchanged']=hashlib.sha256(source.read_bytes()).hexdigest()==before_hash
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x',encoding='utf-8') as handle:json.dump(report,handle,ensure_ascii=False,indent=2)
    print(json.dumps({'counts':{k:v['alert_count'] for k,v in results.items()},'run_evidence':report['run_evidence'],'source_unchanged':report['source_unchanged']}))


if __name__=='__main__':main()
