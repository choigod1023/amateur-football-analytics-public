"""Cut more short ball-labelling clips from the match video and propose ball candidates (the proposals are not detections).

Usage: python scripts/prepare_ball_clips.py <video> <output folder> <first clip number> <camera:second> [<camera:second> ...]
       [--model ball-candidate-experimental.pt] [--ffmpeg ffmpeg] [--seconds 10] [--fps 5]

Each clip gets <output>/clips/bNN/f_001.jpg ... and candidates.json in the format the /ball page reads, and <output>/index_new.json lists
the new clips so a person can add them to the review store's ball/index.json. Candidates that sit at the same place in at least
40 % of the frames of a clip are dropped (lights, windows, line paint). Existing clips are skipped, so a run can be resumed.
"""
import argparse
import json
import subprocess
import time
from pathlib import Path

TOP = {'cam1': 0.70, 'cam3': 0.58, 'cam4': 0.38}            # rows above this are sky, buildings and trees


def window_starts(total, size, overlap):
    values = list(range(0, max(1, total - size + 1), max(1, int(size * (1 - overlap)))))
    if values[-1] != max(0, total - size):
        values.append(max(0, total - size))
    return values


def drop_static(per_frame, share=0.4, tolerance=5):
    """Remove candidates that appear at the same place in at least `share` of the frames."""
    for entry in per_frame:
        entry['cands'] = [c for c in entry['cands']
                          if sum(1 for other in per_frame if any(abs(c[0] - o[0]) < tolerance and abs(c[1] - o[1]) < tolerance for o in other['cands'])) < share * len(per_frame)]
    return per_frame


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('video')
    parser.add_argument('output')
    parser.add_argument('first', type=int)
    parser.add_argument('clips', nargs='+', help='camera:second, for example cam3:1850')
    parser.add_argument('--model', default='ball-candidate-experimental.pt')
    parser.add_argument('--ffmpeg', default='ffmpeg')
    parser.add_argument('--seconds', type=int, default=10)
    parser.add_argument('--fps', type=int, default=5)
    args = parser.parse_args()
    import cv2
    from ultralytics import YOLO
    model = YOLO(args.model)

    def candidates(image, camera):
        height, width = image.shape[:2]
        y0 = int(height * TOP[camera])
        found = []
        for y in [y0 + v for v in window_starts(int(height * 0.95) - y0, 192, 0.25)]:
            for x in window_starts(width, 192, 0.25):
                result = model.predict(image[y:y + 192, x:x + 192], device=0, imgsz=768, conf=0.10, classes=[0], verbose=False)[0]
                if result.boxes is None:
                    continue
                for box, score in zip(result.boxes.xyxy.cpu().numpy(), result.boxes.conf.cpu().numpy()):
                    found.append([float((box[0] + box[2]) / 2 + x), float((box[1] + box[3]) / 2 + y), float(score)])
        found.sort(key=lambda c: -c[2])
        kept = []
        for c in found:
            if all(abs(c[0] - k[0]) > 8 or abs(c[1] - k[1]) > 8 for k in kept):
                kept.append(c)
        return kept

    out = Path(args.output)
    index, started = [], time.time()
    for number, item in enumerate(args.clips, args.first):
        camera, start = item.split(':')
        clip_id, folder = f'b{number:02d}', out / 'clips' / f'b{number:02d}'
        if (folder / 'candidates.json').exists():
            index.append({'id': clip_id, 'camera': camera, 'start': int(start)})
            continue
        folder.mkdir(parents=True, exist_ok=True)
        subprocess.run([args.ffmpeg, '-hide_banner', '-loglevel', 'error', '-y', '-ss', start, '-t', str(args.seconds), '-i', args.video, '-an',
                        '-vf', f'fps={args.fps}', '-q:v', '2', str(folder / 'f_%03d.jpg')], check=True)
        per_frame = [{'file': f.name, 'cands': [[round(a, 1), round(b, 1), round(s, 3)] for a, b, s in candidates(cv2.imread(str(f)), camera)]} for f in sorted(folder.glob('f_*.jpg'))]
        drop_static(per_frame)
        (folder / 'candidates.json').write_text(json.dumps({'id': clip_id, 'camera': camera, 'start': int(start), 'fps': args.fps, 'frames': per_frame}), encoding='utf-8')
        index.append({'id': clip_id, 'camera': camera, 'start': int(start)})
        print(f'{clip_id} {camera} t={start}: {len(per_frame)} frames, {time.time() - started:.0f} s', flush=True)
    (out / 'index_new.json').write_text(json.dumps({'clips': index, 'fps': args.fps, 'seconds': args.seconds}), encoding='utf-8')
    print('done', len(index), 'clips', flush=True)


if __name__ == '__main__':
    main()
