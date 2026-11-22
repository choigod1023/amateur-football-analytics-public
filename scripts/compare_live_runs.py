"""Compare live runs of two detectors on the same segments (research, read only).

python scripts/compare_live_runs.py <folder with <model>/positions_<seg>.jsonl, alerts_<seg>.jsonl, run_<seg>.log> <model A> <model B> <segment> [<segment> ...]

Per segment and model: analysed seconds, mean players of team B and of the other team (after the 1 s hold and merge of app/live_feedback.py), seconds with 2 or more of team B in the box
of the attacked goal, alerts by kind with their video seconds (heartbeat and input rows left out), and the speed of the run (video seconds per wall second, read from the run log if printed).
"""
import json
import re
import sys
from pathlib import Path

DIRECTION = {'s1': -1, 's2': -1, 's3': 1}
BOX_DEPTH, BOX_HALF_WIDTH, HALF_LENGTH = 16.5, 20.16, 44.5


def positions(path, direction):
    rows = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
    seconds = [r for r in rows if r.get('type') == 'second']
    team = [len(r['team']) for r in seconds]
    other = [len(r['other']) for r in seconds]
    in_box = {}
    for r in seconds:
        n = sum(1 for _, x, y in r['team'] if x * direction > HALF_LENGTH - BOX_DEPTH and abs(y) < BOX_HALF_WIDTH)
        if n >= 2:
            in_box[int(r['time'])] = n
    return {'seconds': len(seconds), 'team_mean': sum(team) / max(1, len(team)), 'other_mean': sum(other) / max(1, len(other)),
            'team_ge8': sum(1 for n in team if n >= 8) / max(1, len(team)), 'box_seconds': in_box}


def alerts(path):
    out = []
    for line in path.read_text(encoding='utf-8').splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get('type') in ('heartbeat', 'no_input', 'input_back', 'camera_moved', 'camera_back') or row.get('kind') in ('heartbeat', 'no_input', 'input_back', 'camera_moved', 'camera_back'):
            continue
        out.append((row.get('kind'), round(float(row.get('time', 0)))))
    return out


def speed(path):
    text = path.read_text(encoding='utf-8', errors='replace')
    found = re.findall(r'(\d+(?:\.\d+)?)\s*x\s*real', text) or re.findall(r'real[- ]?time[^0-9]*(\d+(?:\.\d+)?)', text)
    return found[-1] if found else None


def main():
    folder, a, b, segments = Path(sys.argv[1]), sys.argv[2], sys.argv[3], sys.argv[4:]
    for seg in segments:
        print(f'== {seg}')
        for model in (a, b):
            d = folder / model
            p = positions(d / f'positions_{seg}.jsonl', DIRECTION[seg])
            al = alerts(d / f'alerts_{seg}.jsonl')
            kinds = {}
            for kind, t in al:
                kinds.setdefault(kind, []).append(t)
            print(f"{model:10s} seconds {p['seconds']}, team B mean {p['team_mean']:.2f} (>=8 players in {p['team_ge8'] * 100:.0f}% of seconds), other mean {p['other_mean']:.2f}, "
                  f"seconds with >=2 of B in the box {len(p['box_seconds'])} {sorted(p['box_seconds'])[:12]}, alerts {len(al)}, speed {speed(d / f'run_{seg}.log')}")
            for kind, times in sorted(kinds.items()):
                print(f'    {kind}: {times}')


if __name__ == '__main__':
    main()
