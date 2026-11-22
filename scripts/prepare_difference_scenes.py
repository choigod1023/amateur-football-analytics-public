"""Build a small, new review queue from changed coaching events, without editing labels."""
import argparse
import json
from pathlib import Path
import subprocess

TITLES = {'run': '수비 라인 뒤 침투', 'conceded_run': '상대 침투', 'box_attack': '박스 안 공격 인원',
          'line_drop': '수비 라인 하락', 'gap_wide': '라인 간격', 'isolated': '앞선 선수 고립'}


def unmatched(before, after, tolerance=3):
    """One-to-one match of the same kind; a shifted alert is not automatically a new event."""
    available = set(range(len(after)))
    removed = []
    for event in before:
        candidates = [i for i in available if after[i]['kind'] == event['kind'] and abs(after[i]['time'] - event['time']) <= tolerance]
        if candidates:
            available.remove(min(candidates, key=lambda i: abs(after[i]['time'] - event['time'])))
        else:
            removed.append(event)
    return removed, [after[i] for i in sorted(available)]


def describe(events):
    return ' / '.join(f"{int(e['time']//60):02d}:{int(e['time']%60):02d} {TITLES.get(e['kind'], e['kind'])}" for e in events) or '이 구간에 알림 없음'


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--comparison', type=Path, required=True)
    p.add_argument('--video', type=Path, required=True)
    p.add_argument('--ffmpeg', required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    data = json.loads(args.comparison.read_text(encoding='utf-8'))
    half = data['halves']['h2']  # confirmed attack direction only
    before = half['legacy']['events']
    after = half['observed_only_saved_calibration']['events']
    removed, added = unmatched(before, after)
    items = []
    selected = []
    for event in sorted(removed + added, key=lambda e: e['time']):
        t = event['time']
        if any(abs(t - previous) < 20 for previous in selected):
            continue
        selected.append(t)
        start = max(0, t - 8)
        ident = f'd{len(items)+1:04d}'
        prior = [e for e in before if abs(e['time'] - t) <= 5]
        current = [e for e in after if abs(e['time'] - t) <= 5]
        subprocess.run([args.ffmpeg, '-hide_banner', '-loglevel', 'error', '-ss', str(start), '-i', str(args.video),
                        '-t', '16', '-an', '-c:v', 'libx264', '-preset', 'fast', '-crf', '20', '-threads', '2',
                        '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(args.output / f'{ident}.mp4')], check=True)
        items.append({'id': ident, 'kind': 'coaching', 'title': f'후반 {int(t//60):02d}:{int(t%60):02d} 코칭 비교',
                      'reason': '같은 장면에서 보간 포함 여부에 따라 알림이 달라졌습니다. 영상으로 어느 설명이 맞는지 확인해 주세요. 공 소유와 실제 패스는 판정하지 않습니다.',
                      'video': f'{ident}.mp4', 'images': [], 'before': describe(prior), 'after': describe(current),
                      'time': t, 'clip_start': start, 'before_events': prior, 'after_events': current})
        if len(items) >= 6:
            break
    (args.output / 'queue.json').write_text(json.dumps({'items': items, 'selection': 'changed h2 alerts; attack direction confirmed; 3s matching; max 6 separated scenes',
        'evaluation': 'Human review pending; not accuracy evidence'}, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'items': len(items), 'removed_unmatched': len(removed), 'added_unmatched': len(added)}))


if __name__ == '__main__':
    main()
