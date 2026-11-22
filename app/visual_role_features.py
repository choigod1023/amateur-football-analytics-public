"""Opt-in spatial body/context features; no pretrained weights or live integration."""
import cv2
import numpy as np
from app.team_role_features import box_features

BODY_SIZE = 288 + 96
CONTEXT_SIZE = 192

def visual_features(image, bbox):
    """Return baseline24, spatial body384, separate masked context192.

    Context is a 3x box crop with the target removed, never mixed into body HSV.
    Resizing preserves arrangement but cannot recover missing optical detail.
    """
    h, w = image.shape[:2]
    box = np.asarray(bbox, dtype=float)
    if box.shape != (4,) or not np.isfinite(box).all():
        raise ValueError('Expected finite normalized xyxy')
    x1,y1,x2,y2 = np.clip(box,0,1)
    if x2 <= x1 or y2 <= y1:
        raise ValueError('Empty or inverted box')
    l,t = int(x1*w),int(y1*h)
    r,b = min(w,max(l+1,int(x2*w))),min(h,max(t+1,int(y2*h)))
    patch = image[t:b,l:r]
    body = cv2.resize(patch,(32,64),interpolation=cv2.INTER_LINEAR)
    # Unsigned cell gradient histograms (HOG-like), implemented with NumPy.
    gray = body.astype(np.float32).mean(2)
    gy,gx = np.gradient(gray)
    magnitude = np.hypot(gx,gy)
    bins = ((np.arctan2(gy,gx) % np.pi) * (9 / np.pi)).astype(int) % 9
    cells=[]
    for yy in range(0,64,8):
        for xx in range(0,32,8):
            hist=np.bincount(bins[yy:yy+8,xx:xx+8].ravel(), weights=magnitude[yy:yy+8,xx:xx+8].ravel(), minlength=9)
            cells.append(hist/(np.linalg.norm(hist)+1e-6))
    hog=np.concatenate(cells)
    colours = cv2.resize(patch,(4,8),interpolation=cv2.INTER_AREA).ravel()/255.
    bw,bh = r-l,b-t
    cl,ct,cr,cb = max(0,l-bw),max(0,t-bh),min(w,r+bw),min(h,b+bh)
    context = image[ct:cb,cl:cr].copy()
    # Zero target pixels so context is a genuinely distinct branch.
    context[t-ct:b-ct,l-cl:r-cl] = 0
    context = cv2.resize(context,(8,8),interpolation=cv2.INTER_AREA).ravel()/255.
    return (box_features(image,(x1,y1,x2,y2)),
            np.concatenate((hog,colours)).astype(np.float32),context.astype(np.float32))
