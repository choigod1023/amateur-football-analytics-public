"""Training-recording applicability audit, not independent accuracy evaluation."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.temporal_reconnect import TemporalLinker
from app.difference_review import fingerprint


def main():
    p = argparse.ArgumentParser()
    for name in ('video', 'observations', 'store', 'baseline', 'candidate', 'output'):
        p.add_argument(name, type=Path)
    a = p.parse_args()
    read = lambda path: json.loads(path.read_text(encoding='utf-8'))
    queue = read(a.store/'differences/queue.json')['items']
    source_hash = hashlib.sha256(a.video.read_bytes()).hexdigest()
    questions = []
    for ident in ('d0111','d0112','d0113','d0114','d0115'):
        item = next(r for r in queue if r['id'] == ident)
        answer = read(a.store/'differences/answers'/f'{ident}.json')
        if (item['source_sha256'] != source_hash or answer.get('fingerprint') != fingerprint(item)
                or answer.get('source') != 'human' or answer.get('id') != ident
                or answer.get('verdict') not in ('same', 'different', 'unclear')):
            raise ValueError('Invalid source or stale human answer')
        questions.append((item, answer))
    linkers = {name: TemporalLinker(read(getattr(a, name))) for name in ('baseline','candidate')}
    frames = [json.loads(s) for s in a.observations.read_text(encoding='utf-8').splitlines()]
    cap = cv2.VideoCapture(str(a.video))
    if not cap.isOpened():
        raise ValueError('Cannot open recording')
    fps = cap.get(cv2.CAP_PROP_FPS)
    events, checkpoints = {k:[] for k in linkers}, []
    try:
        for row in frames:
            t = row['time']
            cap.set(cv2.CAP_PROP_POS_FRAMES, round(t*fps))
            ok, frame = cap.read()
            if not ok:
                raise ValueError('Recording decode failed')
            tracks = np.asarray(row['source_tracks'], dtype=float).reshape(-1,5)
            for name, linker in linkers.items():
                _, joins = linker.update(t, frame, tracks)
                events[name].extend(joins)
                for item, answer in questions:
                    if abs(t-item['boundary']['end']) < 1e-6:
                        state = linker.memory.get(str(item['source_pair'][0]), {})
                        checkpoints.append({'id':item['id'],'mode':name,
                                            'last_observation_history_count':len(state.get('history',[]))})
    finally:
        cap.release()
    outcomes = []
    for item, answer in questions:
        old, new = map(str,item['source_pair'])
        outcomes.append({'id':item['id'], 'human_verdict':answer['verdict'],
            'exact_boundary_joins':{name:[r for r in rows if r['previous_raw']==old
                and r['raw']==new and abs(r['birth_time']-item['boundary']['start'])<1e-6]
                for name,rows in events.items()}})
    result = {'scope':'training_recording_only_no_generalization_claim',
              'frames':len(frames),'source_sha256':source_hash,
              'history_checkpoints':checkpoints,'outcomes':outcomes,'events':events,
              'limits':['Raw tracker replay omits production IdentityGuard/role/pitch filters.',
                        'Human identity answers do not imply sufficient observations for automatic linking.']}
    with a.output.open('x',encoding='utf-8') as f:
        json.dump(result,f,ensure_ascii=False,indent=2)
    print(json.dumps({'frames':len(frames),'outcomes':outcomes}))


if __name__ == '__main__':
    main()
