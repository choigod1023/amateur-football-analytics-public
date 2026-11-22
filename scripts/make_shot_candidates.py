"""Candidates for the shot tagging page: every moment in which a team got players into the opponent's box (waves of box entries), for two matches, with a short clip.

python scripts/make_shot_candidates.py --store <review store> --ffmpeg ffmpeg.exe \
    --match 'prev|지난 경기|video.mp4|positions_h1.jsonl|positions_h2.jsonl' --match 'cur|오늘 경기|video_h1.mp4+video_h2.mp4|positions_h1.jsonl|positions_h2.jsonl|1405'

Writes <store>/shots/candidates.json and <store>/shots/clips/<id>.mp4 (6 s before to 8 s after the first entry, 960 px wide). The people marked in the picture are the tracked ones (our view: our goal on
the left). The page only shows these moments to a person who then says what happened; nothing is guessed here. A shot that did not start with a player in the box (a shot from outside) can be missing:
the page lets the reviewer add such a moment by hand.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_detailed_report as R  # noqa: E402


def snapshot(data, t):
    row = data.get(int(round(t)))
    if not row:
        return None
    return {'ours': [[round(u, 1), round(v, 1)] for _, u, v in row['ours']], 'theirs': [[round(u, 1), round(v, 1)] for _, u, v in row['theirs']]}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--store', required=True)
    p.add_argument('--ffmpeg', default='ffmpeg')
    p.add_argument('--match', action='append', required=True, help='key|label|video[+video2]|positions1|positions2[|end of positions2 in seconds]')
    args = p.parse_args()
    root = Path(args.store) / 'shots'
    (root / 'clips').mkdir(parents=True, exist_ok=True)
    items, n = [], 0
    for spec in args.match:
        key, label, videos, p1, p2, *rest = (spec.split('|') + [''])[:6] if spec.count('|') < 5 else spec.split('|')
        end = float(rest[0]) if rest and rest[0] else None
        videos = videos.split('+')
        halves = [('전반', videos[0], p1, None), ('후반', videos[-1], p2, end)]
        for half, video, positions, stop in halves:
            data = R.read(positions, end=stop)
            t0 = min(data)
            for side in ('ours', 'theirs'):
                events = R.entries(data, side, 'box')
                for w in R.waves(events):
                    info = R.wave_info(w, data, side, [])
                    n += 1
                    cid = f's{n:03d}'
                    start = max(0.0, info['t'] - 6)
                    clip = root / 'clips' / (cid + '.mp4')
                    subprocess.run([args.ffmpeg, '-v', 'error', '-y', '-ss', f'{start:.2f}', '-i', video, '-t', '14', '-vf', 'scale=960:-2,fps=15', '-c:v', 'libx264', '-preset', 'fast', '-crf', '27',
                                    '-pix_fmt', 'yuv420p', '-an', '-movflags', '+faststart', str(clip)], check=True)
                    snaps = {str(d): snapshot(data, info['t'] + d) for d in (-2, 0, 2)}
                    items.append({'id': cid, 'match': key, 'match_label': label, 'half': half, 'side': 'ours' if side == 'ours' else 'theirs', 'time': info['t'], 'minute': (info['t'] - t0) / 60.0,
                                  'lane': info['lane'], 'players': info['players'], 'clip': cid + '.mp4', 'clip_start': start, 'snapshots': snaps})
                    print(cid, key, half, side, f'{(info["t"] - t0):.0f}s', flush=True)
    (root / 'candidates.json').write_text(json.dumps({'candidates': items, 'pitch_length': R.L, 'pitch_width': R.W}, ensure_ascii=False), encoding='utf-8')
    print(len(items), 'candidates')


if __name__ == '__main__':
    main()
