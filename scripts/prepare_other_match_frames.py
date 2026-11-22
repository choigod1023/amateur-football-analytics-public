"""Prepare additional labeled AI Hub training frames from an explicit manifest.

The SoccerTrack holdout is never read. Artifacts remain local and must retain
the original data access restrictions. Frame/label association is as supplied.
"""
import argparse
import math
import json
import shutil
from pathlib import Path
import cv2


def prepare(root, manifest, prior, output, per_match=20, stride=150):
    if output.exists():
        raise ValueError('output already exists; do not overwrite')
    data=json.loads(manifest.read_text(encoding='utf-8-sig'))
    entries=data['train']
    ids=[str(item['match_id']) for item in entries]
    if len(set(ids))!=len(ids) or set(ids)!={'113','131','103','151','10','106','1'}:
        raise ValueError('unexpected training match manifest')
    for split in ('train','val'):
        for kind in ('images','labels'):
            (output/kind/split).mkdir(parents=True,exist_ok=True)
    # Independent development match and two additional training matches from
    # the earlier audited split. Never use the current SoccerTrack recording.
    copied={}
    for split, prefix in [('train',('game310_', 'game781_')),('val',('game318_',))]:
        images=sorted((prior/'images'/split).glob('*.jpg'))
        images=[p for p in images if p.name.startswith(prefix)]
        if not images: raise ValueError('prior split is missing required images')
        for image in images:
            label=prior/'labels'/split/(image.stem+'.txt')
            if not label.is_file(): raise ValueError('missing prior label')
            shutil.copy2(image,output/'images'/split/image.name)
            shutil.copy2(label,output/'labels'/split/label.name)
        copied[split]=len(images)
    counts={}
    for item in entries:
        mid=str(item['match_id'])
        video=(root/item['video']).resolve(); ann=(root/item['labels']).resolve()
        if not video.is_file() or not ann.is_file(): raise ValueError('missing source data')
        labels=json.loads(ann.read_text(encoding='utf-8-sig'))
        indexed={int(x['frame']):x['data'] for x in labels['tag']}
        cap=cv2.VideoCapture(str(video))
        if not cap.isOpened(): raise ValueError('cannot open training video')
        done=0
        try:
            for number in range(0, per_match*stride, stride):
                if number not in indexed: continue
                cap.set(cv2.CAP_PROP_POS_FRAMES,number); ok,image=cap.read()
                if not ok: continue
                height,width=image.shape[:2]; lines=[]
                for obj in indexed[number]:
                    box=obj.get('tag',[])
                    if len(box)!=4: continue
                    try: x,y,w,h=map(float,box)
                    except (TypeError,ValueError): continue
                    if not all(map(math.isfinite, (x, y, w, h))) or w<=0 or h<=0 or x<0 or y<0 or x+w>width or y+h>height: continue
                    lines.append(f'0 {(x+w/2)/width:.6f} {(y+h/2)/height:.6f} {w/width:.6f} {h/height:.6f}')
                if not lines: continue
                name=f'game{mid}_{number}'
                if not cv2.imwrite(str(output/'images/train'/f'{name}.jpg'),image,[cv2.IMWRITE_JPEG_QUALITY,90]):
                    raise ValueError('could not save frame')
                (output/'labels/train'/f'{name}.txt').write_text('\n'.join(lines)+'\n',encoding='utf-8')
                done+=1
        finally: cap.release()
        counts[mid]=done
    if any(v==0 for v in counts.values()): raise ValueError('one or more matches had no usable frames')
    (output/'dataset.yaml').write_text(f"path: '{output.resolve().as_posix()}'\ntrain: images/train\nval: images/val\nnames:\n  0: person\n",encoding='utf-8')
    return {'additional_training':counts,'prior_training_and_validation':copied,'note':'Different matches; current SoccerTrack excluded. No guarantee of label completeness.'}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('root','manifest','prior','output'): p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--per-match',type=int,default=20)
    args=p.parse_args()
    if not 1<=args.per_match<=100: p.error('per-match must be 1..100')
    print(json.dumps(prepare(args.root.resolve(),args.manifest,args.prior,args.output,args.per_match),ensure_ascii=False,indent=2))
