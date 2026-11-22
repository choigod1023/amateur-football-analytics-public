"""Read-only logged pipeline audit and deduplicated human identity candidates."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.dropout_audit import analyse, reconnect_candidates
from app.difference_review import DifferenceReview, fingerprint, read


def score_candidates(questions, video, model_path):
    import cv2
    from app.temporal_reconnect import sequence_features, temporal_score
    from app.learned_reconnect import descriptor
    model=json.loads(model_path.read_text(encoding='utf-8'))
    cap=cv2.VideoCapture(str(video))
    fps=cap.get(cv2.CAP_PROP_FPS)
    if fps <= 0:
        raise ValueError('Cannot read source FPS')
    output=[]
    try:
        for row in questions:
            sides=[]
            for observations in (row['before_sequence'],row['after_sequence'][:3]):
                sequence=[]
                for observation in observations:
                    cap.set(cv2.CAP_PROP_POS_FRAMES,round(observation['time']*fps))
                    ok,image=cap.read()
                    if not ok:
                        raise ValueError('Cannot decode candidate observation')
                    sequence.append({'time':observation['time'],'box':observation['box'],
                                     'descriptor':descriptor(image,observation['box'])})
                sides.append(sequence)
            x=sequence_features(*sides)
            output.append({'pair':[row['a'],row['b']], 'features':x.tolist() if x is not None else None,
                           'score':temporal_score(model,x), 'threshold':model['threshold'],
                           'motion_gate_pass':bool(x is not None and max(x[9],x[10])<=model['max_prediction_residual_heights']),
                           'model_sha256':hashlib.sha256(model_path.read_bytes()).hexdigest(),
                           'model_scope':'Four training pairs; ranking score is not calibrated identity probability. All competing candidates not scored here.'})
    finally:
        cap.release()
    return output


def main():
    p = argparse.ArgumentParser()
    p.add_argument('observations', type=Path)
    p.add_argument('video', type=Path)
    p.add_argument('store', type=Path)
    p.add_argument('output', type=Path)
    p.add_argument('--temporal-model', type=Path)
    a = p.parse_args()
    frames = [json.loads(line) for line in a.observations.read_text(encoding='utf-8').splitlines()]
    source_hash = hashlib.sha256(a.video.read_bytes()).hexdigest()
    before = {str(f): hashlib.sha256(f.read_bytes()).hexdigest() for f in a.store.rglob('*.json')}
    result = analyse(frames)
    result.update(source_sha256=source_hash, log_sha256=hashlib.sha256(a.observations.read_bytes()).hexdigest())
    review = DifferenceReview(a.store)
    existing = [item for item in review.items().values() if item.get('source_sha256') == source_hash]
    questions, skipped = [], []
    for candidate in reconnect_candidates(frames, limit=None):
        pair = [candidate['a'], candidate['b']]
        overlap = [item for item in existing if set(map(str,item.get('source_pair', []))) == set(pair)]
        if overlap:
            skipped.append({'pair': pair, 'questions': [item['id'] for item in overlap], 'reason':'already_queued_or_answered_for_source'})
            continue
        if any(set(pair) & {q['a'],q['b']} for q in questions):
            continue
        questions.append(candidate)
        if len(questions) == 3:
            break
    current_answers=[]
    for item in existing:
        answer=read(review.root/'answers'/f"{item['id']}.json",{})
        if answer.get('fingerprint')==fingerprint(item) and answer.get('source')=='human':
            current_answers.append({'id':item['id'],'pair':item.get('source_pair'),'verdict':answer.get('verdict')})
    a.output.mkdir(parents=True, exist_ok=True)
    (a.output/'summary.json').write_text(json.dumps({k:v for k,v in result.items() if k!='events'},ensure_ascii=False,indent=2),encoding='utf-8')
    (a.output/'events.json').write_text(json.dumps(result['events'],ensure_ascii=False,indent=2),encoding='utf-8')
    candidate_report={'source_sha256':source_hash,'source_video':str(a.video.resolve()),'questions':questions,
                      'skipped':skipped,'existing_current_identity_answers':current_answers,
                      'labels_unchanged':all(hashlib.sha256(Path(f).read_bytes()).hexdigest()==h for f,h in before.items()),
                      'limitation':'Geometry ranks questions, never establishes same-person truth. Existing role answers are not identity labels.'}
    (a.output/'candidates.json').write_text(json.dumps(candidate_report,ensure_ascii=False,indent=2),encoding='utf-8')
    if a.temporal_model:
        scores=score_candidates(questions,a.video,a.temporal_model)
        (a.output/'candidate-temporal-scores.json').write_text(json.dumps(scores,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='events'},ensure_ascii=False))
    print('questions',[(q['a'],q['b'],q['end'],q['start']) for q in questions])


if __name__=='__main__':main()
