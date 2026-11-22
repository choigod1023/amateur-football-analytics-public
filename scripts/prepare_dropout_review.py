"""Stage selected identity questions and real video crops; never publish or label.

Input: {questions:[{a,b,end,start,before_box,after_box,reason}]}, clip seconds,
pixel xyxy. Existing pending, answered and unclear questions are not repeated.
The publication manifest pins the queue SHA so a publisher can detect conflicts.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess

import cv2


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(part)
    return digest.hexdigest()


def validate(q, width, height, duration):
    q = dict(q)
    q['a'], q['b'] = str(q['a']), str(q['b'])
    q['end'], q['start'] = float(q['end']), float(q['start'])
    if not all(math.isfinite(q[k]) for k in ('end', 'start')) or not 0 <= q['end'] < q['start'] < duration:
        raise ValueError('Identity endpoints must be ordered within the recording')
    if not q['a'] or not q['b'] or q['a'] == q['b']:
        raise ValueError('A question requires two distinct observed track IDs')
    for key in ('before_box', 'after_box'):
        box = list(map(float, q[key]))
        if len(box) != 4 or not all(map(math.isfinite, box)):
            raise ValueError('Expected four finite box coordinates')
        x1,y1,x2,y2 = box
        if not 0 <= x1 < x2 <= width or not 0 <= y1 < y2 <= height:
            raise ValueError('Observed box outside recording')
        q[key] = box
    return q


def iou(a, b):
    if len(a) != 4 or len(b) != 4:
        return 0.
    overlap = max(0., min(a[2],b[2])-max(a[0],b[0])) * max(0.,min(a[3],b[3])-max(a[1],b[1]))
    union = (a[2]-a[0])*(a[3]-a[1])+(b[2]-b[0])*(b[3]-b[1])-overlap
    return overlap/union if union > 0 else 0.


def existing_question(q, rows, source_hash):
    """Reuse answered/unclear/pending rows, including renamed IDs at same boxes."""
    for row in rows:
        if row.get('kind') != 'tracking' or row.get('source_sha256') != source_hash:
            continue
        boundary = row.get('boundary', {})
        if abs(boundary.get('end', -1000)-q['end']) > .201 or abs(boundary.get('start', -1000)-q['start']) > .201:
            continue
        same_ids = list(map(str,row.get('source_pair',[]))) == [q['a'],q['b']]
        same_geometry = all(iou(q[k], boundary.get(k, [])) >= .5 for k in ('before_box','after_box'))
        if same_ids or same_geometry:
            return row['id']
    return None


def zoom_region(q, width, height):
    boxes = [q['before_box'],q['after_box']]
    x1,y1 = min(b[0] for b in boxes),min(b[1] for b in boxes)
    x2,y2 = max(b[2] for b in boxes),max(b[3] for b in boxes)
    pad = max(20.,max(b[3]-b[1] for b in boxes))
    size = min(width,height,max(128,math.ceil(max(x2-x1,y2-y1)+2*pad)))
    size -= size % 2
    left = max(0,min(width-size,int((x1+x2-size)/2)))
    top = max(0,min(height-size,int((y1+y2-size)/2)))
    if not (left <= x1 < x2 <= left+size and top <= y1 < y2 <= top+size):
        raise ValueError('Endpoints too distant for a useful shared enlargement')
    return left,top,size


def prepare(selected, video, store, output, ffmpeg, offset=1950., limit=3):
    video,store,output = map(Path,(video,store,output))
    if not 1 <= limit <= 4 or not math.isfinite(offset) or offset < 0:
        raise ValueError('A small review batch and finite source offset are required')
    queue_path = store/'differences/queue.json'
    queue_bytes = queue_path.read_bytes()
    queue = json.loads(queue_bytes)
    source_hash = sha(video)
    if selected.get('source_sha256',source_hash) != source_hash:
        raise ValueError('Selected recording fingerprint does not match')
    originals = {str(p.resolve()):sha(p) for p in store.rglob('*.json')}
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise ValueError('Cannot decode source recording')
    try:
        width,height = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        duration = cap.get(cv2.CAP_PROP_FRAME_COUNT)/fps if fps > 0 else 0
        if min(width,height,duration) <= 0:
            raise ValueError('Invalid recording metadata')
        questions = [validate(q,width,height,duration) for q in selected['questions']]
        output.mkdir(parents=True,exist_ok=False)
        rows = list(queue['items']); maximum = max((int(r['id'][1:]) for r in rows),default=0)
        created,skipped = [],[]
        for q in questions:
            duplicate = existing_question(q,rows,source_hash)
            if duplicate:
                skipped.append({'a':q['a'],'b':q['b'],'existing_id':duplicate,'reason':'existing_question_preserved'})
                continue
            if len(created) >= limit:
                skipped.append({'a':q['a'],'b':q['b'],'reason':'batch_limit'})
                continue
            maximum += 1; ident = f'd{maximum:04d}'; images=[]
            for suffix,t,box in [('a',q['end'],q['before_box']),('b',q['start'],q['after_box'])]:
                cap.set(cv2.CAP_PROP_POS_MSEC,t*1000)
                ok,frame = cap.read()
                if not ok:
                    raise RuntimeError(f'Could not decode observed endpoint {t}')
                x1,y1,x2,y2=box; pad=max(16,y2-y1)
                left,top=max(0,math.floor(x1-pad)),max(0,math.floor(y1-pad))
                right,bottom=min(width,math.ceil(x2+pad)),min(height,math.ceil(y2+pad))
                image=cv2.resize(frame[top:bottom,left:right],None,fx=6,fy=6,interpolation=cv2.INTER_NEAREST)
                cv2.rectangle(image,(round((x1-left)*6),round((y1-top)*6)),(round((x2-left)*6),round((y2-top)*6)),(0,255,255),2)
                name=f'{ident}-{suffix}.jpg'
                if not cv2.imwrite(str(output/name),image):
                    raise RuntimeError('Failed to write review image')
                images.append(name)
            left,top,size=zoom_region(q,width,height)
            start,end=max(0,q['end']-2),min(duration,q['start']+2)
            filters=(f'[0:v]split=2[f][c];[f]drawbox=x={left}:y={top}:w={size}:h={size}:color=yellow:t=2,'
                     'scale=960:540[full];'
                     f'[c]crop={size}:{size}:{left}:{top},scale=320:320,pad=320:540:0:110:black[zoom];[full][zoom]hstack[v]')
            subprocess.run([str(ffmpeg),'-hide_banner','-loglevel','error','-ss',str(start),'-i',str(video),'-t',str(end-start),
                '-filter_complex',filters,'-map','[v]','-an','-c:v','libx264','-threads','2','-preset','fast','-crf','19',
                '-pix_fmt','yuv420p','-movflags','+faststart','-n',str(output/f'{ident}.mp4')],check=True)
            row={'id':ident,'kind':'tracking','review_scope':'occlusion-reappearance',
                 'case_key':f"reappearance:{source_hash}:{q['a']}:{q['b']}:{q['end']}:{q['start']}",
                 'source_sha256':source_hash,'source_pair':[q['a'],q['b']],
                 'boundary':{k:q[k] for k in ('end','start','before_box','after_box')},
                 'title':f"원본 {int((offset+q['end'])//60):02d}:{int((offset+q['end'])%60):02d} 전후 같은 선수인가요?",
                 'reason':'왼쪽은 전체 경기, 오른쪽은 노란 영역의 실제 확대 영상입니다. 아래 두 사진은 마지막 관측과 다음 후보 관측입니다. 같은 선수인지 확인해 주세요. 흐리거나 가려졌다면 판단 어려움을 선택해 주세요.',
                 'before':f"직전 관측 ID {q['a']} · 원본 {offset+q['end']:.1f}초",
                 'after':f"이후 후보 ID {q['b']} · 원본 {offset+q['start']:.1f}초 · 자동 연결하지 않음",
                 'selection_reason':q.get('reason','ambiguous_observed_boundary'),
                 'video':f'{ident}.mp4','images':images,'time':offset+q['end'],'clip_start':offset+start,
                 'half':'h2','evaluation_scope':'human_identity_question_not_ground_truth_until_answered'}
            created.append(row);rows.append(row)
        unchanged=all(Path(p).is_file() and sha(p)==value for p,value in originals.items())
        if not unchanged or queue_path.read_bytes()!=queue_bytes:
            raise RuntimeError('Source store changed during staging; rebuild against latest answers')
        manifest={'published':False,'queue_sha256':hashlib.sha256(queue_bytes).hexdigest(),'source_sha256':source_hash,
                  'source_video':str(video.resolve()),'source_offset_s':offset,'items':created,'skipped':skipped,
                  'existing_json_checked':len(originals),'existing_json_unchanged':unchanged,
                  'store_json_sha256':originals,
                  'media_sha256':{p.name:sha(p) for p in output.iterdir() if p.suffix in ('.mp4','.jpg')},
                  'page':'/train/reappearance','answers':['same','different','unclear']}
        (output/'staged-publication.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
        return manifest
    finally:
        cap.release()


def main():
    p=argparse.ArgumentParser()
    for name in ('selected','video','store','output','ffmpeg'):p.add_argument(name,type=Path)
    p.add_argument('--offset',type=float,default=1950.);p.add_argument('--limit',type=int,default=3)
    a=p.parse_args();selected=json.loads(a.selected.read_text(encoding='utf-8'))
    result=prepare(selected,a.video,a.store,a.output,a.ffmpeg,a.offset,a.limit)
    print(json.dumps({'prepared':[r['id'] for r in result['items']],'skipped':result['skipped'],'published':False}))


if __name__=='__main__':main()
