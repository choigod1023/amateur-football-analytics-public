"""Research-only, single-source-group transfer test for partially visible pitch corners.

No model is automatically accepted; compare predictions to held-out labels.
"""
import io, json, pathlib, random, re, runpy, sys, zipfile, uuid
import numpy as np
import cv2
import torch
from torch import nn
from torchvision.models import resnet18

ROOT=pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from scripts.calibrate_penalty_lines import _intersection
from scripts.partial_field_loss import masked_corner_loss

random.seed(17);np.random.seed(17);torch.manual_seed(17)
out=ROOT/'work/partial-field-runs'/uuid.uuid4().hex;out.mkdir(parents=True, exist_ok=False)

def target(d):
    lines={a["line_type"]:a["coordinates"] for a in d.get("lines",[]) if "line_type" in a and "coordinates" in a}
    options=[]
    for side in (1,2):
        names=[f"end line #{side}",f"penalty area #{side}-1",f"penalty area #{side}-2",f"penalty area #{side}-3"]
        pairs=[(0,2),(1,2),(1,3),(0,3)]; points=np.zeros((4,2),np.float32); mask=np.zeros(4,np.float32)
        for i,(x,y) in enumerate(pairs):
            if names[x] not in lines or names[y] not in lines: continue
            try: points[i]=_intersection(lines[names[x]],lines[names[y]],[1920,1080]); mask[i]=1
            except (ValueError,TypeError,KeyError):continue
        if mask.sum()>=2:options.append((int(mask.sum()),side,points,mask))
    if not options:return None
    _,side,points,mask=max(options,key=lambda q:q[0]);return side,points,mask

def image(data):
    b=cv2.imdecode(np.frombuffer(data,dtype=np.uint8),cv2.IMREAD_COLOR)
    if b is None:return None
    b=cv2.resize(b,(320,192));return (np.transpose(cv2.cvtColor(b,cv2.COLOR_BGR2RGB),(2,0,1)).astype(np.float32)/255-np.array([.485,.456,.406],np.float32)[:,None,None])/np.array([.229,.224,.225],np.float32)[:,None,None]

def labels_from(zip_path,files):
    results=[]
    with zipfile.ZipFile(zip_path) as z:
        for name in z.namelist():
            match=re.search(r'soccer_(\d+)\.json$',name)
            if not match or int(match[1]) not in files:continue
            try:d=json.loads(z.read(name)); tg=target(d)
            except (ValueError,KeyError,TypeError):continue
            if tg:results.append((int(match[1]),tg,d.get('file_name','')))
    return results

trainpaths={int(re.search(r'soccer_(\d+)\.jpg$',p.name)[1]):p for p in (ROOT/'work/aihub-training-prefix/field-images').glob('*.jpg') if re.search(r'soccer_(\d+)\.jpg$',p.name) and int(re.search(r'soccer_(\d+)\.jpg$',p.name)[1])<=9000}
train=labels_from(ROOT/'work/aihub-training-prefix/training-labels.zip',trainpaths)
train=[(i,t,f) for i,t,f in train if f.startswith('q6c_Hxjgn4B_')]
if len(train)<80:raise SystemExit(f'not enough independent-source training images: {len(train)}')
random.shuffle(train);train=train[:1200]
# The entire AI Hub validation still-image set is a different source from q6c,
# but almost all its samples are from a single video and are not independent.
vlabels=ROOT/'work/aihub-official/validation-labels.zip';
with zipfile.ZipFile(vlabels) as z:
    validids={int(re.search(r'soccer_(\d+)\.json$',n)[1]) for n in z.namelist() if re.search(r'soccer_(\d+)\.json$',n)}
valid=labels_from(vlabels,validids);valid=[(i,t,f) for i,t,f in valid if f.startswith('Vss97zvkNj_') and t[2].sum()==4]
random.shuffle(valid);valid=valid[:200]
parts=runpy.run_path(str(ROOT/'work/aihub-official/list_validation_video.py'))
X=[];Y=[];S=[];M=[]
for i,(side,points,mask),_ in train:
    im=image(trainpaths[i].read_bytes())
    if im is None:continue
    X.append(im);Y.append((points/np.array([1920,1080])).reshape(-1));S.append(side-1);M.append(np.repeat(mask,2))
V=[];W=[];T=[]
with parts['Parts']() as source,zipfile.ZipFile(source) as z:
    names={pathlib.PurePosixPath(n).stem:n for n in z.namelist() if n.lower().endswith('.jpg')}
    for i,(side,points,mask),_ in valid:
        n=names.get(f'soccer_{i}')
        if not n:continue
        im=image(z.read(n))
        if im is None:continue
        V.append(im);W.append((points/np.array([1920,1080])).reshape(-1));T.append(side-1)
print('source_group_train',len(X),'other_source_development',len(V),flush=True)
if len(V)<20:raise SystemExit('insufficient validation images')
device='cuda' if torch.cuda.is_available() else 'cpu'
model=resnet18(weights=None);model.load_state_dict(torch.load(ROOT/'work/role-transfer/torch-cache/checkpoints/resnet18-f37072fd.pth',map_location='cpu',weights_only=True));model.fc=nn.Linear(model.fc.in_features,10);model=model.to(device)
optim=torch.optim.AdamW(model.parameters(),lr=.0001)
dataset=torch.utils.data.TensorDataset(torch.tensor(np.array(X)),torch.tensor(np.array(Y),dtype=torch.float32),torch.tensor(S),torch.tensor(np.array(M),dtype=torch.float32))
loader=torch.utils.data.DataLoader(dataset,batch_size=8,shuffle=True)
for epoch in range(40):
    model.train();losses=[]
    for x,y,side,mask in loader:
        x=x.to(device);y=y.to(device);side=side.to(device)
        mask=mask.to(device);output=model(x);loss=masked_corner_loss(torch.sigmoid(output[:,:8]),y,mask)+.1*nn.functional.cross_entropy(output[:,8:],side)
        optim.zero_grad();loss.backward();optim.step();losses.append(float(loss.detach()))
    if epoch%5==4:print('epoch',epoch+1,'loss',round(sum(losses)/len(losses),5),flush=True)
model.eval();errors=[];correct=[]
with torch.no_grad():
    for i in range(0,len(V),8):
        o=model(torch.tensor(np.array(V[i:i+8])).to(device)).cpu()
        p=torch.sigmoid(o[:,:8]).numpy().reshape(-1,4,2)*[1920,1080]
        y=np.array(W[i:i+8]).reshape(-1,4,2)*[1920,1080]
        errors.extend(np.linalg.norm(p-y,axis=2).mean(axis=1).tolist());correct.extend((o[:,8:].argmax(1).numpy()==np.array(T[i:i+8])).tolist())
baseline=(np.sum(np.array(Y)*np.array(M),axis=0)/np.maximum(np.sum(np.array(M),axis=0),1)).reshape(4,2)*[1920,1080]
baseline_errors=[float(np.linalg.norm(baseline-np.array(y).reshape(4,2)*[1920,1080],axis=1).mean()) for y in W]
result={'train_source':'AI Hub train q6c','development_source':'AI Hub validation Vss','partial_landmarks':True,'train_images':len(X),'development_images':len(V),'train_side_counts':[S.count(0),S.count(1)],'development_side_counts':[T.count(0),T.count(1)],'median_mean_corner_error_px':float(np.median(errors)),'p90_mean_corner_error_px':float(np.percentile(errors,90)),'mean_corner_baseline_median_px':float(np.median(baseline_errors)),'side_accuracy':float(np.mean(correct)),'model_accepted':False,'limitations':'Single source per split; development frames from same match are correlated; development set has been used for model selection. Corner error is not independent field-coordinate accuracy. No runtime deployment.'}
(out/'results.json').write_text(json.dumps(result,indent=2),encoding='utf8');torch.save(model.state_dict(),out/'experimental.pt');print(json.dumps(result),flush=True)
