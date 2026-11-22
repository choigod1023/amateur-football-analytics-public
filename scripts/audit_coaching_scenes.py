"""Audit measured alert inputs and extract original video evidence, never label it."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys

import cv2


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def box_members(players, length=89., direction=1):
    return [str(tid) for tid, x, y in players
            if length/2-16.5 <= x*direction <= length/2 and abs(y) <= 20.16]


def interval_frames(frames, start, end, fps=5):
    return [(sample/fps, frames[sample]) for sample in sorted(frames)
            if start <= sample/fps < end]


def evidence(analyzer, alert, second_metrics, smooth):
    t=alert['time'];second=math.floor(t)-1
    result={'alert':alert,'condition_second':second,
            'ball_observed':False,'ground_truth_verdict':None,
            'ground_truth_limit':'Positions, team labels and track identities are model estimates.'}
    if alert['kind']=='box_attack':
        samples=interval_frames(analyzer.frames,second-1,second+1)
        result['box_samples']=[{'time':at,'ids':box_members(frame['team'],analyzer.length,analyzer.direction),
                                'home_seen':len(frame['team']),'away_seen':len(frame['other'])}
                               for at,frame in samples]
        result['sample_count']=len(samples)
        result['minimum_box_count']=min((len(s['ids']) for s in result['box_samples']),default=None)
    elif alert['kind']=='gap_wide':
        if hasattr(analyzer, 'gap_series'):
            result['trigger_aggregation']='supported_samples_per_second'
            result['trigger_seconds']=[{'second':s,**analyzer.gap_series[s]}
                                       for s in range(second-4,second+1) if s in analyzer.gap_series]
        else:
            result['trigger_aggregation']='last_sample_per_second'
            result['trigger_seconds']=[{'second':s,'gap_m':analyzer.series['team'][s]['attack_line']-analyzer.series['team'][s]['defence_line']}
                                       for s in range(second-4,second+1) if s in analyzer.series['team']]
        values=[]
        for at,frame in interval_frames(analyzer.frames,second-4,second+1):
            metric=second_metrics(frame['team'],frame['other'],analyzer.direction,analyzer.minimum)
            values.append({'time':at,'home_seen':len(frame['team']),'away_seen':len(frame['other']),
                           'gap_m':metric['attack_line']-metric['defence_line'] if metric else None})
        result['all_samples']=values
        result['observed_samples']=sum(v['gap_m'] is not None for v in values)
        result['samples_over_32m']=sum(v['gap_m'] is not None and v['gap_m']>32 for v in values)
    elif alert['kind']=='line_drop':
        line=smooth({s:m['opponent_back_line'] for s,m in analyzer.series['other'].items()})
        result['trigger_comparisons']=[{'from_second':second-d,'to_second':second,'change_m':line[second]-line[second-d]}
                                      for d in range(1,11) if second in line and second-d in line and line[second]-line[second-d]>=14]
        result['retreat_evidence']=analyzer.retreat_evidence(second)
        result['line_samples']=[{'second':s,'smoothed_line_m':line[s]} for s in sorted(line) if second-10<=s<=second]
        # These are tracked IDs, not independently verified same people.
        ends={}
        for s in range(second-10,second+1):
            frames=interval_frames(analyzer.frames,s,s+1)
            if frames:ends[s]={str(tid):x*analyzer.direction for tid,x,y in frames[-1][1]['team']}
        result['shared_track_displacements']=[{'from_second':s,'to_second':second,
            'tracks':[{'id':tid,'retreat_m':ends[s][tid]-ends[second][tid]} for tid in sorted(ends[s].keys()&ends[second].keys())]}
            for s in ends if s<second and second in ends]
    return result


def replay(trace):
    from app.live_feedback import LiveAnalyzer
    from app.position_guard import PositionGuard
    from app.report_scenes import second_metrics
    from app.event_miner import smooth
    analyzer=LiveAnalyzer(1,pitch_width=60,fps=5);guard=PositionGuard();results=[]
    for line in Path(trace).read_text(encoding='utf-8').splitlines():
        row=json.loads(line);t=row['time'];teams,_=guard.filter(t,row['raw_positions'])
        ready=row.get('camera_ready',True) and all(len(teams.get(team,[]))<=11 for team in ('home','away'))
        if not ready:analyzer.interrupt_observations(t);continue
        for alert in analyzer.update(t,teams.get('home',[]),teams.get('away',[])):
            results.append(evidence(analyzer,alert,second_metrics,smooth))
    return results


def extract(video, output, times, ffmpeg):
    cap=cv2.VideoCapture(str(video));fps=cap.get(cv2.CAP_PROP_FPS);duration=cap.get(cv2.CAP_PROP_FRAME_COUNT)/fps
    metadata=[]
    try:
        for t in times:
            start=max(0,t-3);end=min(duration,t+3)
            clip=output/f'scene-{t:02d}.mp4'
            cmd=[str(ffmpeg),'-hide_banner','-loglevel','error','-ss',str(start),'-i',str(video),'-t',str(end-start),
                 '-an','-c:v','libx264','-preset','veryfast','-crf','20','-movflags','+faststart',str(clip)]
            subprocess.run(cmd,check=True)
            images=[]
            for sample in (t-2,t,t+2):
                cap.set(cv2.CAP_PROP_POS_FRAMES,round(sample*fps));ok,frame=cap.read()
                if not ok:raise ValueError('Failed source frame decode')
                path=output/f'scene-{t:02d}-frame-{sample:02d}.jpg'
                if not cv2.imwrite(str(path),frame,[cv2.IMWRITE_JPEG_QUALITY,94]):raise ValueError('Image save failed')
                images.append({'time':sample,'file':path.name,'sha256':sha(path)})
            check=cv2.VideoCapture(str(clip));count=check.get(cv2.CAP_PROP_FRAME_COUNT)
            check.set(cv2.CAP_PROP_POS_FRAMES,max(0,int(count)-1));ok,_=check.read();check.release()
            if not ok:raise ValueError('Extracted clip last frame does not decode')
            metadata.append({'alert_time':t,'start':start,'end':end,'clip':clip.name,'sha256':sha(clip),'images':images})
    finally:cap.release()
    return metadata


def main():
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('output',type=Path)
    p.add_argument('--code-root',type=Path,default=Path(__file__).resolve().parents[1]);p.add_argument('--extract',action='store_true')
    a=p.parse_args();sys.path.insert(0,str(a.code_root.resolve()));a.output.mkdir(parents=True,exist_ok=False)
    traces=a.root/'work/minimap-tracking-validation-20261115/role'
    data={'code_root':str(a.code_root.resolve()),'source_code_sha256':{},'models':{}}
    for name in ('app/live_feedback.py','app/position_guard.py','app/report_scenes.py','app/review_text.py'):
        data['source_code_sha256'][name]=sha(a.code_root/name)
    for name in ('app/coaching_fields.py','app/live_publish.py'):
        if (a.code_root/name).is_file():
            data['source_code_sha256'][name]=sha(a.code_root/name)
    for model in ('clean_baseline','clean_candidate'):
        path=traces/model/'observations.jsonl';data['models'][model]={'trace_sha256':sha(path),'events':replay(path)}
    if a.extract:
        data['media']=extract(a.root/'work/live-dashboard-validation-20261113/replay-1950-2010.mp4',a.output,
                              [7,15,20,23,29,35],a.root/'work/ffmpeg-local/ffmpeg-9.0.2-essentials_build/bin/ffmpeg.exe')
    (a.output/'audit.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:[{'time':e['alert']['time'],'kind':e['alert']['kind']} for e in v['events']] for k,v in data['models'].items()}))


if __name__=='__main__':main()
