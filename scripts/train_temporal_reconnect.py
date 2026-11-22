"""Train multi-frame features only from verified scene answers and raw images."""
import argparse
import hashlib
import json
import sys
from pathlib import Path
import cv2
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.difference_review import fingerprint
from app.learned_reconnect import descriptor
from app.temporal_reconnect import sequence_features, fit_temporal, temporal_score


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('manifest', type=Path)
    p.add_argument('output', type=Path)
    args = p.parse_args()
    data = json.loads(args.manifest.read_text(encoding='utf-8'))
    features, labels, groups, audit = [], [], set(), []
    for pair in data['pairs']:
        path = Path(pair['answer_path'])
        answer = json.loads(path.read_text(encoding='utf-8'))
        queue = json.loads((path.parent.parent / 'queue.json').read_text(encoding='utf-8'))
        item = next(r for r in queue['items'] if r['id'] == pair['id'])
        if (sha(path) != pair['answer_sha256'] or answer.get('source') != 'human'
                or answer['fingerprint'] != fingerprint(item) or answer['id'] != pair['id']
                or answer['verdict'] not in ('same', 'different')
                or int(answer['verdict'] == 'same') != pair['label']):
            raise ValueError('Stale or inconsistent human label')
        sides = []
        for side in ('before', 'after'):
            selected = pair[side][-5:] if side == 'before' else pair[side][:3]
            seq = []
            for row in selected:
                if sha(row['frame_path']) != row['frame_sha256']:
                    raise ValueError('Raw frame changed')
                frame = cv2.imread(row['frame_path'])
                if frame is None:
                    raise ValueError('Cannot decode frame')
                seq.append({'time': row['time'], 'box': row['box_xyxy'],
                            'descriptor': descriptor(frame, row['box_xyxy'])})
            sides.append(seq)
        x = sequence_features(*sides)
        if x is None:
            raise ValueError('Need at least three real observations on each side')
        features.append(x)
        labels.append(pair['label'])
        groups.add(pair['video_group'])
        audit.append({'id': pair['id'], 'label': pair['label'],
                      'frames_before': len(sides[0]), 'frames_after': len(sides[1])})
    model = fit_temporal(features, labels)
    model.update({'train_video_groups': sorted(groups), 'manifest_sha256': sha(args.manifest),
                  'operationally_approved': False,
                  'policy': '0.90 score, 0.15 margin, 1.5-height bidirectional residual; fixed before evaluation'})
    for row, x in zip(audit, features):
        row['training_score'] = temporal_score(model, x)
    model['training_diagnostics'] = audit
    with args.output.open('x', encoding='utf-8') as f:
        json.dump(model, f, indent=2)
    print(json.dumps({'pairs': len(labels), 'training_only': audit}))


if __name__ == '__main__':
    main()
