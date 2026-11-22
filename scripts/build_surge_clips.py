"""Cut the moments in which the whole team moved up or fell back (see app/team_tactics.surges) out of the match video, one clip each and one video with all of them.

Usage: python scripts/build_surge_clips.py <output folder> <calibrations.json> <video> <ffmpeg> --half "<same spec as build_match_report.py>" ... [--team B] [--per-half 8] [--before 5] [--after 11]

The clips keep the picture of the recording as it is (original size, no drawings); a small caption in the corner names the half, the time and what the team did. The caption text is
only the time and the direction: 'the team moved up 20 m' or 'the team fell back 17 m'.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from app import team_tactics as tt  # noqa: E402
from build_match_report import clock, load_half  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('output')
    parser.add_argument('calibrations')
    parser.add_argument('video')
    parser.add_argument('ffmpeg')
    parser.add_argument('--half', action='append', required=True)
    parser.add_argument('--team', default='B')
    parser.add_argument('--per-half', type=int, default=8)
    parser.add_argument('--before', type=float, default=5.0)
    parser.add_argument('--after', type=float, default=11.0)
    args = parser.parse_args()
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    calibrations = json.loads(Path(args.calibrations).read_text(encoding='utf-8'))
    other = 'A' if args.team == 'B' else 'B'
    clips, listing = [], []
    for spec in args.half:
        half = load_half(spec, calibrations, args.team)
        series = tt.seconds_series(half['by_frame'], args.team, other, half['direction'], half['fps'], half['result']['frames'])
        top = sorted(sorted(tt.surges(series), key=lambda s: -abs(s[2]))[:args.per_half])
        for second, direction, metres in top:
            start = half['offset'] + second - args.before
            caption = f'{half["name"]} {clock(half["offset"] + second)}  팀이 ' + (f'{abs(metres):.0f}m 밀고 올라감' if direction == 'forward' else f'{abs(metres):.0f}m 물러남')
            name = f'clip_{len(clips) + 1:02d}.mp4'
            textfile = out / f'{name}.txt'
            textfile.write_text(caption, encoding='utf-8')
            fontfile = 'C\\:/Windows/Fonts/malgun.ttf'
            drawtext = (f"drawtext=fontfile='{fontfile}':textfile='{textfile.name}':x=40:y=36:fontsize=34:fontcolor=white:box=1:boxcolor=black@0.55:boxborderw=12")
            subprocess.run([args.ffmpeg, '-hide_banner', '-loglevel', 'error', '-y', '-ss', f'{start:.2f}', '-t', f'{args.before + args.after:.2f}', '-i', args.video, '-vf', drawtext,
                            '-c:v', 'libx264', '-preset', 'medium', '-crf', '18', '-pix_fmt', 'yuv420p', '-r', '30', '-c:a', 'aac', '-b:a', '128k', '-ar', '44100', '-ac', '2', name],
                           check=True, cwd=out)
            textfile.unlink()
            clips.append(name)
            listing.append({'file': name, 'half': half['name'], 'video_second': round(half['offset'] + second, 1), 'direction': direction, 'metres': metres, 'caption': caption})
            print(caption, flush=True)
    (out / 'concat.txt').write_text(''.join(f"file '{c}'\n" for c in clips), encoding='utf-8')
    subprocess.run([args.ffmpeg, '-hide_banner', '-loglevel', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', 'concat.txt', '-c', 'copy', 'surges_all.mp4'], check=True, cwd=out)
    (out / 'clips.json').write_text(json.dumps(listing, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f'{len(clips)} clips and surges_all.mp4 in {out}')


if __name__ == '__main__':
    main()
