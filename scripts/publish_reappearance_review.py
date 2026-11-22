"""Prepare and append only selected ambiguous scenes, preserving old item fingerprints."""
import argparse,hashlib,json,shutil,subprocess,sys
from pathlib import Path
import cv2
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.live_publish import replace_snapshot


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('selected',type=Path);p.add_argument('video',type=Path);p.add_argument('store',type=Path);p.add_argument('output',type=Path);p.add_argument('ffmpeg');a=p.parse_args()
    root=a.store/'differences';queue_path=root/'queue.json';old_bytes=queue_path.read_bytes();old=json.loads(old_bytes)
    a.output.mkdir(exist_ok=False);source_hash=sha(a.video)
    originals={str(p):sha(p) for p in a.store.rglob('*.json') if p!=queue_path}
    max_id=max(int(r['id'][1:]) for r in old['items']);keys={r.get('case_key') for r in old['items']};created=[]
    cap=cv2.VideoCapture(str(a.video));width=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH));height=int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT));duration=cap.get(cv2.CAP_PROP_FRAME_COUNT)/cap.get(cv2.CAP_PROP_FPS)
    for q in json.loads(a.selected.read_text(encoding='utf-8'))['questions']:
        key=f"reappearance:{source_hash}:{q['a']}:{q['b']}:{q['end']}:{q['start']}"
        if key in keys:continue
        max_id+=1;ident=f'd{max_id:04d}';images=[]
        for suffix,t,box in [('a',q['end'],q['before_box']),('b',q['start'],q['after_box'])]:
            cap.set(cv2.CAP_PROP_POS_MSEC,t*1000);ok,frame=cap.read()
            if not ok:raise RuntimeError('Cannot decode selected endpoint')
            x1,y1,x2,y2=map(int,box);pad=max(16,y2-y1)
            crop_x,crop_y=max(0,x1-pad),max(0,y1-pad)
            crop=frame[crop_y:min(height,y2+pad),crop_x:min(width,x2+pad)]
            image=cv2.resize(crop,None,fx=6,fy=6,interpolation=cv2.INTER_NEAREST);name=f'{ident}-{suffix}.jpg'
            cv2.rectangle(image,((x1-crop_x)*6,(y1-crop_y)*6),((x2-crop_x)*6,(y2-crop_y)*6),(0,255,255),2)
            if not cv2.imwrite(str(a.output/name),image):raise RuntimeError('Crop write failed')
            images.append(name)
        boxes=[q['before_box'],q['after_box']];cx=sum((r[0]+r[2])/2 for r in boxes)/2;cy=sum((r[1]+r[3])/2 for r in boxes)/2
        size=max(128,int(max(r[3]-r[1] for r in boxes)*5));left=max(0,min(width-size,int(cx-size/2)));top=max(0,min(height-size,int(cy-size/2)))
        start=max(0,q['end']-2);end=min(duration,q['start']+2)
        filters=f'[0:v]split=2[f][c];[f]drawbox=x={left}:y={top}:w={size}:h={size}:color=yellow:t=2,scale=960:540[full];[c]crop={size}:{size}:{left}:{top},scale=320:320,pad=320:540:0:110:black[zoom];[full][zoom]hstack[v]'
        subprocess.run([a.ffmpeg,'-hide_banner','-loglevel','error','-ss',str(start),'-i',str(a.video),'-t',str(end-start),'-filter_complex',filters,'-map','[v]','-an','-c:v','libx264','-threads','2','-preset','fast','-crf','19','-pix_fmt','yuv420p','-movflags','+faststart','-n',str(a.output/f'{ident}.mp4')],check=True)
        created.append({'id':ident,'kind':'tracking','review_scope':'occlusion-reappearance','case_key':key,
            'source_sha256':source_hash,'source_pair':[q['a'],q['b']],'boundary':{'end':q['end'],'start':q['start'],'before_box':q['before_box'],'after_box':q['after_box']},
            'title':f"원본 {int((1950+q['end'])//60):02d}:{int((1950+q['end'])%60):02d} 가림 뒤 같은 선수인가요?",
            'reason':'왼쪽은 전체 장면, 오른쪽은 노란 사각 영역의 실제 확대 영상입니다. 아래 사진은 사라지기 직전과 다시 나타난 직후입니다. 주변 선수와 비교해 같은 선수인지 확인해 주세요. 흐려서 알 수 없으면 판단 어려움을 선택하세요.',
            'before':f"사라지기 직전 관측 ID {q['a']}",'after':f"다시 나타난 관측 ID {q['b']} · 자동 병합 보류",
            'video':f'{ident}.mp4','images':images,'time':1950+q['end'],'clip_start':1950+start,'half':'h2','evaluation_scope':'human_reappearance_review_not_ground_truth_until_answered'})
    cap.release()
    # Stage first. Compare source queue again before appending; never overwrite an old item.
    if queue_path.read_bytes()!=old_bytes:raise RuntimeError('Queue changed; rebuild against current queue')
    for item in created:
        for name in [item['video'],*item['images']]:
            with (root/name).open('xb') as target,(a.output/name).open('rb') as source:shutil.copyfileobj(source,target)
    old['items'].extend(created)
    (a.output/'queue-before.json').write_bytes(old_bytes)
    temp=root/'queue-reappearance.tmp';temp.write_text(json.dumps(old,ensure_ascii=False,indent=2),encoding='utf-8')
    if queue_path.read_bytes()!=old_bytes:raise RuntimeError('Concurrent queue edit detected; new media is not published')
    replace_snapshot(temp,queue_path)
    unchanged=all(sha(Path(p))==v for p,v in originals.items())
    report={'published':[i['id'] for i in created],'existing_json_unchanged_except_append_queue':unchanged,'checked_json':len(originals)}
    (a.output/'publication.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report))
    if not unchanged:raise RuntimeError('Existing JSON changed during publishing; investigate concurrent writer')


if __name__=='__main__':main()
