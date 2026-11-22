"""Research-only visible-semantic-line segmentation; absent labels ignored.

Training: AI Hub training images source q6c. Development: AI Hub validation
images source Vss. These are two source videos, not a generalization estimate.
"""
import json,pathlib,random,re,runpy,zipfile
import cv2,numpy as np,torch
from torch import nn

ROOT=pathlib.Path(__file__).resolve().parents[3]; random.seed(17);np.random.seed(17);torch.manual_seed(17)
OUT=ROOT/'work/field-auto-train';OUT.mkdir(exist_ok=True)
CLASSES=[f'end line #{i}' for i in (1,2)]+[f'penalty area #{i}-{j}' for i in (1,2) for j in (1,2,3)]
W,H=320,192
def convert(raw,lines):
 im=cv2.imdecode(np.frombuffer(raw,np.uint8),cv2.IMREAD_COLOR)
 if im is None:return None
 h,w=im.shape[:2];im=cv2.resize(cv2.cvtColor(im,cv2.COLOR_BGR2RGB),(W,H)); masks=np.zeros((len(CLASSES),H,W),np.float32);known=np.zeros(len(CLASSES),np.float32)
 for a in lines:
  if a.get('line_type') not in CLASSES:continue
  pts=np.asarray(a.get('coordinates',[]),dtype=float)
  if pts.shape!=(2,2) or not np.isfinite(pts).all():continue
  i=CLASSES.index(a['line_type']);known[i]=1
  pts=np.rint(pts*np.array([W/w,H/h])).astype(np.int32);cv2.line(masks[i],tuple(pts[0]),tuple(pts[1]),1,3)
 return np.transpose(im,(2,0,1)).astype(np.float32)/255,masks,known
def select(z,ids,source,limit):
 rows=[]
 for n in z.namelist():
  m=re.search(r'soccer_(\d+)\.json$',n)
  if not m or int(m[1]) not in ids:continue
  try:d=json.loads(z.read(n))
  except ValueError:continue
  if str(d.get('file_name','')).startswith(source) and any(a.get('line_type') in CLASSES for a in d.get('lines',[])):rows.append((int(m[1]),d['lines']))
 random.shuffle(rows);return rows[:limit]
trainpaths={int(m[1]):p for p in (ROOT/'work/aihub-training-prefix/field-images').glob('*.jpg') if (m:=re.search(r'soccer_(\d+)\.jpg$',p.name)) and int(m[1])<=9000}
with zipfile.ZipFile(ROOT/'work/aihub-training-prefix/training-labels.zip') as z:train=select(z,trainpaths,'q6c_Hxjgn4B_',500)
with zipfile.ZipFile(ROOT/'work/aihub-official/validation-labels.zip') as z:
 ids={int(m[1]) for n in z.namelist() if (m:=re.search(r'soccer_(\d+)\.json$',n))};valid=select(z,ids,'Vss97zvkNj_',100)
parts=runpy.run_path(str(ROOT/'work/aihub-official/list_validation_video.py'))
X=[];Y=[];K=[];V=[];A=[];B=[]
for i,lines in train:
 row=convert(trainpaths[i].read_bytes(),lines)
 if row is not None:x,y,k=row;X.append(x);Y.append(y);K.append(k)
with parts['Parts']() as source,zipfile.ZipFile(source) as z:
 names={pathlib.PurePosixPath(n).stem:n for n in z.namelist() if n.lower().endswith('.jpg')}
 for i,lines in valid:
  n=names.get(f'soccer_{i}')
  if n:
   row=convert(z.read(n),lines)
   if row is not None:x,y,k=row;V.append(x);A.append(y);B.append(k)
print('train images',len(X),'development images',len(V),flush=True)
if len(X)<100 or len(V)<20:raise SystemExit('insufficient source-separated data')
class Net(nn.Module):
 def __init__(self):
  super().__init__();self.conv=nn.Sequential(nn.Conv2d(3,16,3,2,1),nn.ReLU(),nn.Conv2d(16,32,3,2,1),nn.ReLU(),nn.Conv2d(32,64,3,2,1),nn.ReLU(),nn.Conv2d(64,64,3,1,1),nn.ReLU(),nn.Conv2d(64,len(CLASSES),1))
 def forward(self,x):return nn.functional.interpolate(self.conv(x),size=(H,W),mode='bilinear',align_corners=False)
device='cuda' if torch.cuda.is_available() else 'cpu';net=Net().to(device);optim=torch.optim.AdamW(net.parameters(),lr=.001)
ds=torch.utils.data.TensorDataset(torch.tensor(np.array(X)),torch.tensor(np.array(Y)),torch.tensor(np.array(K)))
dl=torch.utils.data.DataLoader(ds,batch_size=8,shuffle=True)
for epoch in range(10):
 net.train();vals=[]
 for x,y,k in dl:
  x=x.to(device);y=y.to(device);k=k.to(device)[:,:,None,None]
  logits=net(x);loss=nn.functional.binary_cross_entropy_with_logits(logits,y,reduction='none',pos_weight=torch.tensor(20.,device=device));loss=(loss*k).sum()/(k.sum()*H*W).clamp_min(1)
  optim.zero_grad();loss.backward();optim.step();vals.append(float(loss.detach()))
 print('epoch',epoch+1,'loss',round(sum(vals)/len(vals),5),flush=True)
net.eval();tp=fp=fn=0;present=0
with torch.no_grad():
 for i in range(0,len(V),8):
  x=torch.tensor(np.array(V[i:i+8])).to(device);p=(torch.sigmoid(net(x)).cpu().numpy()>=.5);y=np.array(A[i:i+8])>.5;k=np.array(B[i:i+8])[:,:,None,None]>.5
  tp+=int((p&y&k).sum());fp+=int((p&~y&k).sum());fn+=int((~p&y&k).sum());present+=int(k.sum())
result={'train_source':'AI Hub train q6c','development_source':'AI Hub validation Vss','train_images':len(X),'development_images':len(V),'annotated_channel_instances':present,'pixel_precision_on_annotated_channels':tp/(tp+fp) if tp+fp else None,'pixel_recall_on_annotated_channels':tp/(tp+fn) if tp+fn else None,'classes':CLASSES,'unannotated_channels':'ignored; false positives there not measured','accepted_for_calibration':False,'limitations':'single source video per split; frame correlation, raw segmentation not metric calibration, no independent on-video position accuracy.'}
(OUT/'segmentation-results.json').write_text(json.dumps(result,indent=2),encoding='utf8');torch.save(net.state_dict(),OUT/'segmentation-experimental.pt');print(json.dumps(result),flush=True)
