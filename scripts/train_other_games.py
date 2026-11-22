"""Reproduce the small local 9-match training run; target match is excluded."""
import argparse
import re
from pathlib import Path
from ultralytics.utils import YAML

TRAIN = {'310','781','113','131','103','151','10','106','1'}


def audit(dataset):
    config=YAML.load(dataset/'dataset.yaml')
    if not isinstance(config, dict) or Path(config.get('path','')).resolve() != dataset.resolve() or config.get('train') != 'images/train' or config.get('val') != 'images/val':
        raise ValueError('Dataset YAML points outside the audited split')
    train = list((dataset/'images/train').glob('*.jpg'))
    valid = list((dataset/'images/val').glob('*.jpg'))
    def games(items):
        found=set()
        for path in items:
            match=re.fullmatch(r'game(\d+)_[A-Za-z0-9_]+\.jpg', path.name)
            if not match: raise ValueError('Unexpected source filename')
            found.add(match.group(1))
        return found
    if len(train) != 51 or len(valid) != 6 or games(train) != TRAIN or games(valid) != {'318'}:
        raise ValueError('Unexpected train or validation match/frame manifest')
    for split, images in (('train',train),('val',valid)):
        if any(not (dataset/'labels'/split/(p.stem+'.txt')).is_file() for p in images):
            raise ValueError('Missing label file')
    return {'train_frames':len(train), 'train_matches':len(TRAIN), 'validation_frames':len(valid)}


if __name__ == '__main__':
    import torch
    from ultralytics import YOLO
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dataset',type=Path,required=True,help='Local prepared independent-dataset directory')
    p.add_argument('--pretrained',type=Path,required=True,help='Original general pretrained YOLO11n weights, not target-video weights')
    p.add_argument('--project',type=Path,required=True,help='Separate local experiment output directory')
    a=p.parse_args()
    print(audit(a.dataset))
    torch.set_num_threads(4)
    YOLO(str(a.pretrained)).train(data=str(a.dataset/'dataset.yaml'),epochs=3,imgsz=640,batch=4,workers=0,device='cpu',pretrained=True,patience=0,plots=False,save=True,project=str(a.project),name='nine_games',exist_ok=False,verbose=False)
