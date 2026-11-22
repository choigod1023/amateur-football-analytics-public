"""Run a Python script with a GPU memory cap (started by scripts/gpu_guard.py).

Usage: python scripts/run_capped.py <cap GB> <script.py> [args ...]
The cap makes PyTorch raise an out-of-memory error inside the job instead of letting Windows spill GPU memory into
system RAM (which stalled the PC on 2026-11-20).
"""
import runpy
import sys
from pathlib import Path


def apply_cap(cap_gb):
    try:
        import torch
    except ImportError:
        return None
    if not torch.cuda.is_available():
        return None
    total = torch.cuda.get_device_properties(0).total_memory
    fraction = max(0.05, min(1.0, cap_gb * 2 ** 30 / total))
    torch.cuda.set_per_process_memory_fraction(fraction, 0)
    return fraction


if __name__ == '__main__':
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    fraction = apply_cap(float(sys.argv[1]))
    if fraction is not None:
        print(f'[run_capped] GPU memory cap {float(sys.argv[1]):.1f} GB ({fraction:.0%} of the card)', flush=True)
    script = sys.argv[2]
    sys.argv = sys.argv[2:]
    # same import path as `python script.py`: the script's own folder first
    sys.path[0] = str(Path(script).resolve().parent)
    runpy.run_path(script, run_name='__main__')
