import sys, json, collections
from pathlib import Path
import cv2,numpy as np
from ultralytics import YOLO
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.team_suggestions import TeamSuggestions, shirt_histogram

def iou(a,b):
 x1=max(a[0],b[0]);y1=max(a[1],b[1]);x2=min(a[2],b[2]);y2=min(a[3],b[3]); inter=max(0,x2-x1)*max(0,y2-y1);return inter/max(1e-10,(a[2]-a[0])*(a[3]-a[1])+(b[2]-b[0])*(b[3]-b[1])-inter)
def evaluate(name,video,path,weights,device,start,max_distance):
 d=json.loads(Path(path).read_text(encoding='utf-8-sig')); counts=collections.Counter(p.get('team') for p in d['playerInfo'] if p.get('player_position') in ('DF','MF','FW') and p.get('team'));teams=[x for x,_ in counts.most_common(2)];assert len(teams)==2
 m={p['player_sid']:(teams.index(p.get('team')) if p.get('player_position') in ('DF','MF','FW') and p.get('team') in teams else None) for p in d['playerInfo']}; gt={int(a['frame']):a for a in d['tag']};est=TeamSuggestions(max_distance=max_distance); model=YOLO(weights);cap=cv2.VideoCapture(video);cap.set(cv2.CAP_PROP_POS_FRAMES,start);rows=[]
 for f in range(start,start+50):
  ok,frame=cap.read()
  if not ok:break
  r=model.track(frame,persist=True,tracker='bytetrack.yaml',classes=[0],verbose=False,device=device,imgsz=640,conf=.35)[0];b=r.boxes
  tracks=[] if b is None or b.id is None else list(zip(b.xyxy.cpu().numpy(),b.id.int().cpu().tolist()))
  groups=est.update(frame,tracks)
  if f<start+10:continue
  targets=[]
  for a in gt[f]['data']:
   if a.get('id') in m and len(a.get('tag',[]))==4:
    x,y,w,h=map(int,a['tag']);targets.append(([x,y,x+w,y+h],m[a['id']]))
  pairs=sorted(((iou(bb,t[0]),i,j) for i,(bb,_) in enumerate(tracks) for j,t in enumerate(targets)),reverse=True);seen_i=set();seen_j=set();match={}
  for ov,i,j in pairs:
   if ov<.5:break
   if i in seen_i or j in seen_j:continue
   seen_i.add(i);seen_j.add(j);match[i]=j
  for i,(_,tid) in enumerate(tracks):
   j=match.get(i);
   feature=shirt_histogram(frame, tracks[i][0]); distances=np.linalg.norm(est.centres-feature[None,:],axis=1) if feature is not None and est.centres is not None else None
   rows.append((groups.get(str(tid)),j is not None,targets[j][1] if j is not None else None, None if distances is None else float(distances.min())))
 cap.release(); choices=[sum(g==t^flip for g,matched,t,dist in rows if matched and t is not None and g is not None) for flip in (0,1)];flip=int(choices[1]>choices[0]);c=collections.Counter()
 for g,matched,t,dist in rows:
  if not matched:c['unmatched']+=1;c['unmatched_assigned']+=int(g is not None)
  elif t is None:c['nonfield']+=1;c['nonfield_assigned']+=int(g is not None)
  else:
   c['field_total']+=1
   if g is None:c['unknown']+=1
   elif g==(t^flip):c['correct']+=1
   else:c['wrong']+=1
 return {'game':name,'centres_available':est.centres is not None,'frames_warmup':10,'frames_test':40,'counts':dict(c),'score_mapping':'GT chooses permutation on test; optimistic evaluation only'}
if __name__ == '__main__':
 import argparse
 p=argparse.ArgumentParser(description='Compare colour suggestion abstention on a single labelled AI Hub video; never sends data elsewhere.')
 p.add_argument('--video',required=True);p.add_argument('--labels',required=True);p.add_argument('--weights',required=True);p.add_argument('--device',default='cpu');p.add_argument('--start',type=int,default=900)
 a=p.parse_args()
 results=[evaluate('baseline',a.video,a.labels,a.weights,a.device,a.start,float('inf')),evaluate('distance_guard',a.video,a.labels,a.weights,a.device,a.start,.4)]
 print(json.dumps(results,ensure_ascii=False,indent=2))
