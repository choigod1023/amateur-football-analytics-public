import threading
import time

import pytest

from app.latest_frame import DelayStats, LatestFrameQueue
from app.live_input import ReconnectingReader, heartbeat_record, status_record


class GatedReader:
    """A source that gives one frame each time the test lets it: the test decides how fast frames arrive, no real time is involved."""

    def __init__(self, total):
        self.total, self.given = total, 0
        self.gate = threading.Semaphore(0)
        self.released = False

    def read(self):
        self.gate.acquire()
        if self.given >= self.total:
            return False, None
        self.given += 1
        return True, f'frame{self.given}'

    def release(self):
        self.released = True


def wait_for(condition, seconds=3.0):
    end = time.time() + seconds
    while time.time() < end:
        if condition():
            return True
        time.sleep(0.002)
    return False


def test_a_slow_consumer_always_gets_the_newest_frame_and_the_rest_is_counted():
    reader = GatedReader(total=6)
    queue = LatestFrameQueue(reader)
    for _ in range(5):                                           # five frames arrive while the analysis is busy
        reader.gate.release()
    assert wait_for(lambda: queue.stats()['decoded'] == 5)
    number, frame, _ = queue.get(timeout=1)
    assert (number, frame) == (5, 'frame5')                      # not frame1: no backlog
    assert queue.stats() == {'decoded': 5, 'delivered': 1, 'discarded': 4}
    reader.gate.release()                                        # the next frame
    assert queue.get(timeout=1)[:2] == (6, 'frame6')
    reader.gate.release()                                        # the source ends
    assert wait_for(lambda: queue.ended)
    assert queue.get(timeout=1) is None
    queue.close()
    assert reader.released


def test_get_raises_when_nothing_arrives_in_time():
    reader = GatedReader(total=1)
    queue = LatestFrameQueue(reader)
    with pytest.raises(TimeoutError):
        queue.get(timeout=0.05)
    reader.gate.release()
    reader.gate.release()
    queue.close()


def test_the_delay_stays_bounded_when_the_analysis_is_slower_than_the_source():
    """A source of 200 frames, an analysis that takes 20 ms per frame while a frame arrives every 2 ms: without the queue the 100th frame would wait about 1.8 s."""
    class FastReader:
        def __init__(self):
            self.n = 0

        def read(self):
            time.sleep(0.002)
            self.n += 1
            return (True, self.n) if self.n <= 200 else (False, None)

        def release(self):
            pass
    queue = LatestFrameQueue(FastReader())
    delays, seen = DelayStats(), []
    while True:
        item = queue.get(timeout=2)
        if item is None:
            break
        number, _frame, taken = item
        time.sleep(0.02)
        delays.add(time.monotonic() - taken)
        seen.append(number)
    queue.close()
    stats = queue.stats()
    assert stats['discarded'] > 100 and stats['decoded'] == 200 and seen == sorted(seen)
    assert delays.summary()['max_ms'] < 250                      # one analysis plus one frame interval, with a wide margin for a busy test machine


def test_a_file_is_paced_at_its_frame_rate():
    class FileReader:
        def __init__(self):
            self.n = 0

        def read(self):
            self.n += 1
            return (True, self.n) if self.n <= 6 else (False, None)

        def release(self):
            pass
    start = time.monotonic()
    queue = LatestFrameQueue(FileReader(), pace_fps=50)
    numbers = []
    while True:
        item = queue.get(timeout=2)
        if item is None:
            break
        numbers.append(item[0])
    queue.close()
    assert time.monotonic() - start >= 0.08                      # 6 frames at 50 fps take at least 5 x 20 ms; without pacing they would be read at once
    assert numbers[-1] == 6


def test_a_lost_stream_is_opened_again_behind_the_queue_and_the_loss_is_reported():
    events = []

    class Capture:
        def __init__(self, frames):
            self.frames = list(frames)

        def read(self):
            return (True, self.frames.pop(0)) if self.frames else (False, None)

        def release(self):
            pass
    captures = [Capture(['a']), Capture(['b', 'c'])]
    reader = ReconnectingReader(lambda: captures.pop(0), is_file=False, max_retries=3, notify=lambda kind, text: events.append(kind), sleep=lambda s: None)
    queue = LatestFrameQueue(reader)
    got = []
    while True:
        item = queue.get(timeout=2)
        if item is None:
            break
        got.append(item[1])
    queue.close()
    assert got[-1] == 'c' and set(got) <= {'a', 'b', 'c'}        # frames in between may be dropped, the newest one arrives
    assert events[0] == 'no_input' and 'input_back' in events    # the loss after 'a' and the return with 'b'
    assert reader.gave_up                                        # the source is gone for good after 'c': the run ends instead of waiting for ever


def test_delay_summary():
    stats = DelayStats()
    assert stats.summary() == {'frames': 0, 'mean_ms': None, 'p95_ms': None, 'max_ms': None}
    for value in (0.1, 0.2, 0.3):
        stats.add(value)
    summary = stats.summary()
    assert summary['frames'] == 3 and summary['mean_ms'] == 200 and summary['max_ms'] == 300


def test_heartbeat_and_camera_rows_are_status_rows_and_are_not_rated_as_alerts():
    row = heartbeat_record(12.34, {'delay': {'frames': 3}, 'camera': 'ok'})
    assert row['kind'] == 'heartbeat' and row['type'] == 'heartbeat' and row['polarity'] == 'status' and row['stats']['camera'] == 'ok'
    for kind in ('camera_moved', 'camera_back'):
        record = status_record(kind, 5.0)
        assert record['polarity'] == 'status' and record['title'] and record['text']


# ---- Tests of LatestFrameReader
from threading import Event
import numpy as np
import pytest
from app.latest_frame import LatestFrameReader, FrameReaderError


class Capture:
    def __init__(self, count=3, clock=None):
        self.count, self.index = count, 0
        self.buffer = np.zeros((4, 4, 3), np.uint8)
        self.released = Event()
        self.read_times = []
        self.clock = clock

    def read(self):
        if self.clock:
            self.read_times.append(self.clock())
        if self.index >= self.count:
            self.buffer[:] = 255
            return False, None
        self.buffer[:] = self.index
        self.index += 1
        return True, self.buffer

    def release(self):
        self.released.set()


def test_latest_frame_sequence_time_and_eof_drain_are_coherent():
    capture = Capture(3)
    reader = LatestFrameReader(capture)
    assert capture.released.wait(2)
    sequence, frame, captured = reader.read(timeout=1)
    assert sequence == 3 and np.all(frame == 2) and captured > 0
    assert reader.discarded == 2
    assert reader.read(timeout=1) is None
    assert reader.stats == {'decoded': 3, 'delivered': 1, 'discarded': 2,
                            'pending': 0, 'ended': True, 'failed': False, 'stopping': False}
    reader.close()


def test_pacing_uses_source_sequence_timestamps_with_fake_clock():
    class Clock:
        now = 100.
        def __call__(self):return self.now
    clock = Clock()
    class PacedReader(LatestFrameReader):
        def _pace_wait(self, seconds):
            clock.now += seconds
            return False
    capture = Capture(3, clock)
    reader = PacedReader(capture, source_fps=10., pace=True, clock=clock)
    assert capture.released.wait(2)
    assert capture.read_times == pytest.approx([100., 100.1, 100.2, 100.3])
    sequence, frame, captured = reader.read()
    assert sequence == 3 and captured == pytest.approx(100.2)
    assert np.all(frame == 2)
    reader.close()


def test_blocking_read_timeout_and_close_never_release_concurrently():
    class BlockedCapture(Capture):
        def __init__(self):
            super().__init__(1); self.entered = Event(); self.allow = Event(); self.in_read = False
        def read(self):
            self.in_read = True; self.entered.set()
            if not self.allow.wait(5):raise TimeoutError('Test did not release decoder')
            result = super().read(); self.in_read = False
            return result
        def release(self):
            assert not self.in_read
            super().release()
    capture = BlockedCapture(); reader = LatestFrameReader(capture)
    assert capture.entered.wait(2)
    try:
        with pytest.raises(TimeoutError, match='read timeout'):reader.read(timeout=.001)
        with pytest.raises(TimeoutError, match='not released concurrently'):reader.close(timeout=.001)
        assert not capture.released.is_set()
    finally:
        capture.allow.set()
        reader.close(timeout=2)
    assert capture.released.is_set()


def test_capture_failure_is_not_reported_as_clean_eof():
    class Broken(Capture):
        def read(self):raise OSError('Decoder failed')
    capture = Broken(); reader = LatestFrameReader(capture)
    assert capture.released.wait(2)
    with pytest.raises(FrameReaderError) as error:reader.read(timeout=1)
    assert isinstance(error.value.__cause__, OSError)
    with pytest.raises(FrameReaderError):reader.close()


@pytest.mark.parametrize('fps', [None, 0, -1, float('nan')])
def test_paced_reader_requires_real_frame_rate(fps):
    capture = Capture()
    with pytest.raises(ValueError):LatestFrameReader(capture, source_fps=fps, pace=True)
    assert capture.index == 0 and not capture.released.is_set()
