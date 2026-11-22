"""Append unanswered role/team questions; never create or replace human answers.

Usage: python scripts/prepare_capacity_review.py selected.json video.mp4 store output
Selection: list (or {questions:[...]}) of time/track_id/bbox/reason. Audit aliases
time_s/raw_id/box/review_reason and absolute clip_time_s are also accepted.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.training_labels import TrainingLabels

PURPOSE = 'overcapacity_role_team_check'
REASONS = {
    'occluded_person_team_uncertain_not_confirmed_duplicate': '가려진 인물의 소속 팀이 불확실합니다. 중복으로 확정하지 않았으니 상자 안 인물의 역할과 팀을 확인해 주세요.',
    'one_box_contains_multiple_people': '상자 안에 여러 사람이 겹쳤는지 확인해 주세요. 한 사람의 상자가 아니면 불명으로 두고 필요한 선수 상자를 직접 추가해 주세요.',
    'dark_person_classified_team_a_role_uncertain': '어두운 옷의 인물입니다. 선수·심판·골키퍼 등 역할과 소속 팀을 확인해 주세요.',
    'far_person_role_and_team_uncertain': '먼 거리의 인물입니다. 역할과 소속 팀이 불확실합니다. 보이지 않으면 불명으로 남겨 주세요.',
}


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def validate(item):
    t = float(item.get('time', item.get('time_s', -1)))
    box = [float(x) for x in item.get('bbox', item.get('box', []))]
    ident = str(item.get('track_id', item.get('raw_id', '')))
    if not math.isfinite(t) or t < 0 or len(box) != 4 or not all(map(math.isfinite, box)):
        raise ValueError('Finite nonnegative time and four finite box coordinates required')
    if not ident or len(ident) > 128 or box[2] <= box[0] or box[3] <= box[1]:
        raise ValueError('Valid track ID and nonempty box required')
    return t, ident, box


def prepare(selected, video, store, output):
    video, store, output = map(Path, (video, store, output))
    questions = selected if isinstance(selected, list) else selected['questions']
    parsed = [validate(q) for q in questions]
    source_hash = sha(video)
    previous = {}
    manifest = output / 'publication.json'
    if manifest.exists():
        prior = json.loads(manifest.read_text(encoding='utf-8'))
        if prior.get('source_sha256') != source_hash:
            raise ValueError('Output directory belongs to a different recording')
        previous = {q['case_key']:q for q in prior.get('questions', [])}
    before = {p.name: sha(p) for p in store.glob('*.json')}
    existing = {}
    for path in (store / 'pending').glob('*.json'):
        meta = json.loads(path.read_text(encoding='utf-8'))
        key = meta.get('source_provenance', {}).get('case_key')
        if key:
            existing[key] = path.stem
        for member in meta.get('source_provenance', {}).get('case_keys', []):
            existing[member] = path.stem
    output.mkdir(parents=True, exist_ok=True)
    capture = cv2.VideoCapture(str(video))
    staged = []
    try:
        if not capture.isOpened():
            raise ValueError('Cannot open selected recording')
        fps, count = capture.get(cv2.CAP_PROP_FPS), capture.get(cv2.CAP_PROP_FRAME_COUNT)
        if fps <= 0 or count <= 0:
            raise ValueError('Recording must have a known duration')
        last = (count - 1) / fps
        for q, (t, ident, box) in zip(questions, parsed):
            if t > last:
                raise ValueError('Selected time is outside recording')
            key_data = [PURPOSE, source_hash, t, ident, box]
            key = hashlib.sha256(json.dumps(key_data, separators=(',', ':')).encode()).hexdigest()
            if key in existing:
                staged.append({**previous.get(key, {}), 'case_key': key, 'token': existing[key], 'status': 'existing'})
                continue
            center = None
            images = []
            for suffix, when in (('before', max(0, t-1)), ('center', t), ('after', min(last, t+1))):
                capture.set(cv2.CAP_PROP_POS_MSEC, when*1000)
                ok, frame = capture.read()
                if not ok:
                    raise ValueError(f'Cannot decode {when:.3f}s; no questions published')
                h, w = frame.shape[:2]
                x1,y1,x2,y2 = box
                if not (0 <= x1 < x2 <= w and 0 <= y1 < y2 <= h):
                    raise ValueError('Selected box lies outside decoded frame')
                pad = max(32, (y2-y1)*2)
                left, top = max(0, int(x1-pad)), max(0, int(y1-pad))
                right, bottom = min(w, math.ceil(x2+pad)), min(h, math.ceil(y2+pad))
                crop = frame[top:bottom, left:right]
                scale = min(6., 960/max(crop.shape[:2]))
                enlarged = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_NEAREST)
                if suffix == 'center':
                    center = frame
                    cv2.rectangle(enlarged, (round((x1-left)*scale), round((y1-top)*scale)),
                                  (round((x2-left)*scale), round((y2-top)*scale)), (0,255,255), 2)
                # At adjacent times the person may move: this is fixed context,
                # not an asserted trajectory or a newly labelled box.
                name = f'{key[:16]}-{suffix}.jpg'
                target = output / name
                if not target.exists() and not cv2.imwrite(str(target), enlarged):
                    raise IOError('Cannot save context crop')
                images.append({'file':name, 'time_s':when, 'fixed_context':True})
            staged.append({'case_key':key, 'frame':center, 'time':t, 'track_id':ident,
                           'box':box, 'question':q, 'crops':images, 'status':'new'})
    finally:
        capture.release()
    labels = TrainingLabels(store)
    results, groups = [], {}
    for item in staged:
        if item['status'] == 'existing':
            results.append(item)
            continue
        groups.setdefault(item['time'], []).append(item)
    for t, group in groups.items():
        item = group[0]
        q = item['question']
        absolute = float(q.get('clip_time_s', t))
        reasons = [i['question'].get('reason', i['question'].get('review_reason', '역할과 소속 팀을 확인해 주세요.')) for i in group]
        message = ' '.join(dict.fromkeys(REASONS.get(reason, '역할과 소속 팀이 불확실합니다. 구분할 수 없다면 불명으로 남겨 주세요.') for reason in reasons))
        ids = ', '.join(i['track_id'] for i in group)
        keys = [i['case_key'] for i in group]
        group_key = keys[0] if len(keys) == 1 else hashlib.sha256(':'.join(sorted(keys)).encode()).hexdigest()
        timestamp = f"인원 초과 확인 · {int(absolute//60):02d}:{absolute%60:04.1f} · ID {ids} · {message}"
        provenance = {'split':'train', 'purpose':PURPOSE, 'case_key':group_key, 'case_keys':keys,
            'source_sha256':source_hash, 'source_time_sec':t, 'clip_time_sec':absolute,
            'camera_setting':'cam3', 'review_reasons':reasons,
            'split_note':'Human review requested; after answering this scene must not be claimed as unseen evaluation.'}
        labels.publish(item['frame'], [(i['box'], i['track_id']) for i in group], timestamp,
                       'capacity_role_review', provenance=provenance)
        frozen = labels.freeze()
        if not frozen:
            raise RuntimeError('Could not create frozen review question')
        results.extend({k:v for k,v in i.items() if k not in ('frame','question','box')} | {'token':frozen['token']} for i in group)
    changed = [name for name,digest in before.items() if not (store/name).exists() or sha(store/name) != digest]
    report = {'source_sha256':source_hash, 'questions':results, 'answer_files_checked':len(before),
              'changed_existing_answer_files':changed, 'answers_written':0}
    temp = output/'publication.tmp'
    temp.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(output/'publication.json')
    if changed:
        raise RuntimeError('Existing answers changed during publication; inspect concurrent writer')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('selected', 'video', 'store', 'output'):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    report = prepare(json.loads(args.selected.read_text(encoding='utf-8')), args.video, args.store, args.output)
    print(json.dumps(report, ensure_ascii=False))
