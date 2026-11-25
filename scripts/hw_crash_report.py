"""Find the moments the computer stopped writing its state log and show what it did just before (read only).

python scripts/hw_crash_report.py [--logs monitor/logs] [--gap-seconds 60] [--minutes 10]

Reads the CSV files of monitor/log_hw.ps1 (one row about every 5 s: GPU temperature, power, load, clock, throttle reason, CPU load, free memory). A gap longer than --gap-seconds is a stop of the
logger: a normal shutdown, a restart, or a power loss. For each gap the script prints the last row before it, the average and highest values of the last --minutes minutes, and the normal values of
the whole log (median and highest), so a rise before the stop stands out. It cannot tell a normal shutdown from a power loss: compare the gap times with the Windows events (Kernel-Power 41 =
unexpected shutdown; 1074 = shutdown asked by a user or the system; see wiki/hardware-shutdown-1118.md). The log has no CPU temperature and no voltages (HWiNFO is needed for these).
"""
import argparse, csv, datetime as dt, glob, statistics
from pathlib import Path


def num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--logs', type=Path, default=Path(__file__).resolve().parents[3] / 'monitor' / 'logs'); p.add_argument('--gap-seconds', type=float, default=60.0)
    p.add_argument('--minutes', type=float, default=10.0)
    args = p.parse_args()
    rows = []
    for path in sorted(glob.glob(str(args.logs / 'hw_*.csv'))):
        with open(path, encoding='utf-8-sig') as handle:
            for row in csv.DictReader(handle):
                try:
                    row['t'] = dt.datetime.strptime(row['time'], '%Y-%m-%d %H:%M:%S'); rows.append(row)
                except (ValueError, KeyError, TypeError):
                    pass
    rows.sort(key=lambda r: r['t'])
    if not rows:
        print('no rows'); return
    print(f"{len(rows)} rows, {rows[0]['time']} to {rows[-1]['time']}")
    keys = ('gpu_temp_c', 'gpu_power_w', 'gpu_util_pct', 'cpu_util_pct')
    normal = {k: [num(r[k]) for r in rows if num(r[k]) is not None] for k in keys}
    print('whole log (median / highest): ' + ', '.join(f'{k} {statistics.median(v):.1f}/{max(v):.1f}' for k, v in normal.items() if v))
    gaps = [(a, b) for a, b in zip(rows, rows[1:]) if (b['t'] - a['t']).total_seconds() > args.gap_seconds]
    print(f'{len(gaps)} gaps longer than {args.gap_seconds:g} s')
    for a, b in gaps:
        window = [r for r in rows if a['t'] - dt.timedelta(minutes=args.minutes) <= r['t'] <= a['t']]
        def stat(key):
            values = [num(r[key]) for r in window if num(r[key]) is not None]
            return f'{statistics.mean(values):.1f}/{max(values):.1f}' if values else 'NA'
        minutes = (b['t'] - a['t']).total_seconds() / 60
        print(f"{a['time']} -> {b['time']} ({minutes:.0f} min) last row: GPU {a['gpu_temp_c']}C {a['gpu_power_w']}W {a['gpu_util_pct']}% throttle {a['gpu_throttle']}, CPU {a['cpu_util_pct']}% | last {args.minutes:g} min mean/max: "
              + ', '.join(f'{k} {stat(k)}' for k in keys))


if __name__ == '__main__':
    main()
