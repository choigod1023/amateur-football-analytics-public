"""Add the known goal moments of the match of 2026-11-11 to the shot candidates (their team is not recorded, the reviewer says it on the /shots page).

python scripts/add_goal_candidates.py --store <review store> --video match.mp4 --positions-h1 p1.jsonl --positions-h2 p2.jsonl --ffmpeg ffmpeg.exe
Goal times (video seconds) are those of wiki/match-facts.md. The candidates from the box-entry waves did not contain most of them (only one of the eight lies within 20 s of a candidate).
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_detailed_report as R  # noqa: E402

GOALS = {'전반': [162, 551, 648], '후반': [2028, 2137, 2397, 2629, 2843]}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--store', required=True)
    p.add_argument('--video', required=True)
    p.add_argument('--positions-h1', required=True)
    p.add_argument('--positions-h2', required=True)
    p.add_argument('--ffmpeg', default='ffmpeg')
    args = p.parse_args()
    root = Path(args.store) / 'shots'
    path = root / 'candidates.json'
    data = json.loads(path.read_text(encoding='utf-8'))
    if any(c.get('goal') for c in data['candidates']):
        sys.exit('The goal moments are in the list already.')
    n = max(int(c['id'][1:]) for c in data['candidates'])
    for half, positions in (('전반', args.positions_h1), ('후반', args.positions_h2)):
        rows = R.read(positions)
        t0 = min(rows)
        for g in GOALS[half]:
            n += 1
            cid = f's{n:03d}'
            start = max(0.0, g - 8)
            subprocess.run([args.ffmpeg, '-v', 'error', '-y', '-ss', f'{start:.2f}', '-i', args.video, '-t', '14', '-vf', 'scale=960:-2,fps=15', '-c:v', 'libx264', '-preset', 'fast', '-crf', '27',
                            '-pix_fmt', 'yuv420p', '-an', '-movflags', '+faststart', str(root / 'clips' / (cid + '.mp4'))], check=True)
            row = rows.get(g)
            snaps = {'0': {'ours': [[round(u, 1), round(v, 1)] for _, u, v in row['ours']], 'theirs': [[round(u, 1), round(v, 1)] for _, u, v in row['theirs']]} if row else None}
            data['candidates'].append({'id': cid, 'match': 'prev', 'match_label': '지난 경기', 'half': half, 'side': 'unknown', 'time': g, 'minute': (g - t0) / 60.0, 'lane': 2, 'players': 0,
                                       'clip': cid + '.mp4', 'clip_start': start, 'snapshots': snaps, 'goal': True})
            print(cid, half, g, flush=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')


if __name__ == '__main__':
    main()
