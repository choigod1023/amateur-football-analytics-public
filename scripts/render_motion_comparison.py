"""Render the real replay beside before/after observed-position minimaps."""
import argparse
import json
from pathlib import Path
import subprocess
import cv2
import numpy as np


def main():
    p=argparse.ArgumentParser();p.add_argument('video');p.add_argument('directory',type=Path);p.add_argument('ffmpeg');a=p.parse_args()
    rows={k:[json.loads(x) for x in (a.directory/f'{k}-observations.jsonl').read_text(encoding='utf-8').splitlines()] for k in ('before','after')}
    target=a.directory/'comparison.mp4';temp=a.directory/'comparison-intermediate.mp4'
    if target.exists() or temp.exists():raise ValueError('Refusing overwrite')
    capture=cv2.VideoCapture(a.video);writer=cv2.VideoWriter(str(temp),cv2.VideoWriter_fourcc(*'mp4v'),5,(1280,1000))
    if not capture.isOpened() or not writer.isOpened():raise ValueError('Media unavailable')
    last={'before':None,'after':None}
    try:
        for i,after in enumerate(rows['after']):
            capture.set(cv2.CAP_PROP_POS_MSEC,after['time']*1000);ok,image=capture.read()
            if not ok:raise ValueError('Video ended')
            panel=np.full((1000,1280,3),24,np.uint8);panel[:540,160:1120]=cv2.resize(image,(960,540))
            cv2.putText(panel,f"RECORDED TEST - source {1950+after['time']:.1f}s - estimated calibration",(20,565),0,.65,(230,230,230),1)
            for name,left in [('before',0),('after',640)]:
                r=rows[name][i];cv2.rectangle(panel,(left+20,620),(left+620,950),(45,70,40),-1)
                cv2.rectangle(panel,(left+30,630),(left+610,940),(150,175,145),1);cv2.line(panel,(left+320,630),(left+320,940),(150,175,145),1)
                cv2.circle(panel,(left+320,785),45,(150,175,145),1)
                cv2.putText(panel,name.upper()+' (observed positions only)',(left+24,605),0,.6,(235,235,235),1)
                for person in r['display_players']:
                    if person['x'] is None or person['y'] is None:continue
                    pt=(left+30+round(person['x']*580),630+round(person['y']*310))
                    color=(100,220,210) if person['team']=='home' else (220,155,100)
                    cv2.circle(panel,pt,6,color,-1);cv2.putText(panel,person['id'],(pt[0]+7,pt[1]+3),0,.28,color,1)
                if r['alerts']:last[name]=(r['time'],r['alerts'][-1]['kind'])
                text=last[name][1] if last[name] and r['time']-last[name][0]<=8 else 'no current alert'
                cv2.putText(panel,'Coaching: '+text,(left+24,978),0,.55,(235,235,235),1)
            writer.write(panel)
    finally:capture.release();writer.release()
    subprocess.run([a.ffmpeg,'-hide_banner','-loglevel','error','-i',str(temp),'-c:v','libx264','-preset','veryfast','-crf','20','-pix_fmt','yuv420p','-movflags','+faststart','-n',str(target)],check=True)
    print(target)


if __name__=='__main__':main()
