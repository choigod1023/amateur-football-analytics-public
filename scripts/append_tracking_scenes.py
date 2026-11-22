"""Append localized track conflicts to a new offline queue, never change old labels."""
import argparse
import json
from pathlib import Path
import subprocess
import cv2


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--diagnosis', type=Path, required=True)
    p.add_argument('--queue', type=Path, required=True)
    p.add_argument('--video', type=Path, required=True)
    p.add_argument('--ffmpeg', required=True)
    p.add_argument('--include-structural-conflicts', action='store_true', help='diagnostic preview only; simultaneous separate observations need no repeated same-person question')
    args = p.parse_args()
    queue = json.loads(args.queue.read_text(encoding='utf-8'))
    diagnosis = json.loads(args.diagnosis.read_text(encoding='utf-8'))
    for question in diagnosis['questions']:
        if question['kind'] == 'within_track_conflict' and not args.include_structural_conflicts:
            continue
        ident = f"d{len(queue['items'])+1:04d}"
        t = question['time']
        directory = args.queue.parent
        target = directory / f'{ident}.mp4'
        if target.exists():
            raise ValueError('Refusing to overwrite existing media')
        subprocess.run([args.ffmpeg, '-hide_banner', '-loglevel', 'error', '-ss', str(max(0, t-4)), '-i', str(args.video),
                        '-t', '8', '-an', '-c:v', 'libx264', '-preset', 'fast', '-crf', '20', '-threads', '2',
                        '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(target)], check=True)
        still = directory / f'{ident}-full.jpg'
        subprocess.run([args.ffmpeg, '-hide_banner', '-loglevel', 'error', '-ss', str(t), '-i', str(args.video),
                        '-frames:v', '1', '-q:v', '2', str(still)], check=True)
        frame = cv2.imread(str(still))
        if frame is None:
            raise ValueError('Frame decode failed')
        images = []
        for suffix, box in zip(('a', 'b'), question['boxes']):
            x1,y1,x2,y2 = box
            crop = frame[max(0,int(y1)-12):min(frame.shape[0],int(y2)+12),max(0,int(x1)-12):min(frame.shape[1],int(x2)+12)]
            if not crop.size:
                raise ValueError('Invalid crop')
            name = f'{ident}-{suffix}.jpg'
            cv2.imwrite(str(directory / name), cv2.resize(crop, None, fx=6, fy=6, interpolation=cv2.INTER_NEAREST))
            images.append(name)
        queue['items'].append({'id': ident, 'kind': 'tracking', 'title': f"{question['half']} {int(t//60):02d}:{int(t%60):02d} 조각 내부 충돌",
            'reason': '기존 같은 사람 답은 유지합니다. 이 순간의 두 확대 인물이 같은 사람인지 확인해 주세요. 오탐·심판으로 보이면 메모에 적어 주세요. 이 답은 전체 조각의 기존 답을 덮어쓰지 않습니다.',
            'before': f"조각 {question['a']}와 {question['b']}: 과거 같은 사람으로 답함",
            'after': '동시에 떨어진 위치를 관측해 전체 병합을 보류함',
            'video': target.name, 'images': images, 'time': t, 'source_pair': [question['a'],question['b']], 'half': question['half']})
    args.queue.write_text(json.dumps(queue, ensure_ascii=False, indent=2), encoding='utf-8')
    print('queue_items', len(queue['items']))


if __name__ == '__main__':
    main()
