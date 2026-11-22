"""Cut the first and second half from the match recordings using the analyst's kickoff and whistle tags (/tag).

python scripts/cut_halves_from_tags.py --store <review store> --day 2026-11-20 --out-dir halves [--pad 5] [--small]

Needs the tags 전반 시작, 전반 종료, 후반 시작, 후반 종료 of that day (the last one of each kind counts). Each half is cut from PAD seconds before the kickoff to
PAD seconds after the whistle and written as first_half.mp4 and second_half.mp4 (copied, quick). --small also writes 1280-wide copies without sound that fit a phone message.
A half without both tags is skipped with a message. The times are the server times of the button presses, so a late press moves the cut by that much; check the first seconds.
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import analyst_tags, tag_clips  # noqa: E402


def marks(store, day):
    path = Path(store) / 'analyst-tags' / 'tags.jsonl'
    lines = []
    if path.is_file():
        for line in path.read_text(encoding='utf-8').splitlines():
            try:
                lines.append(json.loads(line))
            except ValueError:
                continue
    out = {}
    for t in analyst_tags.fold(lines).values():
        if t['kind'] in analyst_tags.MARKS and analyst_tags.day_of(t['epoch']) == day:
            out[t['kind']] = t['epoch']                     # the last press of a kind wins
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--store', required=True)
    p.add_argument('--day', required=True)
    p.add_argument('--out-dir', required=True)
    p.add_argument('--recordings', default=str(tag_clips.default_recordings()))
    p.add_argument('--ffmpeg', default=tag_clips.default_ffmpeg())
    p.add_argument('--pad', type=float, default=5.0)
    p.add_argument('--small', action='store_true')
    args = p.parse_args()
    m = marks(args.store, args.day)
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    all_pieces = tag_clips.pieces(args.recordings)
    for half, name in (('h1', 'first_half'), ('h2', 'second_half')):
        start, end = m.get('start_' + half), m.get('end_' + half)
        if not start or not end or end <= start:
            print(f'{name}: start or end tag missing, skipped')
            continue
        parts = tag_clips.spans(all_pieces, start - args.pad, end + args.pad)
        covered = sum(b - a for _, a, b in parts)
        target = out / (name + '.mp4')
        ok = tag_clips.cut(args.ffmpeg, parts, target, timeout=900)
        print(f'{name}: {time.strftime("%H:%M:%S", time.localtime(start))} to {time.strftime("%H:%M:%S", time.localtime(end))}, '
              f'recorded {covered:.0f} of {end - start + 2 * args.pad:.0f} s, {"written " + str(target) if ok else "FAILED"}')
        if ok and args.small:
            small = out / (name + '_small.mp4')
            subprocess.run([args.ffmpeg, '-v', 'error', '-y', '-i', str(target), '-vf', 'scale=1280:-2,fps=25', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '30', '-an', str(small)], check=False)
            print('  small copy', small)


if __name__ == '__main__':
    main()
