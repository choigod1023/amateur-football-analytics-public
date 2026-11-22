"""Append only newly worded coaching questions. Preserve original items and answers."""
import argparse
import json
from pathlib import Path


def main():
    p = argparse.ArgumentParser()
    p.add_argument('store', type=Path)
    p.add_argument('evaluation', type=Path)
    args = p.parse_args()
    queue_path = args.store / 'differences/queue.json'
    queue = json.loads(queue_path.read_text(encoding='utf-8'))
    by_id = {i['id']: i for i in queue['items']}
    evaluation = json.loads(args.evaluation.read_text(encoding='utf-8'))
    added = []
    for scene in evaluation['scenes']:
        if not scene['requires_new_text_review']:
            continue
        old = by_id[scene['id']]
        ident = f"d{100 + int(scene['id'][1:]):04d}"
        if ident in by_id:
            continue
        preferred = old['after'] if scene['verdict'] == 'after' else old['before']
        new = '\n'.join(e['title'] + ': ' + e['text'] for e in scene['candidate_events']) or '이 구간에 알림 없음'
        queue['items'].append({'id': ident, 'kind': 'coaching', 'title': old['title'] + ' · 수정 문구 확인',
            'reason': '이 장면에 저장한 답은 그대로 반영했습니다. 같은 선수들의 실제 후퇴가 확인되지 않아 지시 문구를 바꿨습니다. 이전에 선택한 설명과 새 문구 중 영상에 더 맞는 쪽을 확인해 주세요.',
            'before': '이전에 선택한 설명: ' + preferred, 'after': new,
            'video': old['video'], 'images': [], 'time': old['time'], 'parent_review': old['id'],
            'evaluation_scope': 'development wording review; not independent test'})
        added.append(ident)
    temporary = queue_path.with_suffix('.new.json')
    temporary.write_text(json.dumps(queue, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(queue_path)
    print(json.dumps({'added': added}))


if __name__ == '__main__':
    main()
