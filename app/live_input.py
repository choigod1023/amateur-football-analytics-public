"""Reading frames from a live source that can drop out: reconnect with growing waits and report the loss, so that 'no alerts' is never mistaken for 'no input'.

`ReconnectingReader` wraps an opener (a function that returns an object with read() and release(), like cv2.VideoCapture). A file that ends is the end of the run; a stream or
camera that fails is opened again after 1, 2, 4 ... seconds (at most MAX_WAIT) up to `max_retries` times in a row. Every loss and every recovery goes to `notify(kind, text)`
where kind is 'no_input' or 'input_back' (the runner writes both to the alerts file and the banner). An exception of read() or of the opener counts as a failed read.
"""
import os
import time

MAX_WAIT = 30.0


class ReconnectingReader:
    def __init__(self, open_source, is_file=False, max_retries=8, base_wait=1.0, notify=None, sleep=time.sleep, clock=time.time, log=print):
        self.open_source, self.is_file, self.max_retries, self.base_wait = open_source, is_file, max_retries, base_wait
        self.notify, self.sleep, self.clock, self.log = notify or (lambda kind, text: None), sleep, clock, log
        self.capture = None
        self.gave_up = False
        self.reconnects = 0
        self._open()

    def _open(self):
        try:
            self.capture = self.open_source()
        except Exception as error:                      # a failed open is a failed read, the loop below waits and tries again
            self.log(f'Opening the source failed: {error}')
            self.capture = None

    def _read_once(self):
        if self.capture is None:
            return False, None
        try:
            return self.capture.read()
        except Exception as error:
            self.log(f'Reading the source failed: {error}')
            return False, None

    def read(self):
        """(ok, frame). ok is False at the end of a file, or when a stream could not be read again after max_retries tries (gave_up is then True)."""
        ok, frame = self._read_once()
        if ok:
            return True, frame
        if self.is_file:
            return False, None
        lost_at = self.clock()
        self.notify('no_input', 'The video input stopped; trying to connect again.')
        for attempt in range(self.max_retries):
            wait = min(MAX_WAIT, self.base_wait * 2 ** attempt)
            self.log(f'No input; trying again in {wait:.0f} s ({attempt + 1}/{self.max_retries}).')
            self.sleep(wait)
            self.release()
            self._open()
            ok, frame = self._read_once()
            if ok:
                self.reconnects += 1
                self.notify('input_back', f'The video input is back after {self.clock() - lost_at:.0f} s.')
                return True, frame
        self.gave_up = True
        self.notify('no_input', f'The video input did not come back after {self.max_retries} tries; the run stops.')
        return False, None

    def release(self):
        if self.capture is not None:
            try:
                self.capture.release()
            except Exception:
                pass
            self.capture = None


STATUS_TITLES = {'no_input': '입력 없음', 'input_back': '입력 복구', 'camera_moved': '카메라 이동', 'camera_back': '카메라 보정 복구', 'half_switch': '후반 전환'}
STATUS_TEXT = {'no_input': '영상 입력이 끊겼습니다. 이 동안에는 알림이 나가지 않습니다. 연결을 다시 시도하고 있습니다', 'input_back': '영상 입력이 돌아왔습니다. 알림을 다시 보냅니다',
               'camera_moved': '카메라가 보정할 수 없을 만큼 움직였거나 화면이 확인되지 않습니다. 보정을 다시 확인할 때까지 위치와 알림을 보류합니다',
               'camera_back': '카메라 위치를 다시 확인했습니다. 알림을 다시 보냅니다',
               'half_switch': '후반으로 넘어갔습니다. 공격 방향을 바꾸고 분석을 처음부터 다시 시작했습니다'}


def status_record(kind, t):
    """The line of alerts.jsonl for a loss or a recovery of the input (or of the camera calibration): not a coaching alert, it carries polarity 'status' so that it is not rated as one."""
    return {'time': round(t, 1), 'kind': kind, 'polarity': 'status', 'title': STATUS_TITLES[kind], 'text': STATUS_TEXT[kind], 'detail': None, 'rules': [], 'drill': None}


def heartbeat_record(t, stats):
    """A line every few seconds while the input is alive, so that a quiet alerts file means 'nothing to say' and not 'stopped' (app/bench_view.py reads kind 'heartbeat').
    stats: what the run knows about itself: frames decoded, delivered and thrown away by the latest-frame queue, the delay from reading a frame to its analysis (mean, p95 and max in ms), the camera state."""
    return {'time': round(t, 1), 'kind': 'heartbeat', 'type': 'heartbeat', 'polarity': 'status', 'title': '입력 정상', 'text': '영상 입력과 분석이 돌아가고 있습니다', 'detail': None, 'rules': [], 'drill': None, 'stats': stats,
            'pid': os.getpid(), 'wall': round(time.time(), 1)}      # pid and wall: app/service_watch.py tells a run that died from a run that only lost its input
