"""Local high-resolution person search after a missed observation.

Uses only the last observed box to choose the search area. Returned detections
are candidates, not confirmed identity, team, or pitch coordinates.
"""
import math


def search_region(box, shape):
    if len(box)<4 or not all(math.isfinite(float(v)) for v in box[:4]):
        raise ValueError('Finite box required')
    x1,y1,x2,y2=map(float,box[:4]);h,w=shape[:2]
    if x2<=x1 or y2<=y1 or h<=0 or w<=0:
        raise ValueError('Positive box and image dimensions required')
    size=min(384,max(160,6*(y2-y1)))
    cx,cy=(x1+x2)/2,(y1+y2)/2
    left=max(0,min(int(cx-size/2),max(0,w-int(size))))
    top=max(0,min(int(cy-size/2),max(0,h-int(size))))
    return left,top,min(w,left+int(size)),min(h,top+int(size))


def redetect(model, frame, last_box, device=0, confidence=.1):
    x1,y1,x2,y2=search_region(last_box,frame.shape)
    crop=frame[y1:y2,x1:x2]
    result=model.predict(crop,device=device,imgsz=768,conf=confidence,classes=[0],max_det=30,verbose=False)[0]
    boxes=[]
    if result.boxes is not None:
        for box,score in zip(result.boxes.xyxy.cpu().numpy(), result.boxes.conf.cpu().numpy()):
            boxes.append([float(box[0]+x1),float(box[1]+y1),float(box[2]+x1),float(box[3]+y1),float(score)])
    return {'region':[x1,y1,x2,y2],'candidates':boxes,'identity_verified':False}
