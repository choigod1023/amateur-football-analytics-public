"""Replay fixed, observed positions with baseline/candidate team assignments.

Alert counts are not coaching truth. Candidate abstention can change geometry.
This evaluates neither new detections nor previously unclassified positions.
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.live_feedback import LiveAnalyzer


def evaluate(rows, key):
    analyzer = LiveAnalyzer(1, 89, 60, 5)
    alerts, visible, blocked = [], 0, 0
    recent = []
    for row in rows:
        people = row[key]
        teams = {team: [(int(p['id']), (p['x']-.5)*89, (p['y']-.5)*60)
                        for p in people if p['team'] == team and p['x'] is not None and p['y'] is not None]
                 for team in ('home', 'away')}
        t = row['time']
        # Match publisher capacity: a classified candidate with an invalid map
        # location still counts; dropping it here would hide capacity failures.
        if any(sum(p['team']==team for p in people)>11 for team in teams):
            blocked += 1
            analyzer.interrupt_observations(t)
            recent = []
        else:
            found = analyzer.update(t, teams['home'], teams['away'])
            alerts.extend(found)
            recent = [a for a in recent if 0<=t-a['time']<=8]+found
        visible += bool(recent)
    return {'capacity_blocked_frames':blocked, 'visible_alert_frames':visible,
            'alert_counts':dict(Counter(a['kind'] for a in alerts)),
            'alerts':[{'time':a['time'],'kind':a['kind'],'title':a['title']} for a in alerts]}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('predictions',type=Path);p.add_argument('output',type=Path)
    args=p.parse_args()
    rows=[json.loads(line) for line in args.predictions.read_text(encoding='utf-8').splitlines()]
    result={name:evaluate(rows,key) for name,key in [('before','baseline'),('candidate','candidate_on_baseline_pool')]}
    result['deployment_gate']='FAIL: current-scene human team/identity truth missing; abstention reduces coverage. Alert count cannot approve deployment.'
    result['limitations']='Fixed baseline player pool, normalized valid positions only; no new detector run. Ground-truth tactical events are unavailable.'
    with args.output.open('x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2)
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
