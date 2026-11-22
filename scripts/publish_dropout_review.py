"""Dry-run by default; append staged identity questions without replacing answers."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import uuid

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.difference_review import IDENT, MEDIA
from app.live_publish import replace_snapshot


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def publish(staged, store, *, apply=False):
    staged,store=Path(staged).resolve(),Path(store).resolve()
    manifest=json.loads((staged/'staged-publication.json').read_text(encoding='utf-8'))
    root=store/'differences';queue_path=root/'queue.json'
    before=queue_path.read_bytes();old=json.loads(before)
    if hashlib.sha256(before).hexdigest()!=manifest['queue_sha256']:
        raise ValueError('Queue changed since preparation; rebuild the staged batch')
    originals=manifest.get('store_json_sha256')
    if not isinstance(originals,dict) or not originals:
        raise ValueError('Missing original JSON hashes; prepare again before publishing')
    def check_originals():
        for name,digest in originals.items():
            path=Path(name).resolve()
            if not path.is_relative_to(store) or path.suffix!='.json' or not path.is_file() or sha(path)!=digest:
                raise ValueError('Existing answers or source metadata changed; prepare again')
    check_originals()
    items=manifest['items'];ids={row['id'] for row in old['items']};names=[]
    for row in items:
        ident=row['id']
        if not IDENT.fullmatch(ident) or ident in ids or row.get('kind')!='tracking' or row.get('review_scope')!='occlusion-reappearance':
            raise ValueError('Duplicate or invalid staged question')
        ids.add(ident)
        for name in [row['video'],*row['images']]:
            if not MEDIA.fullmatch(name) or not (name==ident+'.mp4' or name.startswith(ident+'-')) or name in names:
                raise ValueError('Invalid staged media name')
            source=(staged/name).resolve();target=root/name
            if source.parent!=staged or not source.is_file() or sha(source)!=manifest['media_sha256'].get(name):
                raise ValueError('Staged media changed or is missing')
            if target.exists():
                raise ValueError('Destination media exists; no file will be overwritten')
            names.append(name)
    report={'dry_run':not apply,'publishable':[r['id'] for r in items],
            'checked_existing_json':len(originals),'original_json_unchanged':True,'published':[]}
    if not apply or not items:return report
    lock=root/'dropout-publication.lock'
    # Cooperative exclusion plus last-moment compare; other publishers must honor
    # the lock for full concurrency exclusion. Existing answers are never written.
    try:
        lock_handle=lock.open('x',encoding='utf-8')
    except FileExistsError as exc:
        raise ValueError('Another publication is in progress') from exc
    temp=root/f'queue-dropout-{uuid.uuid4().hex}.tmp'
    try:
        with lock_handle:lock_handle.write('staged identity question publication')
        check_originals()
        if queue_path.read_bytes()!=before:raise ValueError('Concurrent queue edit detected')
        backup=staged/f'queue-before-publication-{uuid.uuid4().hex}.json'
        with backup.open('xb') as stream:stream.write(before)
        for name in names:
            with (root/name).open('xb') as destination,(staged/name).open('rb') as source:
                shutil.copyfileobj(source,destination)
        updated={**old,'items':old['items']+items}
        with temp.open('x',encoding='utf-8') as stream:json.dump(updated,stream,ensure_ascii=False,indent=2)
        check_originals()
        if queue_path.read_bytes()!=before:raise ValueError('Concurrent queue edit detected; staged media remain unlisted')
        replace_snapshot(temp,queue_path)
        after=json.loads(queue_path.read_text(encoding='utf-8'))
        if after['items'][:len(old['items'])]!=old['items']:
            raise RuntimeError('Existing questions changed during publication')
        for name,digest in originals.items():
            if Path(name).resolve()!=queue_path.resolve() and sha(name)!=digest:
                raise RuntimeError('Existing answer changed concurrently; investigate without rollback')
        report.update(published=[r['id'] for r in items],backup=str(backup),queue_sha256=sha(queue_path))
        return report
    finally:
        if temp.exists():temp.unlink()
        lock.unlink()


def main():
    p=argparse.ArgumentParser();p.add_argument('staged',type=Path);p.add_argument('store',type=Path)
    p.add_argument('--publish',action='store_true');p.add_argument('--report',type=Path)
    args=p.parse_args()
    if args.report and (args.report.exists() or not args.report.parent.is_dir()):
        raise ValueError('Choose a new report filename in an existing directory before publication')
    report=publish(args.staged,args.store,apply=args.publish)
    if args.report:
        with args.report.open('x',encoding='utf-8') as stream:json.dump(report,stream,ensure_ascii=False,indent=2)
    print(json.dumps(report))


if __name__=='__main__':main()
