"""Review labelled AI Hub training frames only; never read evaluation footage."""
import argparse
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import re
import sys
import threading

import cv2
import uvicorn
from fastapi import Request
from fastapi.staticfiles import StaticFiles

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import main
from app.training_labels import TrainingLabels

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT.parent.parent / 'work'
DATASET = WORK / 'detector-extended-20261111' / 'dataset'
IMAGE_DIR = DATASET / 'images' / 'train'
LABEL_DIR = DATASET / 'labels' / 'train'
ALLOWED_GAMES = {'113','131','103','151','10','106','1','310','781'}


def load_sample(image_path, label_path):
    image_path, label_path = image_path.resolve(), label_path.resolve()
    if image_path.parent != IMAGE_DIR.resolve() or label_path.parent != LABEL_DIR.resolve():
        raise ValueError('Only the designated training split is allowed')
    match = re.fullmatch(r'game(\d+)_(?:aihub\1_)?\d+', image_path.stem)
    if not match or match.group(1) not in ALLOWED_GAMES or label_path.stem != image_path.stem:
        raise ValueError('Unexpected training source')
    image = cv2.imread(str(image_path))
    if image is None:
        raise ValueError('Training image cannot be decoded')
    height,width=image.shape[:2]; boxes=[]
    for line in label_path.read_text(encoding='utf-8').splitlines():
        fields=line.split()
        if len(fields)!=5 or fields[0]!='0':
            raise ValueError('Unexpected training annotation')
        x,y,w,h=map(float,fields[1:])
        if not all(0 <= v <= 1 for v in (x,y,w,h)) or w<=0 or h<=0:
            raise ValueError('Invalid training annotation')
        boxes.append(([max(0,(x-w/2)*width),max(0,(y-h/2)*height),min(width,(x+w/2)*width),min(height,(y+h/2)*height)],str(len(boxes)+1)))
    provenance={'split':'train','dataset':'AI Hub existing person annotations','game_id':match.group(1),
                'frame':image_path.name,'image_sha256':hashlib.sha256(image_path.read_bytes()).hexdigest(),
                'boxes':'existing person annotations; role and team not specified'}
    return image, boxes, provenance


def main_entry():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--port',type=int,default=18963);args=parser.parse_args()
    if not 1024<=args.port<=65535:parser.error('unprivileged port required')
    samples=sorted(p for p in IMAGE_DIR.glob('*.jpg') if (LABEL_DIR/(p.stem+'.txt')).is_file())
    if not samples:parser.error('training samples missing')
    main.training_labels=TrainingLabels(WORK/'human-labels'/'aihub-train')
    state={'index':0}; lock=threading.Lock()
    def publish():
        with lock:
            path=samples[state['index']];frame,boxes,provenance=load_sample(path,LABEL_DIR/(path.stem+'.txt'))
            main.training_labels.publish(frame,boxes,datetime.now(timezone.utc).isoformat(),'aihub_train',provenance=provenance)
    @main.app.post('/api/v1/training-labels/next-sample')
    def next_sample(request:Request):
        main.local_label_request(request)
        with lock:state['index']=(state['index']+1)%len(samples)
        publish();return {'available':True}
    publish()
    def refresh():
        while True:
            threading.Event().wait(2)
            publish()
    threading.Thread(target=refresh,daemon=True).start()
    main.app.mount('/',StaticFiles(directory=ROOT/'web',html=True),name='dashboard')
    uvicorn.run(main.app,host='127.0.0.1',port=args.port,access_log=False)

if __name__=='__main__':main_entry()
