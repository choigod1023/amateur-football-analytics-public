"""Read-only free-space warning for a recording process.

Warnings go to the launcher's stderr; they do not delete data or stop streams.
"""
from contextlib import contextmanager
import shutil
import sys
import threading


LOW_SPACE_BYTES = 30 * 1024**3
CHECK_INTERVAL_SECONDS = 60


def report_free_space(directory):
    try:
        free = shutil.disk_usage(directory).free
    except OSError as exc:
        print(f'Recording warning: cannot check free disk space ({exc.__class__.__name__}).', file=sys.stderr, flush=True)
        return
    if free < LOW_SPACE_BYTES:
        print(f'Recording warning: only {free / 1024**3:.1f} GiB free at {directory}; recording can stop if disk fills.', file=sys.stderr, flush=True)


@contextmanager
def watch_free_space(directory):
    stop = threading.Event()
    report_free_space(directory)

    def monitor():
        while not stop.wait(CHECK_INTERVAL_SECONDS):
            report_free_space(directory)

    thread = threading.Thread(target=monitor, name='recording-space-monitor', daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join(timeout=2)
