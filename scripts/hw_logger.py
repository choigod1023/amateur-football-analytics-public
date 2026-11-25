"""Write the hardware state of this computer to a log every few seconds, so that the last values before an unexpected shutdown survive.

python scripts/hw_logger.py [--folder work/hwlog] [--interval 5] [--keep-days 30] [--once]

* One JSON line per sample in <folder>/hw-YYYYMMDD.jsonl. Every line is flushed and fsynced, so a power loss costs at most one interval.
* Fields: wall time, uptime, CPU load and clock, memory, disk free (C:), GPU temperature, power, load, memory, clocks, fan and the reasons the GPU slowed down (nvidia-smi), the five processes
  that used the most CPU. CPU temperature and fan speeds of the main board are NOT read: Windows does not give them without a sensor driver (see wiki/hardware-shutdown-1118.md).
* At start the script looks for the previous run: when the last line of the last log is older than the Windows boot time and the System log holds an unexpected-shutdown event
  (Kernel-Power 41), it writes one line to <folder>/crash-reports.jsonl with the last sample (what the computer did just before it died).
* It only reads the computer state and writes inside <folder>. It does not change any setting and does not touch the review server or the analysis.
"""
import argparse, datetime as dt, json, os, subprocess, sys, time
from pathlib import Path

import psutil

GPU_FIELDS = ['temperature.gpu', 'power.draw', 'power.limit', 'utilization.gpu', 'utilization.memory', 'memory.used', 'clocks.sm', 'clocks.mem', 'fan.speed',
              'clocks_throttle_reasons.active']


def gpu_sample():
    try:
        out = subprocess.run(['nvidia-smi', '--query-gpu=' + ','.join(GPU_FIELDS), '--format=csv,noheader,nounits'], capture_output=True, text=True, timeout=10).stdout.strip().splitlines()
    except Exception as error:
        return {'error': str(error)[:80]}
    if not out:
        return {'error': 'no output'}
    values = [v.strip() for v in out[0].split(',')]
    return dict(zip(['temp_c', 'power_w', 'power_limit_w', 'util_pct', 'mem_util_pct', 'mem_used_mib', 'sm_mhz', 'mem_mhz', 'fan_pct', 'throttle'], values))


def sample():
    boot = psutil.boot_time()
    top = sorted(((p.info['cpu_percent'] or 0, p.info['name']) for p in psutil.process_iter(['name', 'cpu_percent']) if p.info['name'] != 'System Idle Process'), reverse=True)[:5]
    freq = psutil.cpu_freq()
    return {'time': dt.datetime.now().isoformat(timespec='seconds'), 'uptime_s': int(time.time() - boot), 'cpu_pct': psutil.cpu_percent(), 'cpu_mhz': int(freq.current) if freq else None,
            'ram_pct': psutil.virtual_memory().percent, 'disk_free_gb': round(psutil.disk_usage('C:\\').free / 1e9, 1), 'gpu': gpu_sample(), 'top': [f'{n}:{c:.0f}' for c, n in top]}


def last_line(path):
    try:
        with open(path, 'rb') as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - 4096))
            lines = f.read().decode('utf-8', 'ignore').strip().splitlines()
        return json.loads(lines[-1]) if lines else None
    except Exception:
        return None


def unexpected_shutdowns():
    """Times (ISO text) of the most recent Kernel-Power 41 events."""
    try:
        text = subprocess.run(['wevtutil', 'qe', 'System', '/q:*[System[Provider[@Name="Microsoft-Windows-Kernel-Power"] and (EventID=41)]]', '/c:5', '/rd:true', '/f:text'],
                              capture_output=True, text=True, timeout=30, encoding='utf-8', errors='ignore').stdout
    except Exception:
        return []
    return [line.split(':', 1)[1].strip() for line in text.splitlines() if line.strip().startswith('Date:')]


def check_previous(folder):
    files = sorted(Path(folder).glob('hw-*.jsonl'))
    if not files:
        return
    last = last_line(files[-1])
    if not last:
        return
    boot = dt.datetime.fromtimestamp(psutil.boot_time())
    seen = dt.datetime.fromisoformat(last['time'])
    if seen >= boot:
        return
    report = {'detected_at': dt.datetime.now().isoformat(timespec='seconds'), 'boot_time': boot.isoformat(timespec='seconds'), 'last_sample_before_boot': last,
              'seconds_between_last_sample_and_boot': int((boot - seen).total_seconds()), 'recent_kernel_power_41': unexpected_shutdowns()[:3],
              'note': 'The last sample was written before this boot and no clean shutdown is known; a Kernel-Power 41 event close to the boot time means the computer lost power or hung.'}
    with open(Path(folder) / 'crash-reports.jsonl', 'a', encoding='utf-8') as f:
        f.write(json.dumps(report, ensure_ascii=False) + '\n')


def prune(folder, days):
    limit = time.time() - days * 86400
    for path in Path(folder).glob('hw-*.jsonl'):
        if path.stat().st_mtime < limit:
            path.unlink()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--folder', type=Path, default=Path(__file__).resolve().parents[3] / 'work' / 'hwlog'); p.add_argument('--interval', type=float, default=5.0)
    p.add_argument('--keep-days', type=int, default=30); p.add_argument('--once', action='store_true', help='write one sample and stop (a quick test)')
    args = p.parse_args()
    args.folder.mkdir(parents=True, exist_ok=True)
    check_previous(args.folder)
    prune(args.folder, args.keep_days)
    psutil.cpu_percent()
    while True:
        row = sample()
        path = args.folder / f'hw-{row["time"][:10].replace("-", "")}.jsonl'
        with open(path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(row, ensure_ascii=False) + '\n'); f.flush(); os.fsync(f.fileno())
        if args.once:
            print(json.dumps(row, ensure_ascii=False)); return
        time.sleep(args.interval)


if __name__ == '__main__':
    main()
