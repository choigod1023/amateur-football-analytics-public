"""Read the sensor log of HWiNFO and show what the computer measured just before the log stopped (read only).

python scripts/hwinfo_log_report.py [--folder <HWiNFO log folder>] [--gap-seconds 30] [--rows 15]

HWiNFO writes one CSV row every few seconds (Date, Time and about 390 sensor columns, no filter). The script reads the main rails and temperatures by their column names:
  +12V, +5V, +3.3V, 3VSB (standby power: it is what keeps the board and the wake-on-LAN alive), VBAT, Vcore, CPU temperature (Tctl/Tdie), VRM MOS temperature, GPU 12VHPWR voltage and power.
It prints (1) the lowest, mean and highest value of each of them over the log, (2) the moments a rail left the ATX tolerance of +-5 % (12 V: 11.4 to 12.6, 5 V: 4.75 to 5.25, 3.3 V: 3.135 to 3.465),
(3) for every gap longer than --gap-seconds (the log stopped: the computer was switched off, restarted or lost power) the last --rows rows before the gap.
The voltages come from the sensor chip of the main board, are not exact, and a sag that lasts less than the logging interval is not seen. A rail that falls before the computer dies is a strong sign of a
power supply problem; a rail that stays steady until the last row does not clear the power supply (the failure can be faster than the interval).
"""
import argparse, csv, datetime as dt, glob, statistics
from pathlib import Path

COLUMNS = {'12V': '+12V [V]', '5V': '+5V [V]', '3.3V': '+3.3V [V]', '3VSB': '3VSB [V]', 'VBAT': 'VBAT [V]', 'Vcore': 'Vcore [V]', 'CPU C': 'CPU (Tctl/Tdie) [°C]',
           'VRM C': 'VRM MOS [°C]', 'GPU 12V': 'GPU 12VHPWR 전압 [V]', 'GPU W': 'GPU 12VHPWR 전력 소비 [W]'}
LIMITS = {'12V': (11.4, 12.6), '5V': (4.75, 5.25), '3.3V': (3.135, 3.465), '3VSB': (3.135, 3.465)}


def read(folder):
    rows, header = [], None
    for path in sorted(glob.glob(str(Path(folder) / '*.csv')) + glob.glob(str(Path(folder) / '*.CSV'))):
        for encoding in ('utf-8-sig', 'cp949'):
            try:
                with open(path, encoding=encoding, newline='') as handle:
                    table = list(csv.reader(handle))
                break
            except UnicodeDecodeError:
                continue
        else:
            continue
        head = table[0]
        index = {name: head.index(col) for name, col in COLUMNS.items() if col in head}
        for line in table[1:]:
            try:
                day, month, year = line[0].split('.')
                hour, minute, second = line[1].split(':')
                t = dt.datetime(int(year), int(month), int(day), int(hour), int(minute), int(float(second)), int((float(second) % 1) * 1e6))
            except (ValueError, IndexError):
                continue
            row = {'t': t}
            for name, i in index.items():
                try:
                    row[name] = float(line[i])
                except (ValueError, IndexError):
                    row[name] = None
            rows.append(row)
        header = header or index
    rows.sort(key=lambda r: r['t'])
    return rows, header


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--folder', default=str(Path.home() / 'Desktop' / 'comlog')); p.add_argument('--gap-seconds', type=float, default=30.0); p.add_argument('--rows', type=int, default=15)
    args = p.parse_args()
    rows, index = read(args.folder)
    if not rows:
        print('no rows'); return
    span = (rows[-1]['t'] - rows[0]['t']).total_seconds()
    print(f"{len(rows)} rows, {rows[0]['t']:%Y-%m-%d %H:%M:%S} to {rows[-1]['t']:%Y-%m-%d %H:%M:%S} ({span / 3600:.2f} h), columns found: {', '.join(index)}")
    for name in index:
        values = [r[name] for r in rows if r[name] is not None]
        if values:
            print(f'  {name:8s} min {min(values):8.3f} mean {statistics.mean(values):8.3f} max {max(values):8.3f}')
    for name, (low, high) in LIMITS.items():
        out = [r for r in rows if r.get(name) is not None and not (low <= r[name] <= high)]
        print(f"  {name} outside {low} to {high} V: {len(out)} rows" + (f", first {out[0]['t']:%H:%M:%S} value {out[0][name]}" if out else ''))
    gaps = [(a, b) for a, b in zip(rows, rows[1:]) if (b['t'] - a['t']).total_seconds() > args.gap_seconds]
    print(f'{len(gaps)} gaps longer than {args.gap_seconds:g} s')
    for a, b in gaps:
        print(f"gap {a['t']:%Y-%m-%d %H:%M:%S} -> {b['t']:%Y-%m-%d %H:%M:%S} ({(b['t'] - a['t']).total_seconds() / 60:.1f} min); last rows before it:")
        for r in [x for x in rows if x['t'] <= a['t']][-args.rows:]:
            print('   ' + f"{r['t']:%H:%M:%S} " + ' '.join(f'{n}={r[n]}' for n in index if r[n] is not None))


if __name__ == '__main__':
    main()
