"""Cut a short clip around every scene of the detailed report (the scenes build_detailed_report.py draws) and write scenes.json.

python scripts/make_scene_clips.py --h1 positions_h1.jsonl --h2 positions_h2.jsonl --video-h1 h1.mp4 --video-h2 h2.mp4 --h2-end 1405 --ffmpeg ffmpeg.exe --out-dir clips

The times are seconds of the half videos (the positions files use the same clock). Each clip runs from 6 s before to 8 s after the scene, H.264, 960 px wide, with a still of the scene.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_detailed_report as R  # noqa: E402


def pick(data):
    th, bx = R.entries(data, 'ours', 'third'), R.entries(data, 'ours', 'box')
    oth, obx = R.entries(data, 'theirs', 'third'), R.entries(data, 'theirs', 'box')
    ow = [R.wave_info(w, data, 'ours', [e[0] for e in bx]) for w in R.waves(th)]
    tw = [R.wave_info(w, data, 'theirs', [e[0] for e in obx]) for w in R.waves(oth)]
    scenes = []
    reached = sorted([w for w in ow if w['reached']], key=lambda w: -w['players'])[:2]
    for w in sorted(reached, key=lambda w: w['t']):
        scenes.append({'kind': 'our_attack', 't': w['t'], 'at': w['t'] + 4, 'lane': w['lane'], 'players': w['players']})
    deep = sorted([w for w in tw if w['reached']] or tw, key=lambda w: -w['max_speed'])[:2]
    for w in sorted(deep, key=lambda w: w['t']):
        scenes.append({'kind': 'their_attack', 't': w['t'], 'at': w['t'] + 2, 'lane': w['lane'], 'players': w['players'], 'reached': w['reached']})
    cands = [w for w in ow + tw if R.balanced(data.get(w['t'] + 2, {'ours': [], 'theirs': []}))]
    for w in sorted(cands, key=lambda w: -w['players'])[:1]:
        scenes.append({'kind': 'space', 't': w['t'], 'at': w['t'] + 2, 'lane': w['lane'], 'players': w['players']})
    return scenes


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--h1', required=True)
    p.add_argument('--h2', required=True)
    p.add_argument('--video-h1', required=True)
    p.add_argument('--video-h2', required=True)
    p.add_argument('--h2-end', type=float)
    p.add_argument('--ffmpeg', default='ffmpeg')
    p.add_argument('--out-dir', required=True)
    args = p.parse_args()
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    result = []
    n = 0
    for half, positions, video, end in (('전반', args.h1, args.video_h1, None), ('후반', args.h2, args.video_h2, args.h2_end)):
        data = R.read(positions, end=end)
        for s in pick(data):
            n += 1
            start = max(0.0, s['at'] - 6)
            name = f'scene_{n:02d}_{"h1" if half == "전반" else "h2"}_{s["kind"]}_{int(s["at"]):04d}'
            clip, still = out / (name + '.mp4'), out / (name + '.jpg')
            subprocess.run([args.ffmpeg, '-v', 'error', '-y', '-ss', f'{start:.2f}', '-i', video, '-t', '14', '-vf', 'scale=960:-2,fps=15', '-c:v', 'libx264', '-preset', 'fast', '-crf', '26',
                            '-pix_fmt', 'yuv420p', '-an', '-movflags', '+faststart', str(clip)], check=True)
            subprocess.run([args.ffmpeg, '-v', 'error', '-y', '-ss', f'{s["at"]:.2f}', '-i', video, '-frames:v', '1', '-vf', 'scale=1280:-2', str(still)], check=True)
            result.append({**s, 'half': half, 'name': name, 'start': start, 'clip': clip.name, 'still': still.name})
    (out / 'scenes.json').write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding='utf-8')
    print(len(result), 'scenes ->', out)


if __name__ == '__main__':
    main()
