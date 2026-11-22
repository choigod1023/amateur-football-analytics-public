"""What did the phone really send? Bitrate, frame rate and gaps of the recorded SRT stream (read only, CPU only).

python scripts/analyze_recorded_stream.py <folder with the recorded .mp4 segments> --ffprobe <ffprobe.exe> [--window 10] [--output result.json]

The server recorded the stream as 10-minute segments (docs/live-recording.md). For every segment the script reads the packet list of the video stream with ffprobe (time, size, key frame flag) and prints:
  * bitrate per window (default 10 s): median, lowest, highest, share of windows under 2000 and 4000 kbps, and the lowest windows with their time;
  * frames per second per window, the longest gap between two frames (a stall of the stream or a dropped part) and how many gaps are longer than 0.2 s;
  * the key frame interval (median, longest).
It measures what arrived at the server after the SRT transport (not what the phone's app displayed). A low bitrate window can mean a calm scene (encoders spend fewer bits) or the phone lowering the
bitrate (adaptive bitrate, weak network); the script cannot tell them apart, it only shows where and how long.
"""
import argparse, json, statistics, subprocess
from pathlib import Path


def packets(ffprobe, path):
    out = subprocess.run([ffprobe, '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'packet=pts_time,size,flags', '-of', 'csv=p=0', str(path)],
                         capture_output=True, text=True, timeout=600).stdout
    rows = []
    for line in out.splitlines():
        parts = line.split(',')
        if len(parts) >= 3 and parts[0] not in ('', 'N/A'):
            try:
                rows.append((float(parts[0]), int(parts[1]), 'K' in parts[2]))
            except ValueError:
                pass
    rows.sort()
    return rows


def analyse(rows, window):
    start = rows[0][0]
    bins = {}
    for t, size, key in rows:
        b = int((t - start) // window)
        entry = bins.setdefault(b, [0, 0])
        entry[0] += size; entry[1] += 1
    windows = [(start + b * window, entry[0] * 8 / window / 1000, entry[1] / window) for b, entry in sorted(bins.items()) if b < max(bins)]    # the last window is partial
    times = [r[0] for r in rows]
    gaps = [b - a for a, b in zip(times, times[1:])]
    keys = [r[0] for r in rows if r[2]]
    key_gaps = [b - a for a, b in zip(keys, keys[1:])]
    kbps = [w[1] for w in windows]
    return {'duration_s': round(times[-1] - times[0], 1), 'frames': len(rows), 'windows': len(windows),
            'kbps_median': round(statistics.median(kbps)), 'kbps_min': round(min(kbps)), 'kbps_max': round(max(kbps)),
            'share_under_2000': round(sum(1 for k in kbps if k < 2000) / len(kbps), 3), 'share_under_4000': round(sum(1 for k in kbps if k < 4000) / len(kbps), 3),
            'fps_median': round(statistics.median([w[2] for w in windows]), 1), 'fps_min': round(min(w[2] for w in windows), 1),
            'longest_gap_s': round(max(gaps), 2), 'gaps_over_0_2s': sum(1 for g in gaps if g > 0.2), 'gaps_over_1s': sum(1 for g in gaps if g > 1.0),
            'key_interval_median_s': round(statistics.median(key_gaps), 2) if key_gaps else None, 'key_interval_max_s': round(max(key_gaps), 2) if key_gaps else None,
            'lowest_windows': [{'at_s': round(w[0] - start), 'kbps': round(w[1]), 'fps': round(w[2], 1)} for w in sorted(windows, key=lambda w: w[1])[:3]]}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('folder', type=Path); p.add_argument('--ffprobe', required=True); p.add_argument('--window', type=float, default=10.0); p.add_argument('--output', type=Path)
    args = p.parse_args()
    result = {}
    for path in sorted(args.folder.glob('*.mp4')):
        rows = packets(args.ffprobe, path)
        if len(rows) < 100:
            continue
        r = analyse(rows, args.window); result[path.name] = r
        print(f"{path.name[:19]} {r['duration_s']:6.0f}s kbps median {r['kbps_median']:5d} min {r['kbps_min']:5d} max {r['kbps_max']:5d} <2000 {r['share_under_2000']:.0%} <4000 {r['share_under_4000']:.0%} "
              f"fps median {r['fps_median']} min {r['fps_min']} longest gap {r['longest_gap_s']}s (>0.2s: {r['gaps_over_0_2s']}, >1s: {r['gaps_over_1s']}) key {r['key_interval_median_s']}/{r['key_interval_max_s']}s "
              f"lowest {[(w['at_s'], w['kbps']) for w in r['lowest_windows']]}", flush=True)
    if args.output:
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding='utf-8')


if __name__ == '__main__':
    main()
