"""Measure role model outputs on local SoccerTrack team-labelled player boxes.

SoccerTrack CSV team labels do not prove field-player versus goalkeeper role;
do not report per-role accuracy or treat these boxes as independent people.
"""
import argparse, collections, importlib.util, json, sys
from pathlib import Path
import cv2, numpy as np, torch
sys.path.insert(0,str(Path(__file__).resolve().parent))
from evaluate_wide_team_gt import scan

def main():
    p=argparse.ArgumentParser();p.add_argument('folder',type=Path);p.add_argument('source',type=Path);p.add_argument('weights',type=Path,nargs='+');a=p.parse_args()
    spec=importlib.util.spec_from_file_location('role_research',a.source);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    torch.set_num_threads(2); nets=[]
    for path in a.weights:
        net=module.Net();net.load_state_dict(torch.load(path,map_location='cpu',weights_only=True));net.eval();nets.append(net)
    count=[collections.Counter() for _ in nets]; bytrack=[collections.defaultdict(collections.Counter) for _ in nets]
    for frame,tracks,truth in scan(a.folder,'0120_0150',range(1,727,25)):
        crop=[];ids=[]
        for box,tid in tracks:
            x1,y1,x2,y2=map(int,box)
            if x2-x1<8 or y2-y1<16:continue
            image=cv2.resize(frame[y1:y2,x1:x2],(24,48));crop.append(image.transpose(2,0,1));ids.append(tid)
        if not crop:continue
        tensor=torch.tensor(np.asarray(crop),dtype=torch.float32)/255
        for idx,net in enumerate(nets):
            with torch.no_grad():scores=net(tensor).softmax(1).numpy()
            for tid,score in zip(ids,scores):
                role=int(score.argmax()); count[idx][f'argmax_{role}']+=1;bytrack[idx][tid][str(role)]+=1
                if role==0 and float(score[0])>=.99:count[idx]['field_p99']+=1
    print(json.dumps({'frames':30,'classes':['field_player','referee','goalkeeper'],'models':[{'name':path.name,'counts':dict(count[i]),'by_track':dict(bytrack[i])} for i,path in enumerate(a.weights)], 'limitation':'Same 22 team-labelled players across frames, unknown goalkeeper role and partial annotation; use only as transfer diagnostic; ground-truth boxes, not actual tracking.'},indent=2))
if __name__=='__main__':main()
