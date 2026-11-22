"""Preserve reviewed sequence provenance while adding newly answered identity pairs."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.difference_review import fingerprint
from app.learned_reconnect import descriptor
from app.temporal_reconnect import sequence_features, temporal_score


def sha(path):
    with Path(path).open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def verified_label(item, answer):
    if (answer.get('source') != 'human' or answer.get('id') != item['id']
            or answer.get('fingerprint') != fingerprint(item)):
        raise ValueError('Stale or nonhuman identity answer')
    if answer.get('verdict') == 'unclear':
        return None
    if answer.get('verdict') not in ('same', 'different'):
        raise ValueError('Unsupported identity answer')
    return int(answer['verdict'] == 'same')


def match_candidate(item, candidates):
    rows = [q for q in candidates if [str(q['a']), str(q['b'])] == item['source_pair']
            and all(abs(q[k] - item['boundary'][k]) < 1e-8 for k in ('end', 'start'))
            and all(q[k] == item['boundary'][k] for k in ('before_box', 'after_box'))]
    if len(rows) != 1:
        raise ValueError('Exactly one source-matched candidate required')
    return rows[0]


def features(pair):
    sides = []
    for side in ('before', 'after'):
        records = pair[side][-5:] if side == 'before' else pair[side][:3]
        seq = []
        for r in records:
            if sha(r['frame_path']) != r['frame_sha256']:
                raise ValueError('Raw frame changed')
            frame = cv2.imread(r['frame_path'])
            if frame is None:
                raise ValueError('Cannot decode frame')
            seq.append({'time': r['time'], 'box': r['box_xyxy'],
                        'descriptor': descriptor(frame, r['box_xyxy'])})
        sides.append(seq)
    result = sequence_features(*sides)
    if result is None:
        raise ValueError('Insufficient real observations')
    return result


def trace_candidate(item, frames):
    a, b = item['source_pair']
    boundary = item['boundary']
    result = {'a': a, 'b': b, **boundary}
    for side, raw, key in (('before', a, 'end'), ('after', b, 'start')):
        records = [{'time': f['time'], 'box': list(row[:4])} for f in frames
                   for row in f['source_tracks'] if str(int(row[4])) == raw
                   and ((f['time'] <= boundary[key]) if side == 'before' else (f['time'] >= boundary[key]))]
        records = records[-5:] if side == 'before' else records[:3]
        endpoint = records[-1] if side == 'before' and records else (records[0] if records else None)
        if endpoint is None or abs(endpoint['time']-boundary[key]) > 1e-8 or endpoint['box'] != boundary[side+'_box']:
            raise ValueError('Source trace does not reproduce reviewed endpoint')
        result[side+'_sequence'] = records
    return result


def runtime_history(pair):
    sides = {}
    for side in ('before', 'after'):
        records = pair[side][-5:] if side == 'before' else pair[side][:3]
        recent = [r for r in records if records[-1]['time']-r['time'] <= 1.01]
        consecutive = all(b['time']-a['time'] <= .25+1e-9 for a,b in zip(recent,recent[1:]))
        sides[side] = {'retained_count': len(recent), 'training_count': len(records),
                       'consecutive': consecutive}
    return {**sides, 'eligible': sides['before']['retained_count'] >= 3
            and sides['after']['retained_count'] >= 3 and sides['after']['consecutive'],
            'limitation': 'Eligibility only; current competing identities and aliases are not evaluated.'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('root', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    root, output = args.root.resolve(), args.output.resolve()
    work = root / 'work'
    store = work/'human-labels/public-own-match-review-20261111'
    original = {str(p): sha(p) for p in store.rglob('*.json')}
    old_manifest = work/'temporal-reconnect-20261113/train-sequences.json'
    manifest = json.loads(old_manifest.read_text(encoding='utf-8'))
    selection_path = work/'dropout-review-20261114/audit/candidates.json'
    selection = json.loads(selection_path.read_text(encoding='utf-8'))
    video = Path(selection['source_video'])
    if sha(video) != selection['source_sha256']:
        raise ValueError('Source video changed')
    queue = json.loads((store/'differences/queue.json').read_text(encoding='utf-8'))
    items = {r['id']: r for r in queue['items']}
    output.mkdir(parents=True, exist_ok=True)
    if (output/'train-sequences.json').exists() or (output/'model.json').exists():
        raise ValueError('Training output already exists')
    frame_dir = output/'raw-sequences'
    frame_dir.mkdir()
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise ValueError('Cannot decode source video')
    fps = cap.get(cv2.CAP_PROP_FPS)
    if abs(fps-30) > .01:
        raise ValueError('Expected the source 30fps replay')
    skipped = []
    try:
        trace_path = work/'reviewed-reconnect-live-20261113/run-73-observations.jsonl'
        frames = [json.loads(line) for line in trace_path.read_text(encoding='utf-8').splitlines()]
        for ident in ('d0111', 'd0112', 'd0113', 'd0114', 'd0115'):
            item = items[ident]
            answer_path = store/'differences/answers'/f'{ident}.json'
            answer = json.loads(answer_path.read_text(encoding='utf-8'))
            label = verified_label(item, answer)
            if label is None:
                skipped.append(ident)
                continue
            if item.get('source_sha256') != selection['source_sha256']:
                raise ValueError('Question refers to a different source')
            if any(p['id'] == ident for p in manifest['pairs']):
                raise ValueError('Duplicate training pair')
            candidate = trace_candidate(item, frames) if ident in ('d0111', 'd0112') else match_candidate(item, selection['questions'])
            provenance_path = trace_path if ident in ('d0111', 'd0112') else selection_path
            pair = {'id': ident, 'label': label, 'verdict': answer['verdict'],
                    'video_group': 'own-match-20261111', 'answer_path': str(answer_path),
                    'answer_sha256': sha(answer_path), 'fingerprint': answer['fingerprint']}
            for side, raw in (('before', candidate['a']), ('after', candidate['b'])):
                records = candidate[side+'_sequence'][-5:] if side == 'before' else candidate[side+'_sequence'][:3]
                pair[side] = []
                for index, record in enumerate(records):
                    frame_index = round(record['time']*fps)
                    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
                    ok, frame = cap.read()
                    if not ok:
                        raise ValueError('Cannot decode selected source frame')
                    path = frame_dir/f'{ident}-{side}-{index}.png'
                    if not cv2.imwrite(str(path), frame):
                        raise ValueError('Cannot save source frame')
                    pair[side].append({'frame_path': str(path), 'frame_sha256': sha(path),
                        'box_xyxy': record['box'], 'time': 1950+record['time'], 'track_id': str(raw),
                        'provenance': {'video_path': str(video), 'video_sha256': selection['source_sha256'],
                            'frame_index': frame_index, 'fps': fps, 'clip_time': record['time'],
                            'source_time_offset_s': 1950, 'source_trace': str(provenance_path),
                            'source_trace_sha256': sha(provenance_path), 'measured': True}})
            manifest['pairs'].append(pair)
    finally:
        cap.release()
    manifest['parent_manifest_sha256'] = sha(old_manifest)
    manifest['time_basis'] = 'Original match seconds; replay rows include explicit +1950 offset'
    manifest['skipped_unclear'] = skipped
    manifest_path = output/'train-sequences.json'
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    subprocess.run([sys.executable, str(Path(__file__).with_name('train_temporal_reconnect.py')),
                    str(manifest_path), str(output/'model.json')], check=True)
    subset = {**manifest, 'pairs': [p for p in manifest['pairs'] if p['id'] not in ('d0111', 'd0112')]}
    subset_path = output/'train-requested-three.json'
    subset_path.write_text(json.dumps(subset, indent=2), encoding='utf-8')
    subprocess.run([sys.executable, str(Path(__file__).with_name('train_temporal_reconnect.py')),
                    str(subset_path), str(output/'model-requested-three.json')], check=True)
    source_paths = sorted({r['provenance']['video_path'] for p in manifest['pairs']
                           for side in ('before', 'after') for r in p[side]})
    sources = {path: sha(path) for path in source_paths}
    manifest['train_source_sha256'] = list(sources.values())
    # Keep the exact manifest bytes used by the existing trainer; supplemental
    # source hashes belong to a separate provenance file and the model.
    (output/'source-videos.json').write_text(json.dumps(sources, indent=2), encoding='utf-8')
    for model_name in ('model.json', 'model-requested-three.json'):
        path = output/model_name
        model_data = json.loads(path.read_text(encoding='utf-8'))
        model_data['train_source_sha256'] = sorted(set(sources.values()))
        path.write_text(json.dumps(model_data, indent=2), encoding='utf-8')
    baseline = json.loads((work/'temporal-reconnect-20261113/model.json').read_text(encoding='utf-8'))
    candidate = json.loads((output/'model.json').read_text(encoding='utf-8'))
    rows = []
    for pair in manifest['pairs']:
        x = features(pair)
        entry = {'id': pair['id'], 'label': pair['label'], 'prediction_residual_heights': float(max(x[9], x[10])),
                 'runtime_history': runtime_history(pair)}
        for name, model in (('before', baseline), ('after', candidate)):
            value = temporal_score(model, x)
            entry[name] = {'score': value, 'passes_score': value >= model['threshold'],
                'passes_motion': bool(max(x[9], x[10]) <= model['max_prediction_residual_heights'])}
        rows.append(entry)
    unchanged = all(sha(p) == h for p, h in original.items())
    report = {'pairs': rows, 'train_count': len(rows), 'same': sum(r['label'] for r in rows),
              'different': sum(not r['label'] for r in rows), 'checked_json': len(original),
              'source_unchanged': unchanged, 'evaluation_scope': 'training_only',
              'policy_unchanged': all(baseline[k] == candidate[k] for k in
                  ('threshold', 'ambiguity_margin', 'max_prediction_residual_heights', 'regularization')),
              'limitation': 'Single-pair score/motion checks exclude competitor margin, birth timing and alias constraints.'}
    (output/'training-comparison.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    (output/'training-labels-before.json').write_text(json.dumps(original, indent=2), encoding='utf-8')
    if not unchanged:
        raise ValueError('Source JSON changed during training; inspect concurrent writer')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
