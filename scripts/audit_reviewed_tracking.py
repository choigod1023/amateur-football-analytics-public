"""Verify reapplication of existing human answers, NOT unseen identity accuracy."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.reviewed_reconnect import ReviewedReconnector
from app.reappearance_review import reviewed_links
from evaluate_role_tracking import reviewed_pairs, sha, load_rows


def audit(rows, store, source_sha):
    linker = ReviewedReconnector(reviewed_links(store, source_sha))
    adjusted, events = [], []
    for row in rows:
        aliases, emitted = linker.update(row['time'], row['observed_tracks'])
        events.extend(emitted)
        tracks = []
        for track in row['observed_tracks']:
            changed = list(track)
            changed[4] = int(aliases.get(str(int(track[4])), str(int(track[4]))))
            tracks.append(changed)
        adjusted.append({**row, 'observed_tracks': tracks})
    return {'before': reviewed_pairs(rows, store, source_sha),
            'after': reviewed_pairs(adjusted, store, source_sha), 'events': events,
            'uses_human_answers_for_correction': True,
            'unseen_identity_accuracy': None,
            'scope': 'Exact reviewed recording and reproduced boundaries only; no model generalization claim'}


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    for name in ('trace', 'store', 'video', 'output'):
        p.add_argument(name, type=Path)
    a = p.parse_args()
    result = audit(load_rows(a.trace), a.store, sha(a.video))
    result['trace_sha256'], result['video_sha256'] = sha(a.trace), sha(a.video)
    with a.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
