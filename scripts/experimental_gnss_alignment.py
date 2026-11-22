"""Research only: infer one global ID mapping and time offset, then hold out time.

These annotations are not independent; no inferred mapping is used by the app.
"""
import argparse, ast, csv, json
from pathlib import Path
import cv2
import lap
import numpy as np

def read_csv(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as f: return list(csv.reader(f))

def project(h, point):
    p=h @ np.array([*point, 1.]); return p[:2]/p[2]

def eval_alignment(box_path, gps_path, field_path, geo_path):
    parse=lambda path: {tuple(ast.literal_eval(k)):np.array(v) for k,v in json.loads(Path(path).read_text()).items()}
    field, geo=parse(field_path),parse(geo_path)
    corners=[(0.,0.),(105.,0.),(105.,68.),(0.,68.)]
    image_h=cv2.getPerspectiveTransform(np.array([field[k] for k in corners],np.float32),np.array(corners,np.float32))
    origin=geo[(0.,0.)];common=field.keys() & geo.keys()
    geographic=np.array([(geo[k]-origin)*[90000,111000] for k in common],float)
    geo_h,_=cv2.findHomography(geographic,np.array([k for k in common],float),0)
    boxes,gps=read_csv(box_path),read_csv(gps_path)
    bi=[i for i in range(1,len(boxes[0]),4) if boxes[0][i] in ('0','1') and 1<=int(boxes[1][i])<=11]
    gi=[i for i in range(1,len(gps[0]),2) if gps[0][i] in ('0','1')]
    b=np.full((30,len(bi),2),np.nan);g=np.full((300,len(gi),2),np.nan)
    for t in range(30):
        for n,i in enumerate(bi):
            try:
                x,y,w,h=map(float,boxes[4+t*25][i:i+4]);b[t,n]=project(image_h,[x+w/2,y+h])
            except (ValueError,IndexError):pass
    for t in range(300):
        for n,i in enumerate(gi):
            try:
                lat,lon=map(float,gps[4+t][i:i+2]);g[t,n]=project(geo_h,(np.array([lon,lat])-origin)*[90000,111000])
            except (ValueError,IndexError):pass
    best=None
    for lag in range(-20,21,5):
        costs=np.full((len(bi),len(gi)),1000.)
        for i in range(len(bi)):
            for j in range(len(gi)):
                errors=[np.linalg.norm(b[t,i]-g[t*10+lag,j]) for t in range(3,15) if np.isfinite(b[t,i]).all() and np.isfinite(g[t*10+lag,j]).all()]
                if len(errors)>=6:costs[i,j]=np.median(errors)
        cost,mapping,_=lap.lapjv(costs,extend_cost=True)
        if best is None or cost<best[0]:best=(cost,lag,mapping)
    _,lag,mapping=best;errors=[];velocities=[];tracks=0
    for i,j in enumerate(mapping):
        if j<0:continue
        track=[]
        for t in range(15,28):
            gidx=t*10+lag
            if not 0<=gidx<300 or not np.isfinite(b[t,i]).all() or not np.isfinite(g[gidx,j]).all():continue
            track.append(float(np.linalg.norm(b[t,i]-g[gidx,j])))
            if t>15 and gidx-10>=0 and np.isfinite(b[t-1,i]).all() and np.isfinite(g[gidx-10,j]).all():
                vb=b[t,i]-b[t-1,i];vg=g[gidx,j]-g[gidx-10,j];den=np.linalg.norm(vb)*np.linalg.norm(vg)
                if den>.04:velocities.append(float(np.dot(vb,vg)/den))
        if track:tracks+=1;errors.extend(track)
    return {'best_training_offset_100ms':lag,'heldout_observations':len(errors),'heldout_tracks':tracks,
            'heldout_median_m':float(np.median(errors)) if errors else None,'heldout_p90_m':float(np.percentile(errors,90)) if errors else None,
            'motion_pairs':len(velocities),'motion_cosine_median':float(np.median(velocities)) if velocities else None,
            'warning':'Optimized mapping uses same tracked players in the training half; GNSS/video timestamps and IDs not independently verified. Not actual calibration accuracy.'}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('boxes','gnss','image_points','geographic_points'):p.add_argument(name)
    a=p.parse_args();print(json.dumps(eval_alignment(a.boxes,a.gnss,a.image_points,a.geographic_points),indent=2))
