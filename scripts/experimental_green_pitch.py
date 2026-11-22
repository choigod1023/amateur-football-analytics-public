"""Research-only field candidate from green mask and straight lines.

Never approves or installs a calibration. Pitch labels are used only to score
the candidate, not to generate it. Thresholds are not externally validated.
"""
import argparse, json, sys
from pathlib import Path
import cv2
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.experimental_panorama_groundtruth import load, perspective

def propose(frame, *, field_support=False):
    height,width=frame.shape[:2];scale=2600/width
    img=cv2.resize(frame,(2600,round(height*scale)));h,w=img.shape[:2]
    hsv=cv2.cvtColor(img,cv2.COLOR_BGR2HSV)
    green=cv2.morphologyEx(cv2.inRange(hsv,(25,25,20),(95,255,255)),cv2.MORPH_CLOSE,np.ones((15,15),np.uint8))
    occupancy=np.mean(green[:,int(w*.38):int(w*.70)]>0,axis=1)
    rows=np.flatnonzero((occupancy>.90)&(np.arange(h)>h*.2)&(np.arange(h)<h*.75))
    if not len(rows):return None
    far=float(rows[0]);gray=cv2.cvtColor(img,cv2.COLOR_BGR2GRAY)
    contrast=cv2.morphologyEx(gray,cv2.MORPH_TOPHAT,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(15,15)))
    white=cv2.bitwise_and((contrast>10).astype(np.uint8)*255,cv2.dilate(green,np.ones((7,7),np.uint8)))
    raw=cv2.HoughLinesP(white,1,np.pi/180,30,minLineLength=100,maxLineGap=18)
    if raw is None:return None
    lines=raw.reshape(-1,4).astype(float)
    horizontal=[l for l in lines if abs(l[3]-l[1])<4 and abs(l[2]-l[0])>100 and min(l[1],l[3])>h*.65]
    if not horizontal:return None
    longest=max(horizontal,key=lambda l:abs(l[2]-l[0]));near=float((longest[1]+longest[3])/2)
    near_lines=[l for l in horizontal if abs((l[1]+l[3])/2-near)<5]
    left=min(min(l[0],l[2]) for l in near_lines);right=max(max(l[0],l[2]) for l in near_lines)
    if right-left<w*.6 or near-far<h*.15:return None
    sides=[]
    for direction,edge in [(-1,left),(1,right)]:
        candidates=[]
        for l in lines:
            x1,y1,x2,y2=l;dx=x2-x1
            if abs(dx)<1:continue
            slope=(y2-y1)/dx
            if not .08<direction*slope<.25:continue
            if field_support:
                # Require the line to lie below the automatically inferred
                # upper grass edge, with continuous green beside one side.
                # The field boundary itself need not be green on both sides.
                if (y1+y2)/2 < far+10:continue
                length=max(float(np.hypot(dx,y2-y1)),1.)
                normal=np.array([-(y2-y1),dx])/length
                samples=np.linspace(0.1,.9,30)[:,None]
                segment=np.array([x1,y1])+samples*np.array([dx,y2-y1])
                fractions=[]
                for sign in (-1,1):
                    xy=np.rint(segment+sign*normal*6).astype(int)
                    inside=(xy[:,0]>=0)&(xy[:,0]<w)&(xy[:,1]>=0)&(xy[:,1]<h)
                    fractions.append(float(np.mean(green[xy[inside,1],xy[inside,0]]>0)) if inside.sum()>=20 else 0.)
                if max(fractions)<.75:continue
            xn=x1+(near-y1)/slope;xf=x1+(far-y1)/slope
            if direction<0 and not (-w*.05<xn<w*.25 and w*.25<xf<w*.55):continue
            if direction>0 and not (w*.75<xn<w*1.05 and w*.45<xf<w*.75):continue
            length=float(np.hypot(dx,y2-y1));score=abs(xn-edge)+20000/length
            candidates.append((score,xn,xf))
        if not candidates:return None
        _,xn,xf=min(candidates);sides.append((xn,xf))
    left,right=sides
    return np.array([[left[1],far],[right[1],far],[right[0],near],[left[0],near]],float)/scale

def score(candidate,pairs):
    target=np.array([[0,0],[105,0],[105,68],[0,68]],float)
    points={tuple(b):a for a,b in pairs};corners=np.array([points[tuple(v)] for v in target])
    errors=np.linalg.norm(candidate-corners,axis=1)
    if not cv2.isContourConvex(candidate.astype(np.float32)):return {'candidate_error_px':errors.tolist(),'valid_geometry':False}
    meters=[]
    for image,field in pairs:
        if tuple(field) in set(map(tuple,target)):continue
        guess=perspective(image,candidate,target)
        if guess is not None and np.isfinite(guess).all():meters.append(float(np.linalg.norm(guess-field)))
    return {'candidate_error_px':errors.tolist(),'valid_geometry':True,'holdout_marks':len(meters),
            'holdout_median_m':float(np.median(meters)), 'holdout_p90_m':float(np.percentile(meters,90))}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('landmarks');p.add_argument('videos',nargs='+');a=p.parse_args()
    pairs=load(a.landmarks);out=[]
    for filename in a.videos:
        cap=cv2.VideoCapture(filename)
        for sec in (2,10,20):
            cap.set(cv2.CAP_PROP_POS_MSEC,sec*1000);ok,frame=cap.read()
            if not ok:out.append({'second':sec,'error':'frame_unavailable'});continue
            candidate=propose(frame); refined=propose(frame,field_support=True)
            out.append({'second':sec,'result':None if candidate is None else score(candidate,pairs),
                        'field_support_result':None if refined is None else score(refined,pairs)})
        cap.release()
    print(json.dumps({'samples':out,'warning':'Same fixed camera, heuristic thresholds, unverified 105x68, landmarks are only for scoring; not independently surveyed.'},indent=2))
