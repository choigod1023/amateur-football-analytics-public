"""Analyse the logs of scripts/hw_logger.py around unexpected shutdowns (read only).

python scripts/hw_log_analyze.py [--folder work/hwlog] [--window-minutes 10]

For every entry of crash-reports.jsonl it prints the last samples before the computer died (GPU temperature, power, load, CPU load and clock, the busiest processes) and compares the last
window with the normal values of the whole log (median and highest), so that a rise in power or temperature just before the shutdown stands out. With fewer than 3 shutdowns in the log
nothing can be concluded about a cause: the output says so.
"""
import argparse, datetime as dt, json, statistics
from pathlib import Path


def rows(folder):
    out = []
    for path in sorted(Path(folder).glob('hw-*.jsonl')):
        for line in path.read_text(encoding='utf-8').splitlines():
            if line.strip():
                try:
                    out.append(json.loads(line))
                except ValueError:
                    pass
    return out


def number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def summary(items, key):
    values = [number(r['gpu'].get(key)) for r in items if isinstance(r.get('gpu'), dict)]
    values = [v for v in values if v is not None]
    return (round(statistics.median(values), 1), max(values), len(values)) if values else None


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--folder', type=Path, default=Path(__file__).resolve().parents[3] / 'work' / 'hwlog'); p.add_argument('--window-minutes', type=float, default=10.0)
    args = p.parse_args()
    reports_path = args.folder / 'crash-reports.jsonl'
    reports = [json.loads(x) for x in reports_path.read_text(encoding='utf-8').splitlines() if x.strip()] if reports_path.exists() else []
    data = rows(args.folder)
    print(f'{len(data)} samples, {len(reports)} unexpected shutdowns in the log')
    if not data:
        return
    for report in reports:
        last = report['last_sample_before_boot']; end = dt.datetime.fromisoformat(last['time']); start = end - dt.timedelta(minutes=args.window_minutes)
        window = [r for r in data if start <= dt.datetime.fromisoformat(r['time']) <= end]
        print(f"\nShutdown found at boot {report['boot_time']}: last sample {last['time']} ({report['seconds_between_last_sample_and_boot']} s before the boot), {len(window)} samples in the last {args.window_minutes:g} min")
        for key, name in (('temp_c', 'GPU temperature C'), ('power_w', 'GPU power W'), ('util_pct', 'GPU load %'), ('sm_mhz', 'GPU clock MHz')):
            w, a = summary(window, key), summary(data, key)
            if w and a:
                print(f'  {name:18s} last window median {w[0]} max {w[1]} | whole log median {a[0]} max {a[1]}')
        cpu = [r['cpu_pct'] for r in window]
        if cpu:
            print(f"  CPU load % last window median {statistics.median(cpu):.0f} max {max(cpu):.0f} | whole log median {statistics.median([r['cpu_pct'] for r in data]):.0f}")
        print('  last sample: GPU', last['gpu'], '| CPU %', last['cpu_pct'], '| busiest', last['top'])
    if len(reports) < 3:
        print('\nFewer than 3 shutdowns are in the log: this shows what the computer did before them but cannot name a cause.')


if __name__ == '__main__':
    main()
