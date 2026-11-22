"""Report jobs of the web dashboard: an uploaded recording becomes a team video report, one job at a time.

A job lives in <store>/reports/<job id>/ with job.json (what the user asked for), status.json (state, step, percent), the uploaded video and
the outputs written by scripts/run_report_job.py. Anything that changes something (upload, cancel, retry, delete, reading a log) needs the
access token (FOOTBALL_REPORT_TOKEN); without one set on the server nothing can be changed. The upload is streamed to disk with a size limit;
the file name from the browser is never used as a path. Only the output files named in OUTPUTS can be downloaded.

States: uploading, queued, running, done, failed, cancelled. A server restart puts the jobs that were running back into the queue.
"""
import hmac
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

JOB_ID = re.compile(r'^r[0-9a-f]{12}$')
EXTENSIONS = ('.mp4', '.mov', '.mkv', '.ts', '.m4v')
OUTPUTS = ('review.mp4', 'review.md', 'events.json', 'report.mp4', 'report.md', 'scenes.json')
LOGS = ('detect', 'track', 'report', 'worker')
MAX_BYTES = int(os.environ.get('FOOTBALL_REPORT_MAX_MB', '4096')) * 1024 * 1024
KEEP_JOBS = int(os.environ.get('FOOTBALL_REPORT_KEEP', '40'))
STATES = ('uploading', 'queued', 'running', 'done', 'failed', 'cancelled')
STEP_NAMES = {'upload': '업로드', 'waiting': '순서 대기', 'starting': '시작 준비', 'detect': '선수 탐지', 'track': '선수 추적', 'report': '리포트 영상 제작', 'done': '완료', 'setup': '설정 확인'}
MAX_GOALS = 12


def token_ok(given, expected):
    return bool(expected) and bool(given) and hmac.compare_digest(given.encode(), expected.encode())


class ReportJobs:
    def __init__(self, directory, token=None, worker_command=None, cameras_file=None):
        self.root = Path(directory) / 'reports'
        self.token = token if token is not None else os.environ.get('FOOTBALL_REPORT_TOKEN', '')
        self.worker_command = worker_command or [sys.executable, str(Path(__file__).resolve().parents[1] / 'scripts' / 'run_report_job.py')]
        self.cameras_file = cameras_file if cameras_file is not None else os.environ.get('FOOTBALL_REPORT_CAMERAS', '')
        self.lock = threading.Lock()
        self.wake = threading.Event()
        self.thread = None
        self.process = None
        self.running_id = None
        self.cancelled = set()

    # ---- storage helpers ------------------------------------------------------------------------------------------------------
    def _folder(self, job_id):
        if not JOB_ID.match(job_id or ''):
            raise ValueError('Unknown job')
        folder = self.root / job_id
        if not folder.is_dir():
            raise ValueError('Unknown job')
        return folder

    @staticmethod
    def _write(path, data):
        temporary = path.with_suffix(path.suffix + '.tmp')
        temporary.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        os.replace(temporary, path)

    @staticmethod
    def _read(path):
        try:
            return json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return None

    def _set_status(self, folder, state, step, percent=None, message=None):
        status = {'state': state, 'step': step, 'updated': time.strftime('%Y-%m-%d %H:%M:%S')}
        if percent is not None:
            status['percent'] = percent
        if message:
            status['message'] = message[:300]
        self._write(folder / 'status.json', status)

    # ---- options ----------------------------------------------------------------------------------------------------------------
    def cameras(self):
        """[{'id', 'label'}] of the camera settings the server can use (the keys of the camera settings file)."""
        data = self._read(Path(self.cameras_file)) if self.cameras_file else None
        return [{'id': key, 'label': (value.get('label') if isinstance(value, dict) else None) or key} for key, value in (data or {}).items()]

    def validate(self, options):
        """The options of a job, checked: title, team A or B, direction +1 or -1, camera name, seconds, goal seconds."""
        try:
            clean = {'camera': str(options['camera']), 'team': str(options['team']), 'direction': int(options['direction']),
                     'start': float(options.get('start', 0)), 'end': float(options['end']), 'half_name': str(options.get('half_name') or '경기')[:12],
                     'title': ' '.join(str(options.get('title') or '').split())[:60]}
            goals = [float(g) for g in re.split(r'[,\s]+', str(options.get('goals') or '').strip()) if g]
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError('Missing or invalid option') from exc
        if not re.match(r'^[a-z0-9_-]{2,16}$', clean['camera']) or clean['team'] not in ('A', 'B') or clean['direction'] not in (1, -1):
            raise ValueError('Invalid camera, team or direction')
        if not 0 <= clean['start'] < clean['end'] <= clean['start'] + 4 * 3600:
            raise ValueError('The time range must be between 0 seconds and 4 hours')
        if len(goals) > MAX_GOALS or any(not clean['start'] <= g <= clean['end'] for g in goals):
            raise ValueError(f'At most {MAX_GOALS} goal times, each inside the analysed range')
        clean['goals'] = goals
        return clean

    # ---- life cycle -------------------------------------------------------------------------------------------------------------
    def new_job(self, options, name):
        """Reserve a job id for an upload. Returns (job id, path the video must be written to)."""
        suffix = Path(name or '').suffix.lower()
        if suffix not in EXTENSIONS:
            raise ValueError('Allowed video types: ' + ', '.join(EXTENSIONS))
        clean = self.validate(options)
        job_id = 'r' + secrets.token_hex(6)
        folder = self.root / job_id
        folder.mkdir(parents=True, exist_ok=False)
        video = folder / ('upload' + suffix)
        self._write(folder / 'job.json', {**clean, 'video': video.name, 'original_name': Path(name or '').name[:80], 'created': time.strftime('%Y-%m-%d %H:%M:%S')})
        self._set_status(folder, 'uploading', 'upload', 0)
        return job_id, video

    def queue(self, job_id):
        self._set_status(self._folder(job_id), 'queued', 'waiting', 0)
        self.wake.set()
        self.start_worker()
        self.prune()

    def fail(self, job_id, message):
        folder = self._folder(job_id)
        self._set_status(folder, 'failed', 'upload', None, message)
        for item in folder.glob('upload.*'):
            item.unlink(missing_ok=True)

    def cancel(self, job_id):
        """Queued jobs are cancelled at once; a running job is stopped. Finished jobs cannot be cancelled."""
        folder = self._folder(job_id)
        status = self._read(folder / 'status.json') or {}
        if status.get('state') == 'queued':
            self._set_status(folder, 'cancelled', status.get('step', 'waiting'), None, '사용자가 취소했습니다.')
            return True
        if status.get('state') == 'running' and self.running_id == job_id and self.process is not None:
            self.cancelled.add(job_id)
            if os.name == 'nt':
                subprocess.run(['taskkill', '/PID', str(self.process.pid), '/T', '/F'], capture_output=True)       # the worker started its own programs
            else:
                self.process.terminate()
            return True
        return False

    def retry(self, job_id):
        """A failed or cancelled job goes back into the queue (its upload must still be there)."""
        folder = self._folder(job_id)
        status = self._read(folder / 'status.json') or {}
        job = self._read(folder / 'job.json') or {}
        if status.get('state') not in ('failed', 'cancelled') or not (folder / job.get('video', 'upload.mp4')).is_file():
            return False
        for name in OUTPUTS + ('tracks.json', 'raw.mp4'):
            (folder / name).unlink(missing_ok=True)
        shutil.rmtree(folder / 'cache', ignore_errors=True)
        self.queue(job_id)
        return True

    def delete(self, job_id):
        """Remove a job with its upload and outputs. A running job cannot be deleted."""
        folder = self._folder(job_id)
        if (self._read(folder / 'status.json') or {}).get('state') in ('running', 'uploading'):
            return False
        shutil.rmtree(folder, ignore_errors=True)
        return True

    def prune(self):
        """Keep only the newest KEEP_JOBS finished jobs (queued and running jobs are never removed)."""
        done = [f for f in sorted(self.root.glob('r*'), reverse=True) if JOB_ID.match(f.name) and (self._read(f / 'status.json') or {}).get('state') in ('done', 'failed', 'cancelled')]
        for folder in done[KEEP_JOBS:]:
            shutil.rmtree(folder, ignore_errors=True)

    def recover(self):
        """After a restart: jobs that were running or uploading have no worker any more. Running jobs go back into the queue, interrupted uploads fail."""
        if not self.root.is_dir():
            return
        for folder in sorted(self.root.glob('r*')):
            status = self._read(folder / 'status.json') or {}
            if status.get('state') == 'running':
                self._set_status(folder, 'queued', 'waiting', 0, '서버가 다시 시작되어 순서 대기로 돌아왔습니다.')
            elif status.get('state') == 'uploading':
                self._set_status(folder, 'failed', 'upload', None, '업로드 중에 서버가 다시 시작되었습니다. 다시 올려 주세요.')
        if any((self._read(f / 'status.json') or {}).get('state') == 'queued' for f in self.root.glob('r*')):
            self.wake.set()
            self.start_worker()

    # ---- reading ----------------------------------------------------------------------------------------------------------------
    def listing(self):
        jobs = []
        for folder in sorted(self.root.glob('r*'), reverse=True) if self.root.is_dir() else []:
            if not JOB_ID.match(folder.name):
                continue
            job, status = self._read(folder / 'job.json'), self._read(folder / 'status.json')
            if job and status:
                jobs.append({'id': folder.name, 'created': job.get('created'), 'camera': job['camera'], 'team': job['team'], 'half_name': job['half_name'],
                             'title': job.get('title') or job.get('original_name') or folder.name, 'goals': job.get('goals', []), 'range': [job['start'], job['end']],
                             'status': {**status, 'step_name': STEP_NAMES.get(status.get('step'), status.get('step'))},
                             'files': [n for n in OUTPUTS if (folder / n).is_file()], 'can_retry': status.get('state') in ('failed', 'cancelled') and (folder / job.get('video', 'upload.mp4')).is_file()})
        return {'jobs': jobs[:100]}

    def output(self, job_id, name):
        """Path of a finished output file, or None."""
        if name not in OUTPUTS:
            return None
        path = self._folder(job_id) / name
        return path if path.is_file() else None

    def log_tail(self, job_id, step, size=4000):
        """The end of a step log with absolute paths shortened to their file names."""
        if step not in LOGS:
            raise ValueError('Unknown log')
        path = self._folder(job_id) / f'{step}.log'
        try:
            text = path.read_text(encoding='utf-8', errors='replace')[-size:]
        except OSError:
            return ''
        return re.sub(r'(?:[A-Za-z]:)?[\\/](?:[^\s\\/:"\']+[\\/])+', '', text)

    def health(self):
        free = shutil.disk_usage(self.root.parent).free / 2 ** 30
        counts = {state: 0 for state in STATES}
        for folder in self.root.glob('r*') if self.root.is_dir() else []:
            state = (self._read(folder / 'status.json') or {}).get('state')
            if state in counts:
                counts[state] += 1
        return {'worker_alive': bool(self.thread and self.thread.is_alive()), 'counts': counts, 'disk_free_gb': round(free, 1), 'upload_enabled': bool(self.token)}

    # ---- worker -----------------------------------------------------------------------------------------------------------------
    def start_worker(self):
        with self.lock:
            if self.thread and self.thread.is_alive():
                return
            self.thread = threading.Thread(target=self._loop, daemon=True)
            self.thread.start()

    def _next(self):
        for folder in sorted(self.root.glob('r*')):
            if (self._read(folder / 'status.json') or {}).get('state') == 'queued':
                return folder
        return None

    def _loop(self):
        while True:
            folder = self._next()
            if folder is None:
                if not self.wake.wait(timeout=5):
                    return
                self.wake.clear()
                continue
            job_id = folder.name
            self._set_status(folder, 'running', 'starting', 0)
            self.running_id = job_id
            try:
                self.process = subprocess.Popen([*self.worker_command, str(folder)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                try:
                    stdout, stderr = self.process.communicate(timeout=12 * 3600)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    stdout, stderr = self.process.communicate()
                    self._set_status(folder, 'failed', 'worker', None, '처리 시간이 12시간을 넘겨 중단했습니다.')
                    continue
                status = self._read(folder / 'status.json') or {}
                if job_id in self.cancelled:
                    self.cancelled.discard(job_id)
                    self._set_status(folder, 'cancelled', status.get('step', 'starting'), None, '사용자가 취소했습니다.')
                elif self.process.returncode != 0 and status.get('state') != 'failed':
                    (folder / 'worker.log').write_text((stdout or '') + (stderr or ''), encoding='utf-8')
                    self._set_status(folder, 'failed', status.get('step', ''), None, '작업기가 예기치 않게 멈췄습니다. 관리자는 처리 로그의 "작업기"에서 원인을 볼 수 있습니다.')
            except (OSError, subprocess.SubprocessError) as exc:
                (folder / 'worker.log').write_text(str(exc), encoding='utf-8')
                self._set_status(folder, 'failed', 'worker', None, '작업기를 시작하지 못했습니다. 관리자에게 알려 주세요.')
            finally:
                self.process = None
                self.running_id = None
