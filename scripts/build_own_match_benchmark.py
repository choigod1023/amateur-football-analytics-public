"""Freeze an annotation-pending own-match benchmark without inventing truth.

Known review/ball-candidate times are excluded with a 60-second buffer. This is
temporal separation from audited examples, not proof of unseen model ancestry
or independent players. Existing answers and production queues are read-only.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.difference_review import fingerprint


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def interval(start, end, **fields):
    start, end = float(start), float(end)
    if not math.isfinite(start + end) or start < 0 or end < start:
        raise ValueError('Invalid source-time interval')
    return {'start': start, 'end': end, **fields}


def overlaps(a, b, buffer=0):
    return a['start'] <= b['end'] + buffer and b['start'] - buffer <= a['end']


def free_windows(start, end, occupied, buffer=60):
    """Closed occupied intervals; callers keep selected clips inside open gaps."""
    if buffer < 0 or not math.isfinite(buffer):
        raise ValueError('Invalid exclusion buffer')
    current = [(float(start), float(end))]
    for row in occupied:
        low, high = row['start'] - buffer, row['end'] + buffer
        updated = []
        for a, b in current:
            if high <= a or low >= b:
                updated.append((a, b))
            else:
                if a < low: updated.append((a, low))
                if high < b: updated.append((high, b))
        current = updated
    return [interval(a, b) for a, b in current if b > a]


def verified_identity(item, answer, source_sha):
    if (item.get('kind') != 'tracking' or item.get('source_sha256') != source_sha
            or answer.get('source') != 'human' or answer.get('id') != item.get('id')
            or answer.get('fingerprint') != fingerprint(item)
            or answer.get('verdict') not in ('same', 'different')):
        raise ValueError('Missing, stale, ambiguous, or wrong-source identity answer')
    boundary = item['boundary']
    span = interval(boundary['end'], boundary['start'])
    pair = list(map(str, item['source_pair']))
    if len(pair) != 2 or pair[0] == pair[1]:
        raise ValueError('Expected two distinct observed tracks')
    return {'id': item['id'], 'tracks': pair, 'verdict': answer['verdict'],
            'source_sha256': source_sha, 'clip_interval': span,
            'boundary': boundary, 'answer_fingerprint': answer['fingerprint']}


def identity_groups(rows):
    """Do not split known track chains or overlapping review contexts."""
    groups = []
    for row in rows:
        group = [row]
        changed = True
        while changed:
            changed = False
            for old in groups[:]:
                if any(a['source_sha256'] == b['source_sha256'] and
                       (set(a['tracks']) & set(b['tracks']) or
                        overlaps(a['clip_interval'], b['clip_interval'], 4))
                       for a in group for b in old):
                    group.extend(old); groups.remove(old); changed = True
        groups.append(group)
    return [sorted(r['id'] for r in g) for g in groups]


def audited_intervals(store, queue):
    rows = []
    for path in sorted(store.glob('*.json')):
        data = read(path); source = data.get('source_provenance', {})
        time = source.get('clip_time_sec')
        if isinstance(time, (int, float)):
            rows.append(interval(time, time, kind='role_review', path=path.name,
                                 historical_split=source.get('split')))
    ball = read(store/'ball/index.json')
    for clip in ball['clips']:
        rows.append(interval(clip['start'], clip['start'] + ball['seconds'],
                             kind='ball_candidate_conservative', id=clip['id']))
    for item in queue['items']:
        if isinstance(item.get('time'), (int, float)):
            rows.append(interval(max(0, item['time']-2), item['time']+2,
                                 kind='difference_review', id=item['id']))
    events = read(store/'events/candidates.json')
    for event in events['items']:
        if (store/'events/labels'/f"{event['id']}.json").is_file():
            rows.append(interval(event['start'], event['end'], kind='labelled_event', id=event['id']))
    return rows


def build(root, output, ffmpeg):
    root, output = Path(root).resolve(), Path(output).resolve()
    store = root/'work/human-labels/public-own-match-review-20261111'
    original = {str(p): sha(p) for p in store.rglob('*.json')}
    queue = read(store/'differences/queue.json')
    replay = root/'work/live-dashboard-validation-20261113/replay-1950-2010.mp4'
    replay_sha = sha(replay)
    history = read(root/'work/identity-retraining-20261114/train-sequences.json')
    trained = {p['id'] for p in history['pairs']}
    identities = []
    rejected = []
    for item in queue['items']:
        if item.get('kind') != 'tracking': continue
        answer_path = store/'differences/answers'/f"{item['id']}.json"
        try:
            row = verified_identity(item, read(answer_path), replay_sha)
        except (ValueError, KeyError, OSError) as exc:
            rejected.append({'id': item['id'], 'reason': str(exc)}); continue
        row.update(answer_sha256=sha(answer_path), answer_path=str(answer_path),
                   already_used_for_training=item['id'] in trained)
        identities.append(row)
    occupied = audited_intervals(store, queue)
    # Explicit old development window remains excluded even if labels are sparse.
    occupied.append(interval(1950, 2010, kind='known_development_replay'))
    timeline = read(root/'work/own-match-merged-20261111/match_timeline.json')
    gaps = {camera: free_windows(*span, occupied, buffer=60)
            for camera, span in timeline['camera_settings'].items()}
    selected = interval(1560, 1585, camera='cam2', purpose='player_detection_and_role_only')
    conflicts = [r for r in occupied if overlaps(selected, r, 60)]
    if conflicts or not any(g['start'] < selected['start'] and selected['end'] < g['end'] for g in gaps['cam2']):
        raise ValueError('Frozen prospective evaluation intersects audited data exclusion')
    video = root/'work/own-match-merged-20261111/match_from_17min.mp4'
    video_sha = sha(video)
    expected = read(root/'work/identity-retraining-20261114/source-videos.json')
    if expected.get(str(video)) != video_sha:
        raise ValueError('Original match fingerprint changed')
    output.mkdir(parents=True, exist_ok=False)
    clip = output/'evaluation-pending-cam2-1560-1585.mp4'
    command = [str(ffmpeg), '-hide_banner', '-loglevel', 'error', '-ss', '1560', '-i', str(video),
               '-t', '25', '-map', '0:v:0', '-an', '-c:v', 'libx264', '-preset', 'fast', '-crf', '18',
               '-threads', '2', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', '-n', str(clip)]
    subprocess.run(command, check=True)
    capture = cv2.VideoCapture(str(video)); samples = []
    try:
        fps = capture.get(cv2.CAP_PROP_FPS)
        if not capture.isOpened() or fps <= 0: raise ValueError('Unreadable original recording')
        for offset in (5, 12, 20):
            t = 1560 + offset; frame_index = round(t*fps)
            capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index); ok, frame = capture.read()
            if not ok: raise ValueError('Cannot decode pending sample')
            image = output/f'pending-{t}.jpg'
            if not cv2.imwrite(str(image), frame): raise ValueError('Cannot save pending sample')
            samples.append({'source_time':t, 'source_frame_index':frame_index, 'clip_time':offset,
                            'image':image.name, 'sha256':sha(image), 'annotations':None,
                            'annotation_status':'pending_human', 'complete_frame_annotation':False})
    finally:
        capture.release()
    audit = {'buffer_seconds':60, 'occupied':occupied, 'camera_free_windows':gaps,
             'selected':selected, 'selected_conflicts':conflicts}
    manifest = {'version':1, 'status':'evaluation_pending', 'historical_identity_answers':identities,
                'historical_identity_groups':identity_groups(identities), 'not_reused_identity_rows':rejected,
                'train_answer_ids':[r['id'] for r in identities if r['already_used_for_training']],
                'evaluation':{**selected, 'original_video':str(video), 'original_sha256':video_sha,
                              'clip':clip.name, 'clip_sha256':sha(clip), 'fps':fps, 'samples':samples,
                              'ground_truth':None, 'metrics':None, 'calibration_status':'pending_cam2'},
                'training_policy':'Do not add this interval or its human answers to training while it remains evaluation.',
                'promotion_allowed':False, 'annotation_tasks':['Complete visible-person boxes and roles',
                    'Add missed people; mark non-player detections and uncertainty',
                    'Review identities across the 25 seconds before computing ID metrics'],
                'limits':['Historical 60-second replay and its eight answers were already used in development/training.',
                    'Full original match was previously automatically scanned; this is not an untouched video or independent match.',
                    '60-second temporal separation only covers audited role, ball-candidate, difference and labelled-event indices.',
                    'Training ancestry of every old model is not fully auditable; absence from these indices is not proof of universal non-exposure.',
                    'Same match players can appear elsewhere; person-disjoint generalisation is not established.',
                    'Cam2 has a different view; cam3 calibration cannot be reused for tactical position accuracy.',
                    'Three sample images and an unlabelled clip are review material, not dense tracking ground truth.']}
    if any(not Path(p).is_file() or sha(p) != h for p,h in original.items()):
        raise ValueError('Original review store changed during preparation')
    manifest['preservation']={'checked_json':len(original), 'changed':0}
    for name, data in [('manifest.json',manifest),('exclusion-audit.json',audit),('command.json',command)]:
        (output/name).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    return manifest


if __name__ == '__main__':
    p=argparse.ArgumentParser()
    p.add_argument('root',type=Path);p.add_argument('output',type=Path);p.add_argument('ffmpeg',type=Path)
    a=p.parse_args();m=build(a.root,a.output,a.ffmpeg)
    print(json.dumps({'status':m['status'],'answers':len(m['historical_identity_answers']),
                      'evaluation':m['evaluation']['clip'],'preservation':m['preservation']}))
