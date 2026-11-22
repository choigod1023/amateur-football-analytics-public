"""Keep only the newest frame of a live source, so that a slow analysis never builds up a delay.

`LatestFrameQueue` reads the source in its own thread (through app.live_input.ReconnectingReader, which also handles the loss and the return of a stream) and holds ONE frame:
when the analysis takes longer than a frame lasts, the frames in between are thrown away and counted. `get()` gives the newest frame with the moment it was read. The delay of an alert
is the time from that moment to the moment the alert was written; `DelayStats` keeps those numbers for the heartbeat row of alerts.jsonl.
A file is paced at its own frame rate (`pace_fps`), otherwise the thread would read it to the end before the analysis has taken a first frame.
The idea (a reader thread that keeps the latest frame, counts of decoded, delivered and discarded frames) follows an earlier experimental version of this module, rewritten to sit on
the reconnecting reader of this code.
"""
import threading
import time


class DelayStats:
    """Delays in seconds of the last `keep` delivered frames (from the read of the frame to the end of its analysis)."""

    def __init__(self, keep=300):
        self.keep = keep
        self.values = []
        self.count = 0

    def add(self, delay):
        self.count += 1
        self.values.append(max(0.0, float(delay)))
        if len(self.values) > self.keep:
            del self.values[0]

    def summary(self):
        """{'frames': number of frames measured, 'mean_ms', 'p95_ms', 'max_ms'} (None values when nothing was measured yet)."""
        if not self.values:
            return {'frames': self.count, 'mean_ms': None, 'p95_ms': None, 'max_ms': None}
        ordered = sorted(self.values)
        p95 = ordered[min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1))))]
        return {'frames': self.count, 'mean_ms': round(1000 * sum(ordered) / len(ordered)), 'p95_ms': round(1000 * p95), 'max_ms': round(1000 * ordered[-1])}


class LatestFrameQueue:
    def __init__(self, reader, pace_fps=None, clock=time.monotonic, sleep=None):
        """reader: an object with read() -> (ok, frame) and release() (ReconnectingReader or a capture). pace_fps: read no faster than this rate (files)."""
        self.reader, self.pace_fps, self.clock = reader, pace_fps, clock
        self._condition = threading.Condition()
        self._stop = threading.Event()
        self._sleep = sleep or (lambda seconds: self._stop.wait(seconds))
        self._pending = None
        self._ended = False
        self._error = None
        self._decoded = self._delivered = self._discarded = 0
        self._thread = threading.Thread(target=self._run, name='football-latest-frame', daemon=True)
        self._thread.start()

    def _run(self):
        start, number = self.clock(), 0
        try:
            while not self._stop.is_set():
                if self.pace_fps:
                    wait = start + number / self.pace_fps - self.clock()
                    if wait > 0:
                        self._sleep(wait)
                        if self._stop.is_set():
                            break
                ok, frame = self.reader.read()
                taken = self.clock()
                if not ok:
                    break
                number += 1
                with self._condition:
                    self._decoded += 1
                    if self._pending is not None:
                        self._discarded += 1
                    self._pending = (number, frame, taken)
                    self._condition.notify_all()
        except BaseException as error:               # the reader of the source failed in a way it does not handle: the main loop sees it as an end with an error
            self._error = error
        finally:
            with self._condition:
                self._ended = True
                self._condition.notify_all()

    def get(self, timeout=None):
        """(sequence number from 1, frame, moment of the read on this queue's clock), or None when the source has ended and nothing is pending. Raises TimeoutError when nothing came in time."""
        with self._condition:
            if not self._condition.wait_for(lambda: self._pending is not None or self._ended or self._stop.is_set(), timeout):
                raise TimeoutError('no frame arrived in time')
            if self._pending is not None:
                item, self._pending = self._pending, None
                self._delivered += 1
                return item
            return None

    @property
    def ended(self):
        with self._condition:
            return self._ended and self._pending is None

    @property
    def error(self):
        return self._error

    def stats(self):
        with self._condition:
            return {'decoded': self._decoded, 'delivered': self._delivered, 'discarded': self._discarded}

    def close(self, timeout=5.0):
        self._stop.set()
        with self._condition:
            self._condition.notify_all()
        self._thread.join(timeout=timeout)
        try:
            self.reader.release()
        except Exception:
            pass


# ---- Reader (earlier version): a reader that owns an open capture and keeps only the latest frame.
# It is used by scripts/run_live_feedback.py when the capture path of main is chosen; LatestFrameQueue above sits on the reconnecting reader.
import math
import time
from threading import Condition, Event, Thread


class FrameReaderError(RuntimeError):
    """Capture worker failed; the original exception is chained."""


class LatestFrameReader:
    def __init__(self, capture, *, source_fps=None, pace=False, clock=None):
        if pace and (source_fps is None or not math.isfinite(source_fps) or source_fps <= 0):
            raise ValueError('Paced file capture requires a finite positive source_fps')
        self.capture = capture
        self.source_fps = source_fps
        self.pace = pace
        self._clock = clock or time.monotonic
        self._condition = Condition()
        self._stop = Event()
        self._pending = None
        self._ended = False
        self._error = None
        self._decoded = 0
        self._discarded = 0
        self._delivered = 0
        self._worker = Thread(target=self._run, name='football-latest-frame', daemon=True)
        self._worker.start()

    def _pace_wait(self, seconds):
        """Interruptible pacing; overridable for a deterministic test clock."""
        return self._stop.wait(seconds)

    def read(self, timeout=None):
        """Return (one-based source sequence, copied BGR frame, monotonic time).

        None means EOF/cancellation after the last pending frame was drained.
        A timeout and a capture failure are exceptions, never disguised as EOF.
        Captured time is local decode completion, not the camera's exposure time.
        """
        with self._condition:
            ready = self._condition.wait_for(
                lambda: self._pending is not None or self._ended or self._stop.is_set(), timeout)
            if not ready:
                raise TimeoutError('No captured frame arrived before read timeout')
            if self._pending is not None:
                item, self._pending = self._pending, None
                self._delivered += 1
                return item
            if self._error is not None:
                raise FrameReaderError('Capture worker failed') from self._error
            return None

    @property
    def discarded(self):
        with self._condition:
            return self._discarded

    @property
    def stats(self):
        with self._condition:
            return {'decoded': self._decoded, 'delivered': self._delivered,
                    'discarded': self._discarded, 'pending': int(self._pending is not None),
                    'ended': self._ended, 'failed': self._error is not None,
                    'stopping': self._stop.is_set()}

    def close(self, timeout=5.):
        """Stop and wait for worker-owned release; never release during read.

        A blocking decoder cannot safely be released by another thread. On
        timeout the daemon keeps ownership, raises TimeoutError, and releases
        once its read returns. A later close call may finish normally.
        """
        self._stop.set()
        with self._condition:
            self._condition.notify_all()
        self._worker.join(timeout=timeout)
        if self._worker.is_alive():
            raise TimeoutError('Capture read is still blocked; capture was not released concurrently')
        with self._condition:
            if self._error is not None:
                raise FrameReaderError('Capture worker failed') from self._error

    def _run(self):
        epoch = self._clock()
        sequence = 1
        try:
            while not self._stop.is_set():
                if self.pace:
                    delay = epoch + (sequence - 1) / self.source_fps - self._clock()
                    if delay > 0 and self._pace_wait(delay):
                        break
                if self._stop.is_set():
                    break
                ok, frame = self.capture.read()
                captured = self._clock()
                if not ok:
                    break
                # Some capture wrappers reuse their pixel buffer on next read.
                snapshot = (sequence, frame.copy(), captured)
                with self._condition:
                    self._decoded += 1
                    if self._stop.is_set():
                        self._discarded += 1
                        break
                    if self._pending is not None:
                        self._discarded += 1
                    self._pending = snapshot
                    self._condition.notify_all()
                sequence += 1
        except BaseException as exc:
            with self._condition:
                self._error = exc
        finally:
            try:
                self.capture.release()
            except BaseException as exc:
                with self._condition:
                    if self._error is None:
                        self._error = exc
            with self._condition:
                self._ended = True
                self._condition.notify_all()
