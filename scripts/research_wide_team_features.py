"""Compare experimental colour group features on one local wide-camera match."""
import argparse, collections, json, sys
from pathlib import Path
import cv2, numpy as np, torch
sys.path.insert(0,str(Path(__file__).resolve().parent))
from evaluate_wide_team_gt import scan

def feature(frame, box, kind):
    x,y,x2,y2=map(int,box); h=y2-y; w=x2-x
    if w<8 or h<20:return None
    crop=frame[y+int(h*.15):y+int(h*.55),x+int(w*.15):x+int(w*.85)]
    if crop.size<30:return None
    hsv=cv2.cvtColor(crop,cv2.COLOR_BGR2HSV).reshape(-1,3).astype(float)
    hsv=hsv[(hsv[:,2]>40)&~((hsv[:,0]>35)&(hsv[:,0]<85)&(hsv[:,1]>70))]
    if len(hsv)<12:return None
    if kind=='hist':
        colour,grey=hsv[hsv[:,1]>=65],hsv[hsv[:,1]<65];out=np.zeros(16)
        if len(colour):out[:12]=np.histogram(colour[:,0],12,(0,180))[0]
        if len(grey):out[12:]=np.histogram(grey[:,2],4,(0,256))[0]
        return out/max(out.sum(),1)
    angle=hsv[:,0]*np.pi/90.;sat=hsv[:,1]/255.;val=hsv[:,2]/255.
    if kind=='circular': return np.array([np.mean(np.cos(angle)*sat),np.mean(np.sin(angle)*sat),np.mean(val)*.35])
    if kind=='median': return np.array([np.median(np.cos(angle)*sat),np.median(np.sin(angle)*sat),np.median(val)*.35])
    raise ValueError(kind)

def collect(folder, name, frames):
    out=[]
    for frame,tracks,truth in scan(folder,name,frames):
        out.append([(tid,truth[tid],{kind:feature(frame,box,kind) for kind in ('hist','circular','median')}) for box,tid in tracks])
    return out

def evaluate(train,test,kind):
    byid=collections.defaultdict(list)
    for frame in train:
        for tid,truth,feats in frame:
            if feats[kind] is not None:byid[tid].append(feats[kind])
    x=np.asarray([np.median(np.stack(v),axis=0) for v in byid.values()],dtype=np.float32)
    cv2.setRNGSeed(15)
    _,_,centres=cv2.kmeans(x,2,None,(cv2.TERM_CRITERIA_EPS+cv2.TERM_CRITERIA_MAX_ITER,100,.00001),20,cv2.KMEANS_PP_CENTERS)
    def classify(f):
        if f is None:return None
        d=np.linalg.norm(centres-f,axis=1); return int(d.argmin())
    votes=collections.Counter((classify(feats[kind]),truth) for frame in train for _,truth,feats in frame if feats[kind] is not None)
    mapping=0 if votes[0,0]+votes[1,1] >= votes[0,1]+votes[1,0] else 1
    counts=collections.Counter()
    for frame in test:
        for _,truth,feats in frame:
            group=classify(feats[kind]);counts['unknown' if group is None else ('correct' if group^mapping==truth else 'wrong')]+=1
    return {'feature':kind,'counts':dict(counts),'mapping':'fit with labelled bootstrap','limitation':'No distance/confidence guard; true boxes and identities; same game; roles not evaluated'}

def supervised(train,test):
    train_rows=[(features['hist'],truth) for frame in train for _,truth,features in frame if features['hist'] is not None]
    test_rows=[(features['hist'],truth) for frame in test for _,truth,features in frame]
    x=torch.tensor(np.stack([v for v,t in train_rows]),dtype=torch.float32);y=torch.tensor([t for v,t in train_rows],dtype=torch.float32)
    torch.manual_seed(123);torch.set_num_threads(2);model=torch.nn.Linear(16,1);opt=torch.optim.Adam(model.parameters(),lr=.05,weight_decay=.005)
    for _ in range(300):
        opt.zero_grad();loss=torch.nn.functional.binary_cross_entropy_with_logits(model(x).flatten(),y);loss.backward();opt.step()
    data={};
    for gate in (0.5,0.7,0.9):
        count=collections.Counter()
        for feat,truth in test_rows:
            if feat is None: count['unknown']+=1;continue
            with torch.no_grad():prob=torch.sigmoid(model(torch.tensor(feat,dtype=torch.float32))).item()
            if max(prob,1-prob)<gate:count['unknown']+=1
            else:count['correct' if int(prob>=.5)==truth else 'wrong']+=1
        data[str(gate)]=dict(count)
    return {'feature':'supervised_histogram','counts_by_gate':data,'limitation':'Uses GT team labels for the first 10 frames; true boxes, same game, tiny crops; not automatic or independent.'}

def main():
    p=argparse.ArgumentParser();p.add_argument('folder',type=Path);a=p.parse_args()
    train=collect(a.folder,'0000_0030',range(1,11));test=collect(a.folder,'0120_0150',range(1,727,25))
    print(json.dumps([evaluate(train,test,k) for k in ('hist','circular','median')]+[supervised(train,test)],indent=2))
if __name__=='__main__':main()
