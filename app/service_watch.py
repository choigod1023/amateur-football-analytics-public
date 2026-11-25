"""Watching a live run from outside, so that a stop is shown at once on a web page even when the run itself died.

The live run (scripts/run_live_feedback.py) writes <store>/alerts/<session>/alerts.jsonl: coaching alerts, status rows (no_input, input_back) and, every few seconds while frames
arrive, a heartbeat row that carries the process number (pid). This module does not run inside that process. It reads the file the way the bench screen does and decides:

  * ok            the file changed within `stale` seconds, no loss of the input is logged
  * down          one of three causes (the third, a server that does not answer, can only be seen by the browser, see web/watch-banner.js):
      video_lost    the input stopped: a no_input row is the last word, or the heartbeat is silent while the analysis process still exists
      process_dead  the process of the run does not exist any more (pid of the last heartbeat), whatever the file says
      silent        the file is silent and the process cannot be checked (a run from before the pid was written, or another computer)
  * unknown       no heartbeat row and no status row yet: a quiet file says nothing (a run with --heartbeat-seconds 0)
  * idle          the newest run has not changed for hours and has no open outage: nothing to watch

Every outage is written to <store>/service/outages.jsonl (append only): 'down' with the start (the last sign of life, not the moment it was noticed), 'cause' when the cause
changes (a lost input that turns into a dead process), 'up' with the recovery time and the length, 'finished' when a person closes it (the match is over, the run ended on purpose).
The file is read again when the server starts, so an open outage keeps its real start across a restart of the server.

Nothing here writes into the alerts files and nothing leaves the computer.
"""
import json
import os
import threading
import time
from datetime import datetime
from pathlib import Path

from app.bench_view import NOT_LIVE, SESSION, STATUS_KINDS, BenchView, belongs_to_match, current_match, is_live_session

STALE = 25.0                 # seconds without a change of the alerts file (heartbeats come every 10 s while frames arrive) before the run counts as silent
IDLE_AFTER = 3 * 3600.0      # a run that did not change for this long is an old run, not a stop to alarm about
CAUSE_TEXT = {
    'video_lost': ('영상 입력 끊김', '휴대폰이나 송출 쪽에서 영상이 들어오지 않습니다. 분석 프로그램은 켜져 있어서 영상이 돌아오면 저절로 이어집니다.'),
    'process_dead': ('분석 프로그램 종료', '분석 프로그램이 꺼졌습니다. 다시 실행하기 전에는 알림이 나오지 않습니다.'),
    'silent': ('분석 응답 없음', '영상이 끊겼거나 분석 프로그램이 멈춘 것으로 보입니다. 어느 쪽인지는 이 컴퓨터에서 확인해야 합니다.'),
}


def pid_alive(pid):
    """Whether a process with this number exists. (os.kill(pid, 0) must never be used on Windows: there any other signal than the two console events ends the process.)"""
    if not isinstance(pid, int) or pid <= 0:
        return None
    if os.name == 'nt':
        import ctypes
        kernel = ctypes.windll.kernel32
        kernel.OpenProcess.restype = ctypes.c_void_p
        handle = kernel.OpenProcess(0x1000, False, pid)             # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            return bool(kernel.GetExitCodeProcess(ctypes.c_void_p(handle), ctypes.byref(code))) and code.value == 259     # STILL_ACTIVE
        finally:
            kernel.CloseHandle(ctypes.c_void_p(handle))
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def clock_text(moment):
    return datetime.fromtimestamp(moment).strftime('%H:%M:%S')


def length_text(seconds):
    seconds = int(max(0, seconds))
    if seconds < 60:
        return f'{seconds}초'
    if seconds < 3600:
        return f'{seconds // 60}분 {seconds % 60}초'
    return f'{seconds // 3600}시간 {seconds % 3600 // 60}분'


class ServiceWatch:
    def __init__(self, directory, clock=time.time, stale=STALE, pid_check=pid_alive):
        self.directory = Path(directory)
        self.root = self.directory / 'alerts'
        self.log_path = self.directory / 'service' / 'outages.jsonl'
        self.clock, self.stale, self.pid_check = clock, stale, pid_check
        self.lock = threading.RLock()
        self.outages = {}                   # id -> record, in the order of the log
        self.open = {}                      # session -> id of its open outage
        self.acked = {}                     # session -> moment a person silenced the sound
        self.finished = {}                  # session -> moment a person closed its outage; nothing is alarmed until the file changes again
        self.thread = None
        self._load()

    # ---- the log ------------------------------------------------------------------------------------------------------------------
    def _load(self):
        if not self.log_path.is_file():
            return
        for line in self.log_path.read_text(encoding='utf-8', errors='replace').splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if not isinstance(row, dict) or 'id' not in row:
                continue
            ident = row['id']
            if row.get('event') == 'down':
                self.outages[ident] = {'id': ident, 'session': row['session'], 'cause': row['cause'], 'since': row['since'], 'detected': row['detected'], 'ended': None, 'end_reason': None,
                                       'causes': [row['cause']]}
                self.open[row['session']] = ident
            elif ident in self.outages:
                record = self.outages[ident]
                if row.get('event') == 'cause':
                    record['cause'] = row['cause']
                    record['causes'].append(row['cause'])
                elif row.get('event') in ('up', 'finished'):
                    record['ended'], record['end_reason'] = row['at'], row['event']
                    if self.open.get(record['session']) == ident:
                        del self.open[record['session']]

    def _append(self, row):
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.log_path, 'a', encoding='utf-8') as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + '\n')

    def _begin(self, session, cause, since, now):
        ident = (max(self.outages) + 1) if self.outages else 1
        self.outages[ident] = {'id': ident, 'session': session, 'cause': cause, 'since': since, 'detected': now, 'ended': None, 'end_reason': None, 'causes': [cause]}
        self.open[session] = ident
        self._append({'event': 'down', 'id': ident, 'session': session, 'cause': cause, 'since': since, 'detected': now, 'since_text': clock_text(since)})

    def _end(self, session, now, event):
        ident = self.open.pop(session, None)
        if ident is None:
            return
        record = self.outages[ident]
        record['ended'], record['end_reason'] = now, event
        self._append({'event': event, 'id': ident, 'session': session, 'at': now, 'at_text': clock_text(now), 'duration_s': round(now - record['since'], 1)})

    # ---- the judgement ------------------------------------------------------------------------------------------------------------
    def _newest_live(self):
        """(folder, rows, modified) of the live session whose file changed last, or None."""
        if not self.root.is_dir():
            return None
        folders = [p for p in self.root.iterdir() if p.is_dir() and SESSION.match(p.name) and is_live_session(p.name) and (p / 'alerts.jsonl').is_file()]
        # From the moment a new match is started on /setup, a session of a match before it is not the live run any more (the rule of the score board,
        # app/bench_view.belongs_to_match): 2026-11-25 rehearsal, the red band, the half-time prompt and the second-half band of the last match stayed after
        # "새 경기 시작". Nothing is deleted; a new match whose analysis has not written yet is simply 'idle' (no band before the match is normal).
        match = current_match(self.directory)
        folders = [p for p in folders if belongs_to_match(match, p.name, (p / 'alerts.jsonl').stat().st_mtime)]
        for folder in sorted(folders, key=lambda p: (p / 'alerts.jsonl').stat().st_mtime, reverse=True):
            rows = BenchView._read(folder / 'alerts.jsonl')
            if any(r and r.get('kind') not in NOT_LIVE for r in rows):
                return folder, rows, (folder / 'alerts.jsonl').stat().st_mtime
        return None

    def judge(self, rows, modified, now):
        """rows of one alerts file, time of its last change -> (cause or None, state, pid) where state is 'ok', 'down' or 'unknown'."""
        last_word, last_beat, lost_pid = None, None, None
        for row in rows:
            if not row:
                continue
            kind = row.get('kind')
            if kind == 'heartbeat' or row.get('type') == 'heartbeat':
                last_beat = row
                # A lost input is only over when the run says 'input_back' (or another process of the run writes): the run also writes heartbeats while it waits for the video
                # (2026-11-24 rehearsal: the red band lasted one second because a heartbeat followed the 'no_input' row).
                if last_word == 'no_input':
                    if lost_pid is None:
                        lost_pid = row.get('pid')                   # no heartbeat came before the loss: the first one after it belongs to the same process
                    elif row.get('pid') not in (None, lost_pid):
                        last_word = 'heartbeat'
                else:
                    last_word = 'heartbeat'
            elif kind in STATUS_KINDS:
                last_word = kind
                if kind == 'no_input':
                    lost_pid = (last_beat or {}).get('pid')
        pid = (last_beat or {}).get('pid')
        alive = self.pid_check(pid) if pid is not None else None
        age = now - modified
        if alive is False:
            return 'process_dead', 'down', pid
        if last_word == 'no_input':
            return 'video_lost', 'down', pid
        if last_beat is not None and age > self.stale:
            return ('video_lost' if alive else 'silent'), 'down', pid
        if last_word is None:
            return None, 'unknown', pid
        return None, 'ok', pid

    def poll(self):
        """Look once, write the changes to the log, and return the picture of the state (also what the page shows)."""
        with self.lock:
            now = self.clock()
            found = self._newest_live()
            session = None
            cause, state, pid, modified = None, 'idle', None, None
            if found:
                folder, rows, modified = found
                session = folder.name
                cause, state, pid = self.judge(rows, modified, now)
                if now - modified > IDLE_AFTER and session not in self.open:
                    cause, state = None, 'idle'
                if session in self.finished:                          # closed by a person: silent until the run writes again
                    if modified > self.finished[session]:
                        del self.finished[session]
                    else:
                        cause, state = None, 'idle'
            if session is not None:
                if self.acked.get(session) is not None and modified is not None and modified > self.acked[session] and state == 'ok':
                    del self.acked[session]
                if state == 'down':
                    if session not in self.open:
                        self._begin(session, cause, modified, now)
                    elif self.outages[self.open[session]]['cause'] != cause:
                        record = self.outages[self.open[session]]
                        record['cause'] = cause
                        record['causes'].append(cause)
                        self._append({'event': 'cause', 'id': record['id'], 'session': session, 'cause': cause, 'at': now})
                elif state == 'ok' and session in self.open:
                    self._end(session, now, 'up')
                    self.acked.pop(session, None)
            return self._picture(session, state, cause, pid, modified, now)

    def _picture(self, session, state, cause, pid, modified, now):
        out = {'now': now, 'session': session, 'state': state, 'cause': cause, 'pid': pid, 'last_change_age_s': None if modified is None else round(now - modified, 1)}
        record = self.outages.get(self.open.get(session)) if session else None
        if state == 'down' and record:
            title, detail = CAUSE_TEXT[cause]
            out.update({'headline': title, 'detail': detail, 'since': record['since'], 'since_text': clock_text(record['since']), 'duration_s': round(now - record['since'], 1),
                        'duration_text': length_text(now - record['since']), 'acked': session in self.acked, 'outage_id': record['id']})
        else:
            out.update({'headline': {'ok': '라이브 분석 정상', 'unknown': '정상 여부를 알 수 없음', 'idle': '감시할 라이브 실행 없음'}[state],
                        'detail': {'ok': '', 'unknown': '하트비트 기록이 없어 멈춤을 판단할 수 없습니다.', 'idle': ''}[state]})
        out['outages'] = self.listing(8)
        return out

    def listing(self, limit=10):
        """The newest outages first, with times in words."""
        now = self.clock()
        rows = []
        for ident in sorted(self.outages, reverse=True)[:limit]:
            r = self.outages[ident]
            end = r['ended'] if r['ended'] is not None else now
            title = CAUSE_TEXT[r['cause']][0]
            rows.append({'id': ident, 'session': r['session'], 'cause': r['cause'], 'cause_text': title, 'causes': [CAUSE_TEXT[c][0] for c in r['causes']],
                         'since_text': clock_text(r['since']), 'ended_text': clock_text(r['ended']) if r['ended'] is not None else None, 'open': r['ended'] is None,
                         'duration_s': round(end - r['since'], 1), 'duration_text': length_text(end - r['since']),
                         'end_reason': {'up': '복구', 'finished': '사람이 종료 처리'}.get(r['end_reason'])})
        return rows

    # ---- what a person can do -----------------------------------------------------------------------------------------------------
    def ack(self, session):
        """Silence the sound for the open outage of this session (it stays open and logged until the run is back)."""
        with self.lock:
            if session in self.open:
                self.acked[session] = self.clock()
                return True
            return False

    def finish(self, session):
        """Close the open outage because the match or the run is over on purpose."""
        with self.lock:
            if session not in self.open:
                return False
            self._end(session, self.clock(), 'finished')
            self.finished[session] = self.clock()
            return True

    # ---- a thread, so that an outage is logged while nobody has the page open --------------------------------------------------------
    def start(self, interval=2.0):
        if self.thread is not None:
            return

        def loop():
            while True:
                try:
                    self.poll()
                except Exception:                                  # the watch must outlive any single odd file
                    pass
                time.sleep(interval)
        self.thread = threading.Thread(target=loop, name='service-watch', daemon=True)
        self.thread.start()
