"""Make ball-labelling clips for the /ball page from the scenes of the detailed report (scenes.json of scripts/make_scene_clips.py).

python scripts/prepare_ball_clips_scenes.py --scenes clips/scenes.json --video-h1 h1.mp4 --video-h2 h2.mp4 --calibrations calibrations.json --camera cam4 \
    --store <review store> --first 55 --ffmpeg ffmpeg.exe [--second-half-offset 1500]

Each clip is 10 s at 5 frames per second around a scene (5 s before to 5 s after), written to <store>/ball/clips/bNN/ with candidates.json in the format of the /ball page.
The circles are proposals from scripts/ball_motion.py (small bright round blobs inside the pitch, static ones dropped); they are not detections, and only a click of the reviewer becomes a label.
The clip numbers are appended to <store>/ball/index.json (a backup of the old index is written first). The "start" of a second half clip is shown with the offset added (25:00 and later) so that
the halves can be told apart in the list.
"""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from app.pitch_map import fit  # noqa: E402
import ball_motion as B  # noqa: E402


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--scenes', required=True)
    p.add_argument('--video-h1', required=True)
    p.add_argument('--video-h2', required=True)
    p.add_argument('--calibrations', required=True)
    p.add_argument('--camera', default='cam4')
    p.add_argument('--store', required=True)
    p.add_argument('--first', type=int, required=True)
    p.add_argument('--ffmpeg', default='ffmpeg')
    p.add_argument('--second-half-offset', type=int, default=1500)
    p.add_argument('--seconds', type=int, default=10)
    args = p.parse_args()
    scenes = json.loads(Path(args.scenes).read_text(encoding='utf-8'))
    fitted = fit(json.loads(Path(args.calibrations).read_text(encoding='utf-8'))[args.camera])
    root = Path(args.store) / 'ball'
    index_path = root / 'index.json'
    index = json.loads(index_path.read_text(encoding='utf-8'))
    if any(c['id'] == f'b{args.first:02d}' for c in index['clips']):
        sys.exit('The first clip number is in the index already.')
    backup = root / f'index.backup-before-b{args.first}.json'
    shutil.copy2(index_path, backup)
    new = []
    for number, sc in enumerate(scenes, args.first):
        video = args.video_h1 if sc['half'] == '전반' else args.video_h2
        start = max(0, int(sc['at']) - args.seconds // 2)
        clip_id = f'b{number:02d}'
        folder = root / 'clips' / clip_id
        folder.mkdir(parents=True, exist_ok=True)
        subprocess.run([args.ffmpeg, '-hide_banner', '-loglevel', 'error', '-y', '-ss', str(start), '-t', str(args.seconds), '-i', video, '-an', '-vf', 'fps=5', '-q:v', '2', str(folder / 'f_%03d.jpg')], check=True)
        files = sorted(folder.glob('f_*.jpg'))
        images = [cv2.imread(str(f)) for f in files]
        frames = B.drop_static(B.candidates(images, B.pitch_mask(images[0].shape, fitted)))
        per_frame = [{'file': f.name, 'cands': [[round(x, 1), round(y, 1), round(s, 3)] for x, y, s in sorted(c, key=lambda a: -a[2])[:25]]} for f, c in zip(files, frames)]
        shown = start + (args.second_half_offset if sc['half'] == '후반' else 0)
        (folder / 'candidates.json').write_text(json.dumps({'id': clip_id, 'camera': args.camera, 'start': shown, 'fps': 5, 'frames': per_frame, 'pick_note': f'{sc["half"]} {sc["kind"]} 장면 (경기 영상 {start}초)'}, ensure_ascii=False), encoding='utf-8')
        new.append({'id': clip_id, 'camera': args.camera, 'start': shown})
        print(clip_id, sc['half'], sc['kind'], f'{len(files)} frames, avg {sum(len(f["cands"]) for f in per_frame) / len(per_frame):.1f} proposals', flush=True)
    index['clips'].extend(new)
    index_path.write_text(json.dumps(index, ensure_ascii=False), encoding='utf-8')
    print('added', len(new), 'clips; index backup:', backup.name)


if __name__ == '__main__':
    main()
