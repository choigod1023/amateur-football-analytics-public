"""Match preparation from one phone page (/setup, "경기 준비"), added to the review server by one call: install(app, directory, web_root).

The page walks a person who has never seen the system through the match-day settings, top to bottom:
  1 new match   name the match; what the last match left behind (team colours, colour pictures) moves to an archive folder
  2 video       the phone stream arrives (picture on the page)
  3 lines       one picture of the stream with the saved calibration drawn on it, "맞음 / 안 맞음"
  4 colours     make the colour pictures (scripts/team_select_prepare.py, the command of the match-day sheet), then choose the own team
                with the existing /api/v1/team-select API. The live run reads the colour choice once, at its start, so this comes BEFORE the run.
  5 analysis    free memory, the attack direction, then the live run (scripts/run_live_feedback.py with the "새 팀 판별 명령" options)
  6 check       which team reader the run chose (Small-box team reader ON/OFF line of its log) and how many own players it sees
  7 ready       links to the bench and the tag page

Safety (2026-11-24: the owner decided on no operation password, so anybody who can open the page can start and stop the run)
  - The Host and Origin checks of review_public.py apply to every POST.
  - Stopping the run and starting a new match (which moves the last match's files to the archive) need the last four characters of the match
    name typed on the page. That is not a secret, only a guard against a wrong tap; the page says so.
  - Starts (run, restart, colour pictures) are taken at most START_LIMIT times per START_WINDOW seconds.
  - A run starts only while the stream comes in (a fresh picture) and no other run is going.
  - Every start, stop, restart and new match is written to <store>/service/setup/actions.jsonl with the server time and the address of the
    phone that asked (not shown on the page). A run that ended without a stop request is written there as "run_died".
  - Only the commands written here run. A request chooses only the match name (checked by MATCH_NAME), the attack direction (1 or -1) and
    start / stop. A second run is refused while one is running (also one started from a terminal), and so are the colour pictures.
  - Nothing is deleted: a new match moves service/team_profile.json and service/team_select/ to service/_archive/<time>-before-<name>/.
  - The live run is started as its own process (new process group, outside the server's job when Windows allows it), so a restart of the
    server does not end it. Its output goes to <run folder>/run.log like the "*> run.log" of the match-day sheet.
"""
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse, Response
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app import analyst_tags
from app.bench_view import current_match as started_match

PAGES = {'/setup': ('setup.html', None), '/setup.js': ('setup.js', 'application/javascript'), '/setup.css': ('setup.css', 'text/css')}
MATCH_NAME = re.compile(r'^(?!label-)[a-z0-9][a-z0-9-]{2,39}$')
REPO = Path(__file__).resolve().parents[1]
BASE = REPO.parents[1]                                         # ...\<work folder>
CAMERA = 'cam4'
OWN_TEAM = 'B'
RAM_GOOD_GB, RAM_BLOCK_GB = 12.0, 4.0                          # match-day sheet: 12 GB free; the run itself needs about 1.9 GB
VRAM_GOOD_GB, VRAM_BLOCK_GB = 4.0, 3.0                         # the run needs up to 2.3 GB of graphics memory
PROJECT_RAM_GB, PROJECT_VRAM_GB = 12.0, 8.0                    # the project rule (CLAUDE.md, wiki/gpu-memory-rules.md): below this the page says so in plain words; the start is still allowed (the block values above did not change)
GIVE_UP_SECONDS = 1200                                         # a lost video input is waited for this long (20 minutes) before the run ends on its own (2026-11-24: it was about 2 minutes)
TEMPORARY_DIRECTION = -1                                       # the attack direction of a run started in the warm-up, before the sides are known; it is chosen for real just before the kickoff
DEFAULT_RESTART_SECONDS = 10                                   # shown as "about N seconds" until a restart has been measured on this computer (2026-11-25 rehearsal: 4 to 9 s, 3 restarts; it was 60)
MEASURE_UP_TO = 300                                            # a first second later than this after the start is not a start time (the page was closed, the video was missing)
FEW_PLAYERS = 6                                                # match-day sheet section 4: fewer than 6 own players after a minute = restart with the basic command
FEW_PICTURE_PEOPLE = 6                                         # a colour group read from fewer people than this: the page asks for the pictures again (the same temporary 6 of the sheet, not tested)
PREPARE_SECONDS = 60                                           # seconds of stream the colour pictures are read from (one frame a second); see work/overnight-1124/setup/profile-check
PREPARE_GROUPS = 2                                             # 2026-11-25 colour pick: up to 5 colour groups; the person picks the own and the opponent group
PREPARE_RETAKES = 2                                            # and the pictures are taken again by themselves (at most 2 more) when no two groups are clear
PREPARE_FIRST_SECONDS = 78                                     # one sample from the press to the pictures (rehearsals 2026-11-25: 78.3, 78.5, 78.7 s); the guess of the time left
START_LIMIT, START_WINDOW = 3, 60.0                            # at most 3 start requests (run, restart, colour pictures) a minute
FRAME_EVERY, FRAME_FRESH = 6.0, 20.0                           # seconds between two pictures of the stream; a picture older than this means no stream


def paths():
    """The fixed places of the match-day sheet; the environment values only exist for the test server."""
    return {
        'python': Path(os.environ.get('FOOTBALL_SETUP_PYTHON') or BASE / 'outputs' / 'football-coach-server' / '.venv' / 'Scripts' / 'python.exe'),
        'calibrations': BASE / 'work' / 'venue-1120' / 'calibrations.json',
        'detector': BASE / 'work' / 'detector-ft-20261112' / 'ft_n2' / 'best.pt',
        'run_root': Path(os.environ.get('FOOTBALL_SETUP_RUN_ROOT') or BASE / 'work'),
        'source': os.environ.get('LIVE_VIDEO_URL', 'rtsp://127.0.0.1:18554/match'),
    }


def run_folder(run_root, session):
    """match-20261125 -> <work>/live-run-1125 (the folder of the match-day sheet); any other name -> <work>/live-run-<name>."""
    found = re.fullmatch(r'match-\d{4}(\d{4})', session)
    return Path(run_root) / ('live-run-' + (found.group(1) if found else session))


def analysis_command(store, session, direction, p=None):
    """The "새 팀 판별 명령" of work/match-commands-20261125.md section 4, option for option. Only the session and the direction change."""
    p = p or paths()
    store = Path(store)
    folder = run_folder(p['run_root'], session)
    return [str(p['python']), 'scripts/run_live_feedback.py', p['source'], str(p['calibrations']), CAMERA,
            '--direction', str(int(direction)), '--team', OWN_TEAM, '--detector', str(p['detector']),
            '--detector-half', '--detector-batch', '8', '--link-team-gate', '--mark-keeper-zone', '--reconnect-max-seconds', '2', '--reconnect-give-up-seconds', str(GIVE_UP_SECONDS),
            '--small-box-team', '0.6', '--small-box-team-all', '--team-vote-switch', '4',
            '--pitch-margin', '-1.5', '--neon-band', '30', '70', '--dark-min', '0.15', '--vote-min', '2',
            '--team-profile', str(store / 'service' / 'team_profile.json'), '--store', str(store), '--session', session,
            '--positions', str(store / 'alerts' / session / 'positions.jsonl'), '--frames-log', str(folder / 'frames.jsonl'),
            '--heartbeat-seconds', '5', '--device', '0']


def prepare_command(store, p=None):
    """The team colour pictures, the team_select_prepare.py line of the match-day sheet section 3."""
    p = p or paths()
    return [str(p['python']), 'scripts/team_select_prepare.py', p['source'], '--store', str(store), '--start', '0', '--seconds', str(PREPARE_SECONDS),
            '--calibrations', str(p['calibrations']), '--camera', CAMERA, '--pitch-margin', '0', '--groups', str(PREPARE_GROUPS), '--retakes', str(PREPARE_RETAKES)]


def now_text(t=None):
    return time.strftime('%Y-%m-%dT%H:%M:%S', time.localtime(t))


class MatchChoice(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(max_length=40)
    mode: str = Field(default='new', max_length=10)            # new | continue
    confirm: str = Field(default='', max_length=10)             # last four characters of the name, typed by the person


class StopRun(BaseModel):
    model_config = ConfigDict(extra='forbid')
    confirm: str = Field(default='', max_length=10)             # last four characters of the running match's name


def confirm_ok(name, typed):
    return bool(name) and len(name) >= 4 and (typed or '').strip().lower() == name[-4:]


class LinesAnswer(BaseModel):
    model_config = ConfigDict(extra='forbid')
    answer: str = Field(max_length=10)                         # ok | bad | skip


class StartRun(BaseModel):
    model_config = ConfigDict(extra='forbid')
    direction: Optional[int] = None                            # None: the warm-up start, the direction is only temporary and is chosen before the kickoff


class DirectionChoice(BaseModel):
    model_config = ConfigDict(extra='forbid')
    direction: int


# ---- processes ---------------------------------------------------------------------------------------------------------------------
class Processes:
    """Finds the live runs and colour-picture jobs on this computer (also those started from a terminal) and starts the fixed commands."""

    def __init__(self, scan=None, launch=None, alive=None, kill=None, cmdline=None):
        self._scan = scan or self._psutil_scan
        self._launch = launch or self._popen
        self._alive = alive or self._psutil_alive
        self._kill = kill or self._psutil_kill
        self._cmdline = cmdline or self._psutil_cmdline
        self.cache = (0.0, [])

    @staticmethod
    def _psutil_cmdline(pid):
        """The command line of a process as a list, or None when it cannot be read."""
        try:
            import psutil
            return list(psutil.Process(pid).cmdline())
        except Exception:
            return None

    @staticmethod
    def _psutil_scan():
        import psutil
        found = []
        for proc in psutil.process_iter(['pid', 'ppid', 'cmdline', 'create_time']):
            try:
                args = list(proc.info['cmdline'] or [])
            except Exception:
                continue
            names = {Path(a.replace('\\', '/')).name.lower() for a in args if len(a) < 1024}
            if any(Path(a.replace('\\', '/')).name.lower() == 'gpu_guard.py' for a in args):
                continue                                                       # a guarded job is counted by its child
            for kind, marker in (('run', 'run_live_feedback.py'), ('prepare', 'team_select_prepare.py'), ('recorder', 'record_stream_loop.ps1')):
                if marker in names:
                    found.append({'kind': kind, 'pid': proc.info['pid'], 'ppid': proc.info.get('ppid'), 'create_time': proc.info['create_time'], 'args': args})
        return found

    def scan(self, max_age=2.0):
        at, value = self.cache
        if time.time() - at > max_age:
            try:
                value = self._scan()
            except Exception:
                value = []
            self.cache = (time.time(), value)
        return value

    def forget(self):
        self.cache = (0.0, [])

    def of(self, kind):
        return [p for p in self.scan() if p['kind'] == kind]

    @staticmethod
    def _popen(command, log_path, cwd):
        log_path.parent.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ, PYTHONUNBUFFERED='1', PYTHONIOENCODING='utf-8')
        env.pop('FOOTBALL_REPORT_TOKEN', None)                                     # the run never needs the upload password of the server
        with open(log_path, 'ab') as log:
            flags = 0
            if os.name == 'nt':
                flags = 0x00000200 | 0x08000000                                    # CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW
                try:
                    process = subprocess.Popen(command, cwd=str(cwd), stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, env=env,
                                               creationflags=flags | 0x01000000)       # CREATE_BREAKAWAY_FROM_JOB: survives the end of the server's job
                except OSError:
                    process = subprocess.Popen(command, cwd=str(cwd), stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, env=env, creationflags=flags)
            else:
                process = subprocess.Popen(command, cwd=str(cwd), stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, env=env, start_new_session=True)
        try:
            import psutil
            created = psutil.Process(process.pid).create_time()
        except Exception:
            created = time.time()
        return {'pid': process.pid, 'create_time': created, 'handle': process}

    @staticmethod
    def _psutil_alive(pid, create_time):
        try:
            import psutil
            proc = psutil.Process(pid)
            return proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE and abs(proc.create_time() - create_time) < 1.0
        except Exception:
            return False

    @staticmethod
    def _psutil_kill(pid, create_time):
        import psutil
        try:
            proc = psutil.Process(pid)
            if abs(proc.create_time() - create_time) >= 1.0:
                return False
            children = proc.children(recursive=True)
            for child in children + [proc]:
                try:
                    child.terminate()
                except psutil.Error:
                    pass
            psutil.wait_procs(children + [proc], timeout=10)
            return True
        except psutil.Error:
            return False


# ---- machine state -----------------------------------------------------------------------------------------------------------------
def memory_free():
    """(free RAM GB or None, free graphics memory GB or None)."""
    ram = vram = None
    try:
        import psutil
        ram = psutil.virtual_memory().available / 1024 ** 3
    except Exception:
        pass
    try:
        out = subprocess.run(['nvidia-smi', '--query-gpu=memory.free', '--format=csv,noheader,nounits'], capture_output=True, text=True, timeout=5,
                             creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if out.returncode == 0 and out.stdout.strip():
            vram = float(out.stdout.strip().splitlines()[0]) / 1024
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    return ram, vram


def port_open(url, timeout=0.5):
    parts = urlsplit(url)
    host, port = parts.hostname or '127.0.0.1', parts.port or 554
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def grab_frame(source, timeout=12.0):
    """One JPEG of the stream (ffmpeg, like the frame line of the match-day sheet), or None."""
    from app.live_video_routes import _ffmpeg
    ffmpeg = _ffmpeg()
    if not ffmpeg:
        return None
    command = [ffmpeg, '-hide_banner', '-loglevel', 'error', '-rtsp_transport', 'tcp', '-i', source, '-an', '-frames:v', '1', '-f', 'image2pipe', '-c:v', 'mjpeg', '-q:v', '4', 'pipe:1']
    try:
        out = subprocess.run(command, capture_output=True, timeout=timeout, stdin=subprocess.DEVNULL, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except (OSError, subprocess.SubprocessError):
        return None
    data = out.stdout
    return data if data[:2] == b'\xff\xd8' else None


def draw_lines(jpeg, calibrations_path, camera=CAMERA):
    """The pitch lines of the saved calibration over one picture of the stream, as JPEG bytes (None when it cannot be drawn)."""
    import cv2
    import numpy as np
    from app.pitch_map import fit, pitch_lines
    record = json.loads(Path(calibrations_path).read_text(encoding='utf-8')).get(camera)
    if not record:
        return None
    fitted = fit(record)
    if 'H' not in fitted:
        return None
    inverse = np.linalg.inv(fitted['H'])
    image = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        return None
    height, width = image.shape[:2]
    for line in pitch_lines(fitted.get('pitch') or record.get('pitch')):
        points = []
        for x, y in line:
            w = inverse[2, 0] * x + inverse[2, 1] * y + inverse[2, 2]
            if w <= 0:
                points = []
                continue
            u = (inverse[0, 0] * x + inverse[0, 1] * y + inverse[0, 2]) / w
            v = (inverse[1, 0] * x + inverse[1, 1] * y + inverse[1, 2]) / w
            points.append((int(round(u * width)), int(round(v * height))))
        if len(points) >= 2:
            cv2.polylines(image, [np.array(points, np.int32)], False, (255, 0, 255), max(2, width // 640), cv2.LINE_AA)
    ok, data = cv2.imencode('.jpg', image, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return data.tobytes() if ok else None


def read_log(path, head=262144, tail=8192):
    """(first part, last part) of a run log as text."""
    try:
        with open(path, 'rb') as handle:
            first = handle.read(head)
            handle.seek(0, 2)
            size = handle.tell()
            handle.seek(max(0, size - tail))
            last = handle.read()
    except OSError:
        return '', ''
    return first.decode('utf-8', errors='replace'), last.decode('utf-8', errors='replace')


def reader_mode(text):
    if 'Small-box team reader ON' in text:
        return 'on'
    if 'Small-box team reader OFF' in text:
        return 'off'
    return None


RECOLOUR_DROP = 3                                              # P4 (2026-11-25): the own mean this much below the one before "팀 색 다시 찍기" = the new colours are worse
RECOLOUR_LOOK_AFTER = 60                                       # seconds of the new analysis before its own mean is judged (the "최근 평균" is a minute)
WEAK_PICTURES_TEXT = '이 사진으로는 두 팀 색 구분이 약합니다. 다시 찍거나 이전 팀 색을 쓰세요.'
REVERT_LABEL = '이전 팀 색으로 되돌리기'


def recolour_worse(before, mean):
    """Whether the colours taken again read fewer own players: the own mean fell below the mean before the new pictures, and it is under FEW_PLAYERS or
    RECOLOUR_DROP or more lower. A mean that rose (4 to 5) is not a warning."""
    if mean is None:
        return False
    if before is None:                                         # no mean from before the new pictures: only the count itself can be judged
        return mean < FEW_PLAYERS
    return mean < before and (mean < FEW_PLAYERS or before - mean >= RECOLOUR_DROP)


def reader_preview(candidates):
    """(on, log line) of the team reader a run would choose with these pictures, by the run's own rule (app/small_box_team.reader_decision on the profile
    app/team_select_routes would save); the decision does not depend on which group is ours. None when the pictures have no colour groups."""
    try:
        from app.small_box_team import reader_decision
        from app.team_color_profile import make_profile
        if len(candidates['split']['groups']) <= 2:
            return reader_decision(make_profile(candidates['split'], 0))
        from app.colour_pick import sample_score                 # three or more groups: ON when some pair of groups the person may pick is ON
        best = sample_score(candidates['split'])['best']
        return (best['on'], best['line']) if best else None
    except (KeyError, TypeError, ValueError, ImportError):
        return None


def retake_text(progress, now=None):
    """The line while the pictures are taken again by themselves (<team_select>/progress.json of scripts/team_select_prepare.py), or None during the first sample.
    The time left is a guess: the samples still to come at the length of the first one (else PREPARE_FIRST_SECONDS), less the time of this one so far."""
    if not isinstance(progress, dict) or not isinstance(progress.get('attempt'), int) or progress['attempt'] < 2:
        return None
    now = time.time() if now is None else now
    attempt, total = progress['attempt'], int(progress.get('of') or progress['attempt'])
    each = float(progress.get('first_seconds') or PREPARE_FIRST_SECONDS)
    began = progress.get('attempt_began')
    left = max(0.0, (total - attempt + 1) * each - (now - float(began if began is not None else now)))
    minutes, seconds = divmod(int(round(left / 10.0) * 10), 60)
    when = f'약 {minutes}분 {seconds}초' if minutes and seconds else f'약 {minutes}분' if minutes else f'약 {max(seconds, 10)}초'
    return f'팀 색이 뚜렷하지 않아 한 번 더 찍는 중입니다 ({attempt}/{total}). 남은 시간 최대 {when}.'


def own_counts(positions_path, now=None, fresh=15.0):
    """(own players in the newest second or None when the file is not fresh, mean of the last 60 seconds or None, seconds read)."""
    path = Path(positions_path)
    try:
        modified = path.stat().st_mtime
        with open(path, 'rb') as handle:
            handle.seek(0, 2)
            size = handle.tell()
            handle.seek(max(0, size - 262144))
            lines = handle.read().decode('utf-8', errors='replace').splitlines()
    except OSError:
        return None, None, 0
    seconds = []
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict) and row.get('type') == 'second' and isinstance(row.get('team'), list):
            seconds.append(len(row['team']))
    if not seconds:
        return None, None, 0
    recent = seconds[-60:]
    current = seconds[-1] if (now or time.time()) - modified <= fresh else None
    return current, round(sum(recent) / len(recent), 1), len(recent)


# ---- the routes --------------------------------------------------------------------------------------------------------------------
def client_of(request):
    return request.client.host if request.client else None


OTHER_RUN_TEXT = '이 컴퓨터에서 다른 분석이 이미 돌고 있습니다. 담당자에게 연락하세요.'


def _norm(text):
    return str(text).replace('\\', '/').rstrip('/').lower()


def command_belongs(args, store, folder=None):
    """Whether a command line is one this server started for its own store: '--store <store>' (and the run folder, for a run) appear in it.
    2026-11-25 rehearsal: a test server on another store ended the rehearsal's analysis six times, because it ended every run_live_feedback.py on the computer."""
    if args is None:
        return None
    parts = [_norm(a) for a in args]
    mine = _norm(Path(store).resolve()) if Path(store).exists() else _norm(store)
    stores = {_norm(store), mine}
    if not any(parts[i] == '--store' and parts[i + 1] in stores for i in range(len(parts) - 1)):
        return False
    if folder is None:
        return True
    inside = {_norm(folder) + '/', _norm(Path(folder).resolve()) + '/'}
    return any(p.startswith(prefix) for p in parts for prefix in inside)


def install(app, directory, web_root, processes=None, frame_source=None, memory=None, receiver_check=None):
    store = Path(directory)
    root = Path(web_root).resolve()
    service = store / 'service'
    setup = service / 'setup'
    match_path = setup / 'match.json'
    run_path = setup / 'run.json'
    prepare_path = setup / 'prepare.json'
    lines_path = setup / 'lines.json'
    actions_path = setup / 'actions.jsonl'
    direction_path = setup / 'direction.json'       # {match, direction, confirmed}: the attack direction of this match (confirmed = chosen just before the kickoff)
    kept_path = setup / 'colours_kept.json'          # {match, at, ...}: "팀 색 그대로 사용" was pressed
    job_path = setup / 'job.json'                    # a colour change that restarts the analysis by itself
    times_path = setup / 'restart_times.json'        # seconds the analysis needed to give its first second after a start (the newest few)
    previous_path = setup / 'colours_previous.json'  # {match, profile (archived copy), before_mean, restarted_at, reverted}: the colours before "팀 색 다시 찍기"
    profile_path = service / 'team_profile.json'
    candidates_path = service / 'team_select' / 'candidates.json'
    progress_path = service / 'team_select' / 'progress.json'          # which sample the colour pictures are reading (scripts/team_select_prepare.py --retakes)
    procs = processes or Processes()
    grab = frame_source or (lambda: grab_frame(paths()['source']))
    measure = memory or memory_free
    receiver = receiver_check or (lambda: port_open(paths()['source']))
    lock = threading.Lock()
    starts = []                                  # moments of start requests (rate limit)
    frame = {'data': None, 'at': 0.0, 'asked': 0.0, 'busy': False}
    handles = {}                                 # pid -> Popen of runs started by this server (kept so Windows handles stay valid)
    ticker = {}
    auto_tick = processes is None                # tests give fake processes and move the change on by polling

    def read_json(path):
        try:
            return json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return None

    def write_json(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix('.tmp')
        temp.write_text(json.dumps(value, ensure_ascii=False, indent=1), encoding='utf-8')
        os.replace(temp, path)

    def record(action, request, result, **extra):
        """One line per request that starts, stops or moves something: server time, the phone's address, the outcome."""
        row = {'at': now_text(), 't': round(time.time(), 1), 'action': action, 'client': client_of(request) if request is not None else None, 'result': result, **extra}
        try:
            setup.mkdir(parents=True, exist_ok=True)
            with open(actions_path, 'a', encoding='utf-8') as handle:
                handle.write(json.dumps(row, ensure_ascii=False) + '\n')
        except OSError:
            pass

    def refuse(action, request, status, text, **extra):
        record(action, request, 'refused', status=status, reason=text, **extra)
        raise HTTPException(status, text)

    def rate_ok():
        moment = time.time()
        starts[:] = [t for t in starts if moment - t < START_WINDOW]
        if len(starts) >= START_LIMIT:
            return False
        starts.append(moment)
        return True

    # ---- the clock, the direction and the automatic restart (the warm-up procedure) -------------------------------------------------
    def clock_info():
        """The match clock of /api/v1/clock (app/analyst_tags.py), read from the tag file: the kickoff is a mark made on /setup or /tag."""
        lines = []
        try:
            with open(store / 'analyst-tags' / 'tags.jsonl', encoding='utf-8') as handle:
                for line in handle:
                    try:
                        lines.append(json.loads(line))
                    except ValueError:
                        continue
        except OSError:
            pass
        match = started_match(store)
        try:
            return analyst_tags.match_clock(analyst_tags.fold(lines), time.time(), match[1] if match else None)
        except Exception:
            return {'state': 'before', 'since': None, 'now': time.time(), 'marks': []}

    def expect_before_kickoff(action, request):
        if clock_info()['state'] != 'before':
            refuse(action, request, 409, '전반이 이미 시작되어 여기서는 바꿀 수 없습니다. 팀 색이나 방향이 틀렸으면 담당자에게 연락하세요.')

    def direction_for(match):
        value = read_json(direction_path)
        if match and isinstance(value, dict) and value.get('match') == match['name'] and value.get('direction') in (1, -1):
            return value
        return None

    def kept_for(match):
        value = read_json(kept_path)
        return bool(match and isinstance(value, dict) and value.get('match') == match['name'])

    def restart_seconds():
        """"about N seconds" for a restart: the middle of the last measured ones, else the default."""
        value = read_json(times_path)
        if isinstance(value, list) and value:
            recent = sorted(float(v) for v in value[-3:])
            return int(round(recent[len(recent) // 2]))
        return DEFAULT_RESTART_SECONDS

    def measure_start(run):
        """Every start of this server is measured: seconds from the start to the first second the new run writes (a 'second' line after the newest header of
        its positions file). Before 2026-11-25 only the automatic restarts (new colours, new direction) were measured, so a match day with only the red band's
        restarts kept the default of 60 s on the page (rehearsal: 4 to 9 s)."""
        if not run or not run.get('alive') or run.get('measured') or not run.get('started_at') or not run.get('session'):
            return None
        path = store / 'alerts' / run['session'] / 'positions.jsonl'
        try:
            if path.stat().st_mtime < run['started_at']:
                return None
            with open(path, 'rb') as handle:
                handle.seek(0, 2)
                handle.seek(max(0, handle.tell() - 262144))
                lines = handle.read().decode('utf-8', errors='replace').splitlines()
        except OSError:
            return None
        kinds = []
        for line in lines:
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict):
                kinds.append(row.get('type'))
        if 'header' not in kinds or 'second' not in kinds[len(kinds) - 1 - kinds[::-1].index('header'):]:
            return None
        seconds = round(time.time() - run['started_at'])
        stored = {k: v for k, v in run.items() if k != 'alive'}
        stored.update(measured=now_text(), first_second_s=seconds if seconds <= MEASURE_UP_TO else None)
        write_json(run_path, stored)
        run.update(measured=stored['measured'], first_second_s=stored['first_second_s'])
        if seconds <= MEASURE_UP_TO:
            done = read_json(times_path)
            write_json(times_path, ((done if isinstance(done, list) else []) + [seconds])[-10:])
        return seconds

    def archive_records(session):
        """Before the kickoff only: the position record and the half-time sums made so far (warm-up, maybe with the wrong colours or direction) go to the archive,
        so the first half starts clean and the direction of the new run is the one the sums use (the sums read only the first header line of the file)."""
        archive = service / '_archive' / f"{time.strftime('%Y%m%d-%H%M%S')}-before-restart-{session}"
        moved = []
        for source in (store / 'alerts' / session / 'positions.jsonl', service / 'halftime' / session):
            if source.exists():
                archive.mkdir(parents=True, exist_ok=True)
                shutil.move(str(source), str(archive / (source.name if source.is_file() else 'halftime-' + source.name)))
                moved.append(source.name)
        return moved

    def stop_current():
        """Ends the analysis this server started (never one of the others) without a typed code (only used before the kickoff, by the colour and direction changes)."""
        procs.forget()
        run, _others = tracked(run_path, 'run')
        count = 1 if run and run.get('alive') and procs._kill(run['pid'], run['create_time']) else 0
        if run:
            run['stopped'] = now_text()
            run.pop('alive', None)
            write_json(run_path, run)
        procs.forget()
        return count

    def keep_previous(match):
        """Before "팀 색 다시 찍기": a copy of the colour choice in use goes to the archive (the new choice overwrites team_profile.json), with the own mean
        of this moment, so that "이전 팀 색으로 되돌리기" can bring it back and the page can tell when the new colours read fewer own players."""
        profile = profile_for(match)
        if not profile:
            return None
        archive = service / '_archive' / f"{time.strftime('%Y%m%d-%H%M%S')}-before-recolour-{match['name']}"
        archive.mkdir(parents=True, exist_ok=True)
        shutil.copy2(profile_path, archive / 'team_profile.json')
        current, mean, count = own_counts(store / 'alerts' / match['name'] / 'positions.jsonl')
        value = {'match': match['name'], 'at': now_text(), 'profile': str((archive / 'team_profile.json').relative_to(service)).replace('\\', '/'),
                 'profile_created': profile['created'], 'note': profile.get('note'), 'before_now': current, 'before_mean': mean, 'before_seconds': count,
                 'restarted_at': None, 'reverted': None}
        write_json(previous_path, value)
        return value

    def previous_for(match):
        value = read_json(previous_path)
        return value if match and isinstance(value, dict) and value.get('match') == match['name'] else None

    def read_job(match=None):
        match = match or current_match()
        value = read_json(job_path)
        return value if match and isinstance(value, dict) and value.get('match') == match['name'] else None

    def job_text(job):
        wait = restart_seconds()
        phase = job.get('phase')
        if job.get('kind') == 'revert' and phase == 'starting':
            return f'이전 팀 색으로 분석이 다시 시작되는 중입니다. 약 {wait}초 걸립니다.'
        if job.get('kind') == 'recolour':
            if phase == 'photos':
                return retake_text(read_json(progress_path)) or '팀 색 사진을 만드는 중입니다. 약 1분 30초 걸립니다.'
            if phase == 'choose':
                return f'새 사진에서 우리 팀을 고르세요. 고르면 분석이 저절로 다시 시작됩니다(약 {wait}초 걸립니다).'
        if phase == 'starting':
            return f'분석이 다시 시작되는 중입니다. 약 {wait}초 걸립니다.'
        if phase == 'done':
            return f"다시 시작했습니다. 걸린 시간 {job.get('seconds')}초."
        return job.get('text') or ''

    def advance():
        """Moves a change on by itself: photos made -> choose -> (colour chosen) the analysis starts again with the new colours -> its first second = done, the seconds are measured.
        Called by every poll of the page and by a small thread while a change runs."""
        with lock:
            match = current_match()
            job = read_job(match)
            if not job or job.get('phase') in (None, 'done', 'failed'):
                return job

            def save(**change):
                job.update(change)
                write_json(job_path, job)
            if job['phase'] == 'photos':
                procs.forget()
                prep, prep_others = tracked(prepare_path, 'prepare')
                if (prep and prep.get('alive')) or prep_others:
                    return job
                found = candidates_for(match)
                if found and found.get('ok') and len(found.get('groups') or []) >= 2 and found['created'] >= job['started']:
                    save(phase='choose')
                else:
                    save(phase='failed', text='사진을 만들지 못했습니다. 영상이 들어오는지 보고 "팀 색 다시 찍기"를 다시 누르세요.')
            if job['phase'] == 'choose':
                profile, found = profile_for(match), candidates_for(match)
                if profile and found and profile['created'] >= found['created'] and profile['created'] >= job['started']:
                    try:
                        moved = archive_records(match['name'])
                        result = launch_run(None, 'auto_restart', restart_direction(read_json(run_path), match) or job['direction'])
                        save(phase='starting', launched_at=time.time(), archived=moved, direction=result['direction'])
                        previous = previous_for(match)
                        if previous and not previous.get('reverted'):
                            write_json(previous_path, {**previous, 'restarted_at': time.time()})      # the new colours are judged a minute after this
                    except HTTPException as error:
                        save(phase='failed', text=str(error.detail) + ' "분석 다시 시작"을 눌러 이어 가세요.')
            if job['phase'] == 'starting':
                run = read_json(run_path)
                live, _ = tracked(run_path, 'run')
                measured = measure_start(live)                              # written to restart_times.json there, once per start
                _, _, count = own_counts(store / 'alerts' / match['name'] / 'positions.jsonl')
                if count > 0:
                    seconds = measured if measured is not None else (live or {}).get('first_second_s') or round(time.time() - job['launched_at'])
                    save(phase='done', seconds=seconds, finished=now_text())
                    record('restart_done', None, 'ok', kind=job['kind'], seconds=seconds, session=match['name'])
                elif time.time() - job['launched_at'] > 300 or not (run and tracked(run_path, 'run')[0].get('alive')):
                    save(phase='failed', text='분석이 다시 켜지지 않았습니다. 담당자에게 연락하세요.')
            return job

    def keep_ticking():
        """While a change runs, a small thread keeps it moving even when no page is open (the page also moves it at every poll)."""
        if not auto_tick or (ticker.get('thread') is not None and ticker['thread'].is_alive()):
            return

        def loop():
            while True:
                time.sleep(1.0)
                try:
                    job = advance()
                except Exception:
                    job = None
                if not job or job.get('phase') in (None, 'done', 'failed'):
                    return
        ticker['thread'] = threading.Thread(target=loop, name='setup-job', daemon=True)
        ticker['thread'].start()

    # ---- facts --------------------------------------------------------------------------------------------------------------------
    def current_match():
        value = read_json(match_path)
        return value if isinstance(value, dict) and MATCH_NAME.match(str(value.get('name', ''))) else None

    def owned(value, kind):
        """Whether the process of a record this server wrote is still that process: same number, same start time (a number used again by another program is not),
        and its command line names this store (and, for a run, the run folder of the record). An unreadable command line leaves the start-time check alone."""
        if not (value and isinstance(value.get('pid'), int)):
            return False
        if not procs._alive(value['pid'], value.get('create_time', 0)):
            return False
        folder = Path(value['log']).parent if kind == 'run' and value.get('log') else None
        belongs = command_belongs(procs._cmdline(value['pid']), store, folder)
        return belongs is not False

    def tracked(path, kind):
        """The record of a process this server started, with 'alive' (only when it is still that process, see owned()); every other process of the same kind on
        this computer (a terminal, another review server, another store) is in 'others'. Only the first is ever ended by this server; the others only block a start."""
        value = read_json(path)
        if value and isinstance(value.get('pid'), int):
            value['alive'] = owned(value, kind)
        found = procs.of(kind)
        mine = set()
        if value and isinstance(value.get('pid'), int):
            folder = Path(value['log']).parent if kind == 'run' and value.get('log') else None
            # alive, or the scan (kept up to 2 s) still lists the record's own process that has just ended: never "another" analysis
            if value.get('alive') or any(p['pid'] == value['pid'] and command_belongs(p.get('args'), store, folder) for p in found):
                mine = {value['pid']}
        grew = True
        while mine and grew:                                   # the venv python.exe starts the real python as its child: both carry the script name
            before = len(mine)
            mine |= {p['pid'] for p in found if p.get('ppid') in mine}
            grew = len(mine) > before
        others = [p for p in found if p['pid'] not in mine]
        return value, others

    def note_death(run):
        """A run that ended without a stop request is written down once."""
        if run and not run.get('alive') and not run.get('stopped') and not run.get('died_noted'):
            record('run_died', None, 'noted', session=run.get('session'), pid=run.get('pid'), started=run.get('started'))
            stored = {k: v for k, v in run.items() if k != 'alive'}
            stored['died_noted'] = now_text()
            write_json(run_path, stored)
            run['died_noted'] = stored['died_noted']

    def profile_for(match):
        """The saved colour choice when it was made for this match (after it was named), else None."""
        profile = read_json(profile_path)
        if not match or not isinstance(profile, dict) or not isinstance(profile.get('created'), str):
            return None
        return profile if profile['created'] >= match['created'] else None

    def candidates_for(match):
        value = read_json(candidates_path)
        if not match or not isinstance(value, dict) or not isinstance(value.get('created'), str):
            return None
        return value if value['created'] >= match['created'] else None

    def kick_frame():
        if frame['busy'] or time.time() - frame['asked'] < FRAME_EVERY:
            return
        frame['busy'], frame['asked'] = True, time.time()

        def work():
            try:
                data = grab()
                if data:
                    frame['data'], frame['at'] = data, time.time()
            finally:
                frame['busy'] = False
        threading.Thread(target=work, daemon=True).start()

    def video_now():
        """Whether the stream gives pictures now; asks once more when the last picture is old."""
        if frame['data'] and time.time() - frame['at'] < FRAME_FRESH:
            return True
        data = grab()
        if data:
            frame['data'], frame['at'] = data, time.time()
            return True
        return False

    def second_half_direction(session):
        """The direction of the newest second-half command of the session (<session>/control.jsonl), or None before the switch."""
        direction = None
        try:
            lines = (store / 'alerts' / session / 'control.jsonl').read_text(encoding='utf-8').splitlines()
        except (OSError, TypeError):
            lines = []
        for line in lines:
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict) and row.get('cmd') == 'second_half' and row.get('direction') in (1, -1):
                direction = row['direction']
        return direction

    def restart_direction(run, match=None):
        """The one rule for every start again of the same match (red band, /setup restart, the start button, the restart after new colours):
        1. after the switch to the second half: the second-half direction (the run turns round at half time and does not read old commands again);
        2. else the direction a person confirmed last for this match (direction.json, confirmed): 2026-11-25 rehearsal, the run was off when "오른쪽"
           was confirmed and the red band started it again with the temporary direction of the warm-up;
        3. else the direction of the last run (the temporary one, still to be confirmed)."""
        match = match or current_match()
        session = (run or {}).get('session') or (match or {}).get('name')
        second = second_half_direction(session) if session else None
        if second in (1, -1):
            return second
        saved = direction_for(match)
        if saved and saved.get('confirmed') and (not run or run.get('session') == saved.get('match')):
            return saved['direction']
        return (run or {}).get('direction')

    def state():
        match = current_match()
        today = 'match-' + time.strftime('%Y%m%d')
        kick_frame()
        video = bool(frame['data']) and time.time() - frame['at'] < FRAME_FRESH
        receiving = receiver()
        recorder = bool(procs.of('recorder'))
        run, run_others = tracked(run_path, 'run')
        note_death(run)
        measure_start(run)
        prep, prep_others = tracked(prepare_path, 'prepare')
        run_alive = bool(run and run.get('alive')) or bool(run_others)
        prep_alive = bool(prep and prep.get('alive')) or bool(prep_others)
        profile = profile_for(match)
        candidates = candidates_for(match)
        lines = read_json(lines_path)
        lines = lines if lines and match and lines.get('match') == match['name'] else None
        ram, vram = measure()
        out = {'suggested_name': today, 'match': {'name': match['name'], 'created': match['created'], 'confirm_hint': match['name'][-4:]} if match else None,
               'today_exists': (store / 'alerts' / today).exists()}
        if not receiving:
            out['video'] = {'state': 'problem', 'text': '영상 받는 프로그램이 꺼져 있습니다. 담당자에게 연락하세요.'}
        elif not video:
            out['video'] = {'state': 'wait', 'text': '영상이 아직 안 들어옵니다. 휴대폰에서 송출을 시작하세요.'}
        else:
            out['video'] = {'state': 'ok', 'text': '영상이 들어오고 있습니다.'}
        out['video']['recording'] = recorder
        out['lines'] = {'answer': (lines or {}).get('answer'), 'can_draw': video}
        pending = bool(candidates and profile and candidates.get('ok') and candidates['created'] > profile['created'])   # usable pictures made again after the choice
        if prep_alive:
            again = retake_text(read_json(progress_path))
            colours = {'state': 'making', 'text': again or '사진을 만드는 중입니다. 약 1분 30초 걸립니다.', 'retake': bool(again)}
        elif profile and not pending:
            note = (profile.get('note') or '우리 팀을 골랐습니다.').replace('사진 왼쪽', '첫째 묶음').replace('사진 오른쪽', '둘째 묶음')   # the words of this page
            colours = {'state': 'ok', 'text': note}
        elif candidates and candidates.get('ok') and len(candidates.get('groups') or []) >= 2:
            fewest = min(int(g.get('people') or 0) for g in candidates['groups'])
            many = len(candidates['groups']) > 2
            colours = {'state': 'choose', 'text': '묶음 중에서 우리 팀과 상대 팀을 하나씩 누르세요.' if many else '두 묶음 중 우리 팀 쪽을 누르세요.', 'created': candidates['created'],
                       'many': many, 'tries': len(candidates.get('attempts') or []) or None, 'clear': candidates.get('clear'),
                       'weak': bool(candidates.get('weak')), 'few_people': fewest < FEW_PICTURE_PEOPLE, 'fewest': fewest,
                       'groups': [{'colour': g.get('colour_text'), 'people': g.get('people'), 'urls': [f'/team-select-files/{n}' for n in g.get('images', [])]} for g in candidates['groups']]}
            preview = reader_preview(candidates)                # the same rule the run applies at its start (Small-box team reader ON/OFF)
            colours['reader_on'] = None if preview is None else bool(preview[0])
            colours['reader_line'] = None if preview is None else preview[1]
            if preview is not None and not preview[0]:
                earlier = previous_for(match)                   # "이전 팀 색" exists only after "팀 색 다시 찍기"
                colours['reader_text'] = WEAK_PICTURES_TEXT if earlier and not earlier.get('reverted') else '이 사진으로는 두 팀 색 구분이 약합니다. 다시 찍으세요.'
        elif candidates:
            colours = {'state': 'retry', 'text': '선수가 잘 안 보여 사진을 못 나눴습니다. 선수들이 경기장에 들어온 뒤 다시 누르세요.'}
        elif prep and not prep.get('alive') and prep.get('match') == (match or {}).get('name'):
            colours = {'state': 'retry', 'text': '사진을 만들지 못했습니다. 영상이 들어오는지 보고 다시 누르세요.'}
        else:
            colours = {'state': 'start', 'text': '양 팀 선수들이 조끼를 입고 경기장에 퍼져 있을 때 누르세요(킥오프 직전이 좋습니다). 1분 동안 영상을 봅니다.'}
        out['colours'] = colours
        memory = {'ram_gb': None if ram is None else round(ram, 1), 'vram_gb': None if vram is None else round(vram, 1)}
        if (ram is not None and ram < RAM_BLOCK_GB) or (vram is not None and vram < VRAM_BLOCK_GB):
            memory['state'], memory['text'] = 'block', '컴퓨터 메모리가 모자라 시작할 수 없습니다. 담당자에게 연락하세요.'
        elif (ram is not None and ram < PROJECT_RAM_GB) or (vram is not None and vram < PROJECT_VRAM_GB):
            low_gb = ram if (ram is not None and ram < PROJECT_RAM_GB) else vram       # the value that is under the rule (the start is allowed: it is not under the block values)
            memory['state'], memory['text'] = 'low', f'메모리 여유가 적습니다({low_gb:.1f} GB). 분석은 시작할 수 있습니다. 화면이 느려지면 담당자에게 연락하세요.'
        else:
            memory['state'], memory['text'] = 'ok', '메모리 여유 충분'
        out['memory'] = memory
        same_match = bool(run and match and run.get('session') == match['name'])
        analysis = {'running': run_alive, 'mine': bool(run and run.get('alive')), 'session': (run or {}).get('session'), 'started': (run or {}).get('started'),
                    'direction': (run or {}).get('direction'), 'confirm_hint': ((run or {}).get('session') or '')[-4:] or None}
        if run_others and not analysis['mine']:
            analysis['other'] = True                                # not started by this server: it is never stopped from here, and no start is taken while it runs
            analysis['text'] = OTHER_RUN_TEXT
        if same_match and not run_alive:
            analysis['ended'] = 'stopped' if run.get('stopped') else 'died'
            analysis['restart_direction'] = restart_direction(run, match)
            analysis['text'] = ('분석을 멈췄습니다.' if run.get('stopped') else '분석이 스스로 꺼졌습니다.') + ' "분석 다시 시작"을 누르면 같은 경기로 이어집니다.'
        out['analysis'] = analysis
        check = {}
        if same_match:
            first, _ = read_log(run.get('log', ''))
            mode = reader_mode(first)
            check['reader'] = mode
            check['reader_text'] = {'on': '조끼 색으로 구분 중', 'off': '기본 방식으로 구분 중'}.get(mode, '구분 방식을 읽는 중')
            check['colours_today'] = bool(profile) and f"Team colours from the coach's choice ({profile['created']})" in first
            current, mean, count = own_counts(store / 'alerts' / run['session'] / 'positions.jsonl')
            check.update({'own_now': current, 'own_mean': mean, 'seconds': count})
            age = time.time() - run.get('started_at', time.time())
            check['few'] = run_alive and age > 60 and mean is not None and mean < FEW_PLAYERS
            check['waiting'] = run_alive and count == 0
        out['check'] = check
        clock = clock_info()
        saved = direction_for(match)
        shown = saved or ({'direction': (run or {}).get('direction'), 'confirmed': False} if run_alive and (run or {}).get('direction') in (1, -1) else None)
        out['clock'] = {'state': clock['state'], 'marks': clock['marks']}
        out['direction'] = {'value': shown['direction'] if shown else None, 'confirmed': bool(shown and shown.get('confirmed')), 'running': (run or {}).get('direction') if run_alive else None}
        out['colours_kept'] = kept_for(match)
        previous = previous_for(match)
        if previous:
            own_run = bool(run and run.get('alive'))
            mean = (out['check'] or {}).get('own_mean')
            judged = bool(previous.get('restarted_at') and time.time() - previous['restarted_at'] >= RECOLOUR_LOOK_AFTER and own_run
                          and (run or {}).get('started_at', 0) >= previous['restarted_at'] - 5)
            worse = judged and not previous.get('reverted') and recolour_worse(previous.get('before_mean'), mean)
            out['colours_previous'] = {'available': not previous.get('reverted'), 'reverted': previous.get('reverted'), 'note': previous.get('note'),
                                       'before_mean': previous.get('before_mean'), 'judged': judged, 'worse': bool(worse), 'label': REVERT_LABEL,
                                       'text': f"다시 찍은 팀 색으로 우리 팀이 {mean:g}명만 잡힙니다. '{REVERT_LABEL}'를 누르세요." if worse else None}
        else:
            out['colours_previous'] = None
        job = advance() if match else None
        if job:
            out['job'] = {'kind': job.get('kind'), 'phase': job.get('phase'), 'text': job_text(job), 'seconds': job.get('seconds'),
                          'elapsed': round(time.time() - job['launched_at']) if job.get('phase') == 'starting' and job.get('launched_at') else None}
        else:
            out['job'] = None
        out['restart_seconds'] = restart_seconds()
        return out

    # ---- pages --------------------------------------------------------------------------------------------------------------------
    def page(name, media_type):
        def serve():
            path = root / name
            if not path.is_file():
                raise HTTPException(404)
            return FileResponse(path, media_type=media_type, headers={'Cache-Control': 'no-store'}) if media_type else FileResponse(path, headers={'Cache-Control': 'no-store'})
        return serve
    for route, (name, media_type) in PAGES.items():
        app.get(route)(page(name, media_type))

    @app.get('/api/v1/setup')
    def setup_state():
        return state()

    @app.get('/api/v1/setup/lines.jpg')
    def setup_lines_picture():
        kick_frame()
        if not frame['data'] or time.time() - frame['at'] > FRAME_FRESH:
            raise HTTPException(503, '영상이 없습니다')
        try:
            data = draw_lines(frame['data'], paths()['calibrations'])
        except Exception:
            data = None
        if not data:
            raise HTTPException(503, '선을 그리지 못했습니다')
        return Response(data, media_type='image/jpeg', headers={'Cache-Control': 'no-store'})

    @app.post('/api/v1/setup/match')
    def setup_match(data: MatchChoice, request: Request):
        name = data.name.strip()
        if not MATCH_NAME.match(name):
            refuse('match', request, 400, '경기 이름은 영어 소문자, 숫자, - 로 3~40자입니다. 예: match-20261125')
        if data.mode not in ('new', 'continue'):
            refuse('match', request, 400, 'Bad mode')
        with lock:
            procs.forget()
            run, others = tracked(run_path, 'run')
            prep, prep_others = tracked(prepare_path, 'prepare')
            if (run and run.get('alive')) or (prep and prep.get('alive')):
                refuse('match', request, 409, '분석이나 사진 만들기가 돌고 있어 경기를 바꿀 수 없습니다. 먼저 분석을 멈추세요.', name=name)
            # a process started from a terminal on THIS store still holds the match; one of another store (another review server, a test) does not
            if any(command_belongs(p.get('args'), store) for p in others + prep_others):
                refuse('match', request, 409, '이 경기 기록에 쓰는 분석이나 사진 만들기가 다른 곳에서 돌고 있어 경기를 바꿀 수 없습니다. 담당자에게 연락하세요.', name=name)
            match = current_match()
            exists = (store / 'alerts' / name).exists() or bool(match and match['name'] == name)
            if data.mode == 'continue':
                if not exists:
                    refuse('match', request, 404, '그 이름의 경기가 없습니다.', name=name)
                if match and match['name'] == name:
                    record('match_continue', request, 'ok', name=name)
                    return {'match': match, 'moved': []}
                value = {'name': name, 'created': now_text(), 'continued': True}
                write_json(match_path, value)
                record('match_continue', request, 'ok', name=name)
                return {'match': value, 'moved': []}
            if exists:
                refuse('match', request, 409, '같은 이름의 경기가 이미 있습니다. "이어서 하기" 또는 다른 이름을 고르세요.', name=name)
            if not confirm_ok(name, data.confirm):
                refuse('match', request, 400, f'확인 칸에 경기 이름의 마지막 네 글자({name[-4:]})를 넣어 주세요.', name=name)
            stamp = time.strftime('%Y%m%d-%H%M%S')
            archive = service / '_archive' / f'{stamp}-before-{name}'
            moved = []
            for source in (profile_path, service / 'team_select', match_path, lines_path):
                if source.exists():
                    archive.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(source), str(archive / source.name))
                    moved.append(source.name)
            for leftover in (run_path, prepare_path):                  # records of finished processes go along (a live one was refused above)
                if leftover.exists():
                    archive.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(leftover), str(archive / leftover.name))
            (store / 'alerts' / name).mkdir(parents=True, exist_ok=True)
            value = {'name': name, 'created': now_text(), 'archive': archive.name if moved else None}
            write_json(match_path, value)
            record('match_new', request, 'ok', name=name, moved=moved, archive=value['archive'])
            return {'match': value, 'moved': moved}

    @app.post('/api/v1/setup/lines')
    def setup_lines(data: LinesAnswer):
        if data.answer not in ('ok', 'bad', 'skip'):
            raise HTTPException(400, 'Bad answer')
        match = current_match()
        if not match:
            raise HTTPException(409, '먼저 새 경기를 시작하세요.')
        value = {'match': match['name'], 'answer': data.answer, 'at': now_text()}
        write_json(lines_path, value)
        return value

    @app.post('/api/v1/setup/team-photos')
    def setup_team_photos(request: Request):
        with lock:
            procs.forget()
            match = current_match()
            if not match:
                refuse('team_photos', request, 409, '먼저 새 경기를 시작하세요.')
            run, others = tracked(run_path, 'run')
            if run and run.get('alive'):
                refuse('team_photos', request, 409, '분석이 돌고 있어 사진을 만들 수 없습니다. 팀 색을 바꾸려면 먼저 분석을 멈추세요.')
            if others:
                refuse('team_photos', request, 409, OTHER_RUN_TEXT, others=[p['pid'] for p in others])
            prep, prep_others = tracked(prepare_path, 'prepare')
            if (prep and prep.get('alive')) or prep_others:
                return {'started': False, 'running': True}
            if not (REPO / 'yolo11n.pt').is_file():                     # the default detector of the script; never let it be fetched from the internet
                refuse('team_photos', request, 409, '사진을 만들 프로그램 파일이 없습니다. 담당자에게 연락하세요.')
            if not rate_ok():
                refuse('team_photos', request, 429, '너무 자주 눌렀습니다. 1분 뒤에 다시 누르세요.')
            if not video_now():
                refuse('team_photos', request, 409, '영상이 들어오지 않아 사진을 만들 수 없습니다. 휴대폰 송출을 확인하세요.')
            command = prepare_command(store)
            started = procs._launch(command, setup / 'prepare.log', REPO)
            handles[started['pid']] = started.get('handle')
            write_json(prepare_path, {'pid': started['pid'], 'create_time': started['create_time'], 'match': match['name'], 'started': now_text()})
            record('team_photos', request, 'ok', pid=started['pid'], match=match['name'])
            procs.forget()
            return {'started': True}

    def launch_run(request, action, direction, confirmed=None):
        """Starts the run of the current match (the lock is held by the caller). confirmed: True when the direction was chosen by a person, False when it is only
        the temporary one of the warm-up start, None when the direction file is left as it is (a restart)."""
        procs.forget()
        match = current_match()
        if not match:
            refuse(action, request, 409, '먼저 새 경기를 시작하세요.')
        run, others = tracked(run_path, 'run')
        if run and run.get('alive'):
            refuse(action, request, 409, '분석이 이미 돌고 있습니다.')
        if others:                                               # one GPU analysis at a time on this computer (wiki/gpu-memory-rules.md)
            refuse(action, request, 409, OTHER_RUN_TEXT, others=[p['pid'] for p in others])
        prep, prep_others = tracked(prepare_path, 'prepare')
        if (prep and prep.get('alive')) or prep_others:
            refuse(action, request, 409, '팀 색 사진을 만드는 중입니다. 끝난 뒤 누르세요.')
        profile = profile_for(match)
        if not profile:
            refuse(action, request, 409, '이 경기의 팀 색을 아직 고르지 않았습니다. 팀 색을 먼저 고르세요.')
        newer = candidates_for(match)
        if newer and newer.get('ok') and newer['created'] > profile['created']:
            refuse(action, request, 409, '팀 색 사진을 새로 만들었습니다. 새 사진에서 우리 팀을 먼저 고르세요.')
        if not receiver():
            refuse(action, request, 409, '영상 받는 프로그램이 꺼져 있습니다. 담당자에게 연락하세요.')
        ram, vram = measure()
        if (ram is not None and ram < RAM_BLOCK_GB) or (vram is not None and vram < VRAM_BLOCK_GB):
            refuse(action, request, 409, '컴퓨터 메모리가 모자라 시작할 수 없습니다. 담당자에게 연락하세요.')
        if not rate_ok():
            refuse(action, request, 429, '너무 자주 눌렀습니다. 1분 뒤에 다시 누르세요.')
        if not video_now():
            refuse(action, request, 409, '영상이 들어오지 않아 시작할 수 없습니다. 휴대폰에서 송출을 시작하세요.')
        p = paths()
        session = match['name']
        folder = run_folder(p['run_root'], session)
        folder.mkdir(parents=True, exist_ok=True)
        (store / 'alerts' / session).mkdir(parents=True, exist_ok=True)
        command = analysis_command(store, session, direction, p)
        started = procs._launch(command, folder / 'run.log', REPO)
        handles[started['pid']] = started.get('handle')
        write_json(run_path, {'pid': started['pid'], 'create_time': started['create_time'], 'match': session, 'session': session,
                              'direction': direction, 'started': now_text(), 'started_at': time.time(), 'log': str(folder / 'run.log'),
                              'ram_gb': None if ram is None else round(ram, 1), 'vram_gb': None if vram is None else round(vram, 1)})
        record(action, request, 'ok', session=session, direction=direction, pid=started['pid'])
        if confirmed is not None:
            write_json(direction_path, {'match': session, 'direction': direction, 'confirmed': confirmed, 'at': now_text()})
        procs.forget()
        return {'started': True, 'session': session, 'direction': direction}

    @app.post('/api/v1/setup/start')
    def setup_start(data: StartRun, request: Request):
        """The warm-up start (no direction: the one already chosen for this match, else the temporary one) or a start with a direction chosen by a person."""
        if data.direction is not None and data.direction not in (1, -1):
            refuse('start', request, 400, 'Bad direction')
        with lock:
            match = current_match()
            saved = direction_for(match)
            if data.direction is not None:
                return launch_run(request, 'start', data.direction, confirmed=True)
            second = second_half_direction(match['name']) if match else None
            if second in (1, -1):                                   # after the switch to the second half: the second-half direction, the first-half choice stays as it was
                return launch_run(request, 'start', second)
            if saved:
                return launch_run(request, 'start', saved['direction'], confirmed=bool(saved.get('confirmed')))
            return launch_run(request, 'start', TEMPORARY_DIRECTION, confirmed=False)

    # ---- just before the kickoff: keep the colours, take the colour pictures again, choose the direction -------------------------------------------------
    @app.post('/api/v1/setup/kickoff/colours-keep')
    def setup_colours_keep(request: Request):
        with lock:
            match = current_match()
            if not match:
                refuse('colours_keep', request, 409, '먼저 새 경기를 시작하세요.')
            expect_before_kickoff('colours_keep', request)
            run, others = tracked(run_path, 'run')
            if not ((run and run.get('alive')) or others):
                refuse('colours_keep', request, 409, '분석이 꺼져 있어 팀 색을 확인할 수 없습니다. 먼저 분석을 켜세요.')
            current, mean, count = own_counts(store / 'alerts' / match['name'] / 'positions.jsonl')
            write_json(kept_path, {'match': match['name'], 'at': now_text(), 'own_now': current, 'own_mean': mean})
            record('colours_keep', request, 'ok', own_now=current, own_mean=mean)
            return {'kept': True}

    @app.post('/api/v1/setup/kickoff/recolour')
    def setup_recolour(request: Request):
        """The analysis is stopped (the colour pictures are not made while it runs), the pictures are made again, and when the own team is chosen the analysis starts
        again by itself with the new colours (advance()). Only before the kickoff."""
        with lock:
            procs.forget()
            match = current_match()
            if not match:
                refuse('recolour', request, 409, '먼저 새 경기를 시작하세요.')
            expect_before_kickoff('recolour', request)
            job = read_job(match)
            if job and job.get('phase') in ('photos', 'starting'):              # in 'choose' the pictures may be taken once more (P4: weak pictures)
                return {'started': False, 'job': job.get('phase')}
            prep, prep_others = tracked(prepare_path, 'prepare')
            if (prep and prep.get('alive')) or prep_others:
                return {'started': False, 'job': 'photos'}
            _run, run_others = tracked(run_path, 'run')
            if run_others:
                refuse('recolour', request, 409, OTHER_RUN_TEXT, others=[p['pid'] for p in run_others])
            if not (REPO / 'yolo11n.pt').is_file():
                refuse('recolour', request, 409, '사진을 만들 프로그램 파일이 없습니다. 담당자에게 연락하세요.')
            if not rate_ok():
                refuse('recolour', request, 429, '너무 자주 눌렀습니다. 1분 뒤에 다시 누르세요.')
            if not video_now():
                refuse('recolour', request, 409, '영상이 들어오지 않아 사진을 만들 수 없습니다. 휴대폰 송출을 확인하세요.')
            saved = direction_for(match)
            run = read_json(run_path)
            direction = (saved or {}).get('direction') or (run or {}).get('direction') or TEMPORARY_DIRECTION
            keep_previous(match)
            stopped = stop_current()
            started = procs._launch(prepare_command(store), setup / 'prepare.log', REPO)
            handles[started['pid']] = started.get('handle')
            write_json(prepare_path, {'pid': started['pid'], 'create_time': started['create_time'], 'match': match['name'], 'started': now_text()})
            write_json(job_path, {'match': match['name'], 'kind': 'recolour', 'phase': 'photos', 'started': now_text(), 'direction': direction, 'stopped_run': stopped})
            try:
                kept_path.unlink()
            except OSError:
                pass
            record('recolour', request, 'ok', pid=started['pid'], match=match['name'], stopped_run=stopped)
            procs.forget()
            keep_ticking()
            return {'started': True}

    @app.post('/api/v1/setup/kickoff/colours-revert')
    def setup_colours_revert(request: Request):
        """"이전 팀 색으로 되돌리기": the colour choice from before the last "팀 색 다시 찍기" comes back (from its archived copy) and the analysis starts again
        by itself with it (the records with the new colours go to the archive first, as for every change before the kickoff). Only before the kickoff."""
        with lock:
            procs.forget()
            match = current_match()
            if not match:
                refuse('colours_revert', request, 409, '먼저 새 경기를 시작하세요.')
            expect_before_kickoff('colours_revert', request)
            previous = previous_for(match)
            if not previous or previous.get('reverted'):
                refuse('colours_revert', request, 409, '되돌릴 이전 팀 색이 없습니다.')
            job = read_job(match)
            if job and job.get('phase') in ('photos', 'starting'):
                refuse('colours_revert', request, 409, '팀 색 사진을 만들거나 분석을 다시 시작하는 중입니다. 끝난 뒤에 누르세요.')
            prep, prep_others = tracked(prepare_path, 'prepare')
            if (prep and prep.get('alive')) or prep_others:
                refuse('colours_revert', request, 409, '팀 색 사진을 만드는 중입니다. 끝난 뒤에 누르세요.')
            _run, run_others = tracked(run_path, 'run')
            if run_others:
                refuse('colours_revert', request, 409, OTHER_RUN_TEXT, others=[p['pid'] for p in run_others])
            try:
                old = json.loads((service / previous['profile']).read_text(encoding='utf-8'))
            except (OSError, ValueError, TypeError):
                refuse('colours_revert', request, 409, '이전 팀 색 파일을 찾지 못했습니다. 담당자에게 연락하세요.')
            # the start must be possible BEFORE the running analysis is ended (else the analysis would be left off with the colours changed)
            moment = time.time()
            if len([t for t in starts if moment - t < START_WINDOW]) >= START_LIMIT:
                refuse('colours_revert', request, 429, '너무 자주 눌렀습니다. 1분 뒤에 다시 누르세요.')
            if not receiver() or not video_now():
                refuse('colours_revert', request, 409, '영상이 들어오지 않아 다시 시작할 수 없습니다. 휴대폰 송출을 확인하세요.')
            from app.team_color_profile import save_profile
            # saved as a choice made now: the pictures taken again are older than it, so the start is not refused for "new pictures to choose from"
            restored = {**old, 'created': now_text(), 'restored_from': previous['profile'], 'restored_created': old.get('created')}
            stop_current()
            save_profile(profile_path, restored)
            moved = archive_records(match['name'])
            result = launch_run(request, 'colours_revert', restart_direction(read_json(run_path), match) or TEMPORARY_DIRECTION)
            write_json(job_path, {'match': match['name'], 'kind': 'revert', 'phase': 'starting', 'started': now_text(), 'launched_at': time.time(),
                                  'direction': result['direction'], 'archived': moved})
            write_json(previous_path, {**previous, 'reverted': now_text()})
            try:
                kept_path.unlink()
            except OSError:
                pass
            keep_ticking()
            return {'reverted': True, 'direction': result['direction']}

    @app.post('/api/v1/setup/kickoff/direction')
    def setup_direction(data: DirectionChoice, request: Request):
        """The attack direction, chosen for good just before the kickoff. The running analysis already has it: nothing restarts. It has another one: the analysis is
        started again with this one (the warm-up records go to the archive first). The analysis is off: the direction is kept for its next start."""
        if data.direction not in (1, -1):
            refuse('direction', request, 400, 'Bad direction')
        with lock:
            procs.forget()
            match = current_match()
            if not match:
                refuse('direction', request, 409, '먼저 새 경기를 시작하세요.')
            expect_before_kickoff('direction', request)
            job = read_job(match)
            if job and job.get('phase') in ('photos', 'choose', 'starting'):
                refuse('direction', request, 409, '팀 색을 다시 찍는 중입니다. 끝난 뒤에 방향을 고르세요.')
            run, others = tracked(run_path, 'run')
            alive = bool(run and run.get('alive'))                 # only the analysis this server started is turned round; another one is never ended from here
            running = (run or {}).get('direction') if alive else None
            if alive and running != data.direction and others:
                refuse('direction', request, 409, OTHER_RUN_TEXT, others=[p['pid'] for p in others])
            if not alive or running == data.direction:
                write_json(direction_path, {'match': match['name'], 'direction': data.direction, 'confirmed': True, 'at': now_text()})
                record('direction', request, 'ok', direction=data.direction, restarted=False)
                return {'direction': data.direction, 'restarted': False}
            prep, prep_others = tracked(prepare_path, 'prepare')
            if (prep and prep.get('alive')) or prep_others:
                refuse('direction', request, 409, '팀 색 사진을 만드는 중입니다. 끝난 뒤에 방향을 고르세요.')
            stop_current()
            moved = archive_records(match['name'])
            result = launch_run(request, 'direction_restart', data.direction, confirmed=True)
            write_json(job_path, {'match': match['name'], 'kind': 'direction', 'phase': 'starting', 'started': now_text(), 'launched_at': time.time(), 'direction': data.direction, 'archived': moved})
            keep_ticking()
            return {'direction': data.direction, 'restarted': True, **{k: v for k, v in result.items() if k != 'direction'}}

    @app.post('/api/v1/setup/restart')
    def setup_restart(request: Request):
        """The run of the same match again, with the direction it had last (turned when the second half was switched). Scores and records go on."""
        with lock:
            run = read_json(run_path)
            match = current_match()
            if not run or not match or run.get('session') != match['name']:
                refuse('restart', request, 409, '다시 시작할 분석이 없습니다. "분석 시작"을 누르세요.')
            direction = restart_direction(run, match)
            if direction not in (1, -1):
                refuse('restart', request, 409, '공격 방향을 모릅니다. "분석 시작"에서 방향을 골라 주세요.')
            return launch_run(request, 'restart', direction)

    @app.post('/api/v1/setup/stop')
    def setup_stop(data: StopRun, request: Request):
        with lock:
            procs.forget()
            run, others = tracked(run_path, 'run')
            name = (run or {}).get('session') or ((current_match() or {}).get('name'))
            targets = [(run['pid'], run['create_time'])] if run and run.get('alive') else []
            if not targets:
                if others:                                       # another server's or a terminal's analysis: never ended from here
                    refuse('stop', request, 409, OTHER_RUN_TEXT, others=[p['pid'] for p in others])
                record('stop', request, 'nothing')
                return {'stopped': 0}
            if not confirm_ok(name, data.confirm):
                refuse('stop', request, 400, f'확인 칸에 경기 이름의 마지막 네 글자({(name or "")[-4:]})를 넣어 주세요.')
            count = sum(1 for pid, created in targets if procs._kill(pid, created))
            if run:
                run['stopped'] = now_text()
                run.pop('alive', None)
                write_json(run_path, run)
            record('stop', request, 'ok', stopped=count, session=name)
            procs.forget()
            return {'stopped': count}

    return state
