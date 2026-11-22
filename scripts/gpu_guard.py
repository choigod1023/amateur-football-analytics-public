"""Run one GPU experiment (training or evaluation) under memory limits so the PC does not stall.

Usage:
  python scripts/gpu_guard.py [options] -- <command ...>
  python scripts/gpu_guard.py --check            (only the pre-flight check)

What it does (2026-11-20: three parallel GPU jobs filled the 12 GB card and 99.7% of the 32 GB RAM and the PC stalled):
1. Pre-flight: refuses to start when another guarded job runs (lock file), when the live analysis
   (run_live_feedback.py) runs, or when free VRAM / free RAM is below --vram-need / --ram-need GB.
2. VRAM cap: a Python script command is started through scripts/run_capped.py, which calls
   torch.cuda.set_per_process_memory_fraction so the job fails with an out-of-memory error instead of
   spilling into system RAM. The cap is --vram-cap GB (default 8).
3. Lower priority: the job runs at below-normal priority so live, recording and the server come first.
4. Watchdog: every --interval seconds it reads system RAM and total GPU memory; when RAM use is above
   --ram-kill % or GPU memory above --vram-kill % for two readings in a row, it stops the job and its children.
5. Record: peaks, duration, exit code and stop reason are appended to work/gpu-guard/runs.jsonl
   (one JSON line per run) and printed at the end.
Exit code: the job's own code, 98 when the pre-flight refused, 99 when the watchdog stopped the job.
"""
import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT.parents[1] / 'work'
LIVE_MARKERS = ('run_live_feedback',)


def gpu_memory():
    """(used MB, total MB) of GPU 0 from nvidia-smi, or None when it cannot be read."""
    try:
        out = subprocess.run(['nvidia-smi', '--query-gpu=memory.used,memory.total', '--format=csv,noheader,nounits'],
                             capture_output=True, text=True, timeout=10).stdout.strip().splitlines()[0]
        used, total = (float(x) for x in out.split(','))
        return used, total
    except Exception:
        return None


def live_running(processes=None):
    for p in processes if processes is not None else psutil.process_iter(['cmdline']):
        try:
            line = ' '.join(p.info.get('cmdline') or [])
        except Exception:
            continue
        if any(m in line for m in LIVE_MARKERS) and 'gpu_guard' not in line:
            return True
    return False


def preflight(gpu, ram_available_mb, live, locked, vram_need_gb, ram_need_gb, allow_live=False):
    """Return a list of reasons not to start (empty = may start)."""
    reasons = []
    if locked:
        reasons.append('another guarded GPU job is running (one GPU job at a time)')
    if live and not allow_live:
        reasons.append('the live analysis is running (no GPU experiments during a match)')
    if gpu is None:
        reasons.append('cannot read GPU memory (nvidia-smi)')
    elif (gpu[1] - gpu[0]) < vram_need_gb * 1024:
        reasons.append(f'free GPU memory {(gpu[1] - gpu[0]) / 1024:.1f} GB < {vram_need_gb} GB')
    if ram_available_mb < ram_need_gb * 1024:
        reasons.append(f'free RAM {ram_available_mb / 1024:.1f} GB < {ram_need_gb} GB')
    return reasons


class Watchdog:
    """Stop decision: limit exceeded in `strikes` readings in a row."""

    def __init__(self, ram_kill, vram_kill, strikes=2):
        self.ram_kill, self.vram_kill, self.strikes = ram_kill, vram_kill, strikes
        self.count = 0

    def check(self, ram_percent, vram_percent):
        over = []
        if ram_percent > self.ram_kill:
            over.append(f'RAM {ram_percent:.1f}% > {self.ram_kill}%')
        if vram_percent is not None and vram_percent > self.vram_kill:
            over.append(f'GPU memory {vram_percent:.1f}% > {self.vram_kill}%')
        self.count = self.count + 1 if over else 0
        return '; '.join(over) if self.count >= self.strikes else None


def wrap_command(command, vram_cap_gb):
    """Start `python script.py ...` through run_capped.py so the VRAM cap applies; other commands are left as they are."""
    if not command or not Path(command[0]).name.lower().startswith('python'):
        return command
    # interpreter options such as -X utf8 stay in front of the script
    i = next((k for k, c in enumerate(command[1:], 1) if c.endswith('.py')), None)
    if i is None or any(c in ('-m', '-c') for c in command[1:i]):
        return command
    return [*command[:i], str(ROOT / 'scripts' / 'run_capped.py'), str(vram_cap_gb), *command[i:]]


def stop_tree(pid):
    try:
        parent = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return
    children = parent.children(recursive=True)
    for p in [*children, parent]:
        try:
            p.kill()
        except psutil.NoSuchProcess:
            pass


def tree_rss_mb(pid):
    try:
        parent = psutil.Process(pid)
        return sum(p.memory_info().rss for p in [parent, *parent.children(recursive=True)]) / 2 ** 20
    except psutil.NoSuchProcess:
        return 0.0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--vram-need', type=float, default=8, help='GB of free GPU memory needed to start')
    parser.add_argument('--ram-need', type=float, default=12, help='GB of free RAM needed to start')
    parser.add_argument('--vram-cap', type=float, default=8, help='GB the job may allocate (Python jobs)')
    parser.add_argument('--ram-kill', type=float, default=90, help='stop the job above this system RAM %%')
    parser.add_argument('--vram-kill', type=float, default=95, help='stop the job above this GPU memory %%')
    parser.add_argument('--interval', type=float, default=2.0)
    parser.add_argument('--allow-live', action='store_true', help='start even while the live analysis runs (not on match days)')
    parser.add_argument('--log', default=str(WORK / 'gpu-guard' / 'runs.jsonl'))
    parser.add_argument('--name', default='')
    parser.add_argument('--check', action='store_true', help='only run the pre-flight check')
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = args.command[1:] if args.command[:1] == ['--'] else args.command

    lock = Path(args.log).parent / 'running.lock'
    locked = False
    if lock.exists():
        try:
            locked = psutil.pid_exists(int(lock.read_text().split()[0]))
        except Exception:
            locked = False
    gpu = gpu_memory()
    ram = psutil.virtual_memory()
    reasons = preflight(gpu, ram.available / 2 ** 20, live_running(), locked, args.vram_need, args.ram_need, args.allow_live)
    state = f'GPU memory free {(gpu[1] - gpu[0]) / 1024:.1f}/{gpu[1] / 1024:.1f} GB, ' if gpu else ''
    print(f'[gpu_guard] {state}RAM free {ram.available / 2 ** 30:.1f}/{ram.total / 2 ** 30:.1f} GB', flush=True)
    if reasons:
        print('[gpu_guard] not starting: ' + '; '.join(reasons), flush=True)
        return 98
    if args.check:
        print('[gpu_guard] ok to start', flush=True)
        return 0
    if not command:
        parser.error('give the command after --')

    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(f'{os.getpid()} {datetime.now().isoformat(timespec="seconds")}')
    wrapped = wrap_command(command, args.vram_cap)
    env = dict(os.environ, PYTORCH_CUDA_ALLOC_CONF=os.environ.get('PYTORCH_CUDA_ALLOC_CONF', 'expandable_segments:True'))
    flags = getattr(subprocess, 'BELOW_NORMAL_PRIORITY_CLASS', 0)
    start = time.time()
    job = subprocess.Popen(wrapped, env=env, creationflags=flags)
    dog = Watchdog(args.ram_kill, args.vram_kill)
    peak = {'ram_percent': 0.0, 'job_rss_mb': 0.0, 'gpu_used_mb': 0.0}
    stopped = None
    try:
        while job.poll() is None:
            time.sleep(args.interval)
            ram_percent = psutil.virtual_memory().percent
            g = gpu_memory()
            vram_percent = 100 * g[0] / g[1] if g else None
            peak['ram_percent'] = max(peak['ram_percent'], ram_percent)
            peak['job_rss_mb'] = max(peak['job_rss_mb'], tree_rss_mb(job.pid))
            if g:
                peak['gpu_used_mb'] = max(peak['gpu_used_mb'], g[0])
            stopped = dog.check(ram_percent, vram_percent)
            if stopped:
                print(f'[gpu_guard] stopping the job: {stopped}', flush=True)
                stop_tree(job.pid)
                break
        job.wait()
    except KeyboardInterrupt:
        stopped = 'stopped by the user (Ctrl+C)'
        stop_tree(job.pid)
    finally:
        lock.unlink(missing_ok=True)
    code = 99 if stopped and not stopped.startswith('stopped by the user') else job.returncode
    record = {'time': datetime.now().isoformat(timespec='seconds'), 'name': args.name, 'command': command,
              'seconds': round(time.time() - start), 'exit': code, 'stopped': stopped,
              'peak_ram_percent': round(peak['ram_percent'], 1), 'peak_job_rss_gb': round(peak['job_rss_mb'] / 1024, 2),
              'peak_gpu_used_gb': round(peak['gpu_used_mb'] / 1024, 2), 'vram_cap_gb': args.vram_cap}
    Path(args.log).parent.mkdir(parents=True, exist_ok=True)
    with open(args.log, 'a', encoding='utf-8') as f:
        f.write(json.dumps(record, ensure_ascii=False) + '\n')
    print('[gpu_guard] ' + json.dumps(record, ensure_ascii=False), flush=True)
    return code


if __name__ == '__main__':
    sys.exit(main())
