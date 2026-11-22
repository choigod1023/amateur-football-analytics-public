"""End-to-end check of a degraded SRT feed: does the live coaching analysis still give the same alerts and team shapes?

One segment of a calibrated match video is
  1. analysed straight from the file (the reference run),
  2. sent over loopback SRT with each degradation profile of scripts/srt_degradation_test.py (bitrate, picture height, SRT latency, packet loss, jitter),
  3. analysed by scripts/run_live_feedback.py from the received stream (a stream with a lower height is scaled back to the calibrated 1920 x 1080 first),
  4. compared with the reference: alerts of the same kind within +-ALERT_WINDOW seconds, and per second the number of players, the centre and the depth of the focus team.
The arrival delay of the transport and the delay of the analysis are added up for the whole way from the camera to the coach screen.
Loopback only: nothing leaves this computer. The match video is one the tracker was developed on, so the absolute alerts are not an accuracy test; the change against the
reference run is what counts here.
"""
import argparse, json, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import srt_degradation_test as transport  # noqa: E402

ALERT_WINDOW = 10.0
SKIP_KINDS = ('heartbeat', 'no_input', 'input_back', 'camera_moved', 'camera_back')
HERE = Path(__file__).resolve().parent


def live_command(python, source, args, out_dir, start, seconds):
    cmd = [python, '-X', 'utf8', str(HERE / 'run_live_feedback.py'), str(source), str(args.calibrations), args.camera, '--direction', str(args.direction), '--team', args.team,
           '--detector', str(args.detector), '--start', str(start), '--seconds', str(seconds), '--alerts', str(out_dir / 'alerts.jsonl'),
           '--positions', str(out_dir / 'positions.jsonl'), '--heartbeat-seconds', '10']
    if args.classifier:
        cmd += ['--classifier', str(args.classifier)]
    if args.reference_bg:
        cmd += ['--reference-bg', *map(str, args.reference_bg)]
    if args.shift:
        cmd += ['--shift', *map(str, args.shift)]
    return cmd


def run_live(python, source, args, out_dir, start, seconds):
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / 'run.log').open('w', encoding='utf-8') as log:
        started = time.time()
        code = subprocess.run(live_command(python, source, args, out_dir, start, seconds), stdout=log, stderr=subprocess.STDOUT).returncode
    return {'exit_code': code, 'wall_seconds': round(time.time() - started)}


def read_alerts(path, offset):
    out = []
    if not Path(path).exists():
        return out
    for line in Path(path).read_text(encoding='utf-8').splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get('type') in SKIP_KINDS or row.get('kind') in SKIP_KINDS:
            continue
        out.append((row.get('kind'), float(row.get('time', 0)) + offset))
    return out


def analysis_delay(path):
    """Mean and 95th percentile delay of the analysis (ms) from the last heartbeat that carries it."""
    last = None
    if not Path(path).exists():
        return None
    for line in Path(path).read_text(encoding='utf-8').splitlines():
        if line.strip():
            row = json.loads(line)
            if row.get('type') == 'heartbeat' and (row.get('stats') or {}).get('delay'):
                last = row['stats']['delay']
    return last


def match_alerts(reference, candidate, window=ALERT_WINDOW):
    """One-to-one matches of the same kind within `window` seconds (closest first)."""
    pairs = sorted((abs(r[1] - c[1]), i, j) for i, r in enumerate(reference) for j, c in enumerate(candidate) if r[0] == c[0] and abs(r[1] - c[1]) <= window)
    used_r, used_c, matched = set(), set(), 0
    for _, i, j in pairs:
        if i in used_r or j in used_c:
            continue
        used_r.add(i); used_c.add(j); matched += 1
    return matched


def shapes(path, offset):
    """{second: (players of the focus team, centre x, centre y, depth x span)} of the focus team from positions.jsonl."""
    out = {}
    if not Path(path).exists():
        return out
    for line in Path(path).read_text(encoding='utf-8').splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get('type') != 'second':
            continue
        team = row['team']
        if not team:
            out[int(row['time'] + offset)] = (0, None, None, None)
            continue
        xs, ys = [p[1] for p in team], [p[2] for p in team]
        out[int(row['time'] + offset)] = (len(team), sum(xs) / len(xs), sum(ys) / len(ys), max(xs) - min(xs))
    return out


def compare_shapes(reference, candidate):
    common = [s for s in reference if s in candidate and reference[s][1] is not None and candidate[s][1] is not None]
    if not common:
        return None
    mean = lambda values: round(sum(values) / len(values), 2)
    return {'seconds_compared': len(common), 'mean_players_reference': mean([reference[s][0] for s in common]), 'mean_players_candidate': mean([candidate[s][0] for s in common]),
            'mean_abs_player_count_difference': mean([abs(reference[s][0] - candidate[s][0]) for s in common]),
            'mean_abs_centre_x_difference_m': mean([abs(reference[s][1] - candidate[s][1]) for s in common]),
            'mean_abs_centre_y_difference_m': mean([abs(reference[s][2] - candidate[s][2]) for s in common]),
            'mean_abs_depth_span_difference_m': mean([abs(reference[s][3] - candidate[s][3]) for s in common])}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('video', type=Path); p.add_argument('calibrations', type=Path); p.add_argument('camera'); p.add_argument('--direction', type=int, choices=(1, -1), required=True)
    p.add_argument('--team', choices=('A', 'B'), default='B'); p.add_argument('--detector', type=Path, required=True); p.add_argument('--classifier', type=Path)
    p.add_argument('--reference-bg', type=float, nargs=4); p.add_argument('--shift', type=float, nargs=2)
    p.add_argument('--ffmpeg', type=Path, required=True); p.add_argument('--python', default=sys.executable)
    p.add_argument('--start', type=float, required=True); p.add_argument('--seconds', type=float, default=300.0)
    p.add_argument('--profiles', nargs='+', required=True, choices=list(transport.PROFILES))
    p.add_argument('--transport-workers', type=int, default=4); p.add_argument('--analysis-workers', type=int, default=3)
    p.add_argument('--work-dir', type=Path, required=True); p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    if '/' in args.python or chr(92) in args.python:
        args.python = str(Path(args.python).resolve())
    args.ffmpeg = args.ffmpeg.resolve()
    args.work_dir.mkdir(parents=True, exist_ok=True)
    results = {'video': args.video.name, 'start_s': args.start, 'seconds': args.seconds, 'camera': args.camera, 'profiles': {}}

    def save():
        args.output.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding='utf-8')

    with ThreadPoolExecutor(max_workers=max(1, args.analysis_workers)) as pool:
        reference_job = pool.submit(run_live, args.python, args.video, args, args.work_dir / 'reference', args.start, args.seconds)

        # 1. transport (several profiles at the same time; each one runs in real time)
        def send(name):
            profile = transport.PROFILES[name]
            out_ts = args.work_dir / f'{name}.ts'
            info = transport.run_transport(args.ffmpeg, args.video, args.start, args.seconds, profile, out_ts, seed=7)
            source = out_ts
            if profile['height'] != 1080:                                   # the calibration clicks are in 1920 x 1080 pixels
                source = args.work_dir / f'{name}_1080.mp4'
                subprocess.run([str(args.ffmpeg), '-hide_banner', '-loglevel', 'error', '-nostdin', '-y', '-i', str(out_ts), '-an', '-vf', 'scale=1920:1080:flags=bicubic',
                                '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '12', '-pix_fmt', 'yuv420p', str(source)], check=False)
            return name, info, source

        sent = []
        with ThreadPoolExecutor(max_workers=max(1, args.transport_workers)) as send_pool:
            futures = []
            for name in args.profiles:
                futures.append(send_pool.submit(send, name)); time.sleep(3)
            for f in futures:
                sent.append(f.result())
                print('sent', sent[-1][0], sent[-1][1].get('arrival_delay'), flush=True)
        # 2. analysis of every received stream (several at the same time)
        jobs = {name: pool.submit(run_live, args.python, source, args, args.work_dir / name, 0.0, args.seconds) for name, _, source in sent}
        reference_run = reference_job.result()
        results['reference'] = reference_run
        reference_alerts = read_alerts(args.work_dir / 'reference' / 'alerts.jsonl', 0.0)
        reference_shapes = shapes(args.work_dir / 'reference' / 'positions.jsonl', 0.0)
        results['reference'].update({'alerts': [(k, round(t, 1)) for k, t in reference_alerts], 'analysis_delay_ms': analysis_delay(args.work_dir / 'reference' / 'alerts.jsonl')})
        print('reference alerts:', results['reference']['alerts'], flush=True)
        for name, info, _ in sent:
            run = jobs[name].result()
            out = args.work_dir / name
            alerts = read_alerts(out / 'alerts.jsonl', args.start)
            matched = match_alerts([(k, t) for k, t in reference_alerts], alerts)
            delay = analysis_delay(out / 'alerts.jsonl')
            arrival = (info.get('arrival_delay') or {}).get('median_s')
            row = {**transport.PROFILES[name], 'live_run': run, 'proxy_data_packets': info['proxy_data_packets'], 'proxy_dropped': info['proxy_dropped'], 'arrival_delay': info['arrival_delay'],
                   'analysis_delay_ms': delay, 'alerts': [(k, round(t, 1)) for k, t in alerts], 'reference_alert_count': len(reference_alerts), 'candidate_alert_count': len(alerts),
                   'matched_alerts': matched, 'alert_recall': round(matched / len(reference_alerts), 3) if reference_alerts else None,
                   'alert_precision': round(matched / len(alerts), 3) if alerts else None,
                   'shape': compare_shapes(reference_shapes, shapes(out / 'positions.jsonl', args.start)),
                   'camera_to_coach_delay_s': round(arrival + (delay or {}).get('mean_ms', 0) / 1000, 2) if arrival is not None else None}
            results['profiles'][name] = row
            save()
            print(name, 'alerts', len(alerts), 'of', len(reference_alerts), 'matched', matched, 'shape', row['shape'], 'delay_s', row['camera_to_coach_delay_s'], flush=True)
    save()


if __name__ == '__main__':
    main()
