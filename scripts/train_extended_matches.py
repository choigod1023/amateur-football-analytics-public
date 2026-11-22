"""Small local person-detector training on nine non-target soccer matches."""
import argparse
import hashlib
import json
import re
from pathlib import Path

from ultralytics.utils import YAML


def audit(dataset):
    config=YAML.load(dataset/'dataset.yaml')
    if Path(config.get('path','')).resolve()!=dataset.resolve() or config.get('train')!='images/train' or config.get('val')!='images/val':
        raise ValueError('unexpected dataset path or split')
    result={}
    for split in ('train','val'):
        images=list((dataset/'images'/split).glob('*.jpg'))
        matches=set()
        for image in images:
            found=re.fullmatch(r'game(\d+)_(?:aihub\1_)?\d+\.jpg',image.name)
            if not found or not (dataset/'labels'/split/(image.stem+'.txt')).is_file():
                raise ValueError('invalid source name or missing label')
            matches.add(found.group(1))
        expected={'113','131','103','151','10','106','1','310','781'} if split=='train' else {'318'}
        if matches!=expected or len(images)!=(156 if split=='train' else 6):
            raise ValueError('unexpected training or validation split')
        result[split]={'frames':len(images),'matches':sorted(matches)}
    return result


if __name__=='__main__':
    import torch
    from ultralytics import YOLO
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('dataset','pretrained','project'): p.add_argument('--'+name,type=Path,required=True)
    args=p.parse_args()
    details=audit(args.dataset.resolve())
    details['pretrained_sha256']=hashlib.sha256(args.pretrained.read_bytes()).hexdigest()
    details['note']='Filename audit does not prove video contents or original pretrained model history.'
    print(json.dumps(details),flush=True)
    torch.set_num_threads(4)
    YOLO(str(args.pretrained)).train(data=str((args.dataset/'dataset.yaml').resolve()),epochs=3,imgsz=640,batch=4,workers=0,device='cpu',pretrained=True,patience=0,plots=False,save=True,project=str(args.project.resolve()),name='nine_games_156',exist_ok=False,verbose=False)
