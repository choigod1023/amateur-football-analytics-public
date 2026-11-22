"""Worker of one report job (started by app/report_jobs.py): detect people, track, and build the team video report.

Usage: python scripts/run_report_job.py <job folder>

Builds the whole-half coaching review (scripts/build_review_video.py: review.mp4, review.md, events.json). Reads job.json (video, camera, team, direction, start, end, half_name, goals), writes status.json with a percent after every step and while the
detector runs, and the outputs next to it. Settings come from environment variables of the server: FOOTBALL_REPORT_FFMPEG,
FOOTBALL_REPORT_DETECTOR (yolo weights), FOOTBALL_REPORT_CLASSIFIER (team/role model.pt), FOOTBALL_REPORT_CAMERAS (json: per camera 'bg',
'shift_schedule', 'pitch_length', 'pitch_width', 'label'), FOOTBALL_REPORT_CALIBRATIONS (calibrations.json of the review store).
The camera must have a saved calibration. Steps and their share of the percent: detect 0-70, track 70-80, report 80-100.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
CHUNK_SECONDS = 60
SHARE = {'detect': (0, 70), 'track': (70, 80), 'report': (80, 100)}


def step(folder, state, name, percent=None, message=None, eta=None):
    status = {'state': state, 'step': name, 'updated': time.strftime('%Y-%m-%d %H:%M:%S')}
    if percent is not None:
        status['percent'] = int(percent)
    if message:
        status['message'] = message[:300]
    if eta is not None:
        status['eta_seconds'] = int(eta)
    tmp = folder / 'status.json.tmp'
    tmp.write_text(json.dumps(status, ensure_ascii=False), encoding='utf-8')
    os.replace(tmp, folder / 'status.json')


def fail(folder, name, text):
    step(folder, 'failed', name, None, friendly(name, text))
    raise SystemExit(1)


def friendly(name, text):
    """A short Korean reason for the dashboard; the full log stays in the step log."""
    text = (text or '').strip()
    if 'No such file' in text or 'Invalid data found' in text or 'moov atom' in text:
        return '영상 파일을 읽을 수 없습니다. 파일이 온전한지 확인해 주세요.'
    if 'No moment worth' in text or 'Fewer than 60 measured' in text:
        return '이 구간에서 보여 드릴 장면을 찾지 못했습니다. 더 긴 구간이나 선수가 잘 보이는 구간으로 다시 시도해 주세요.'
    if 'out of memory' in text.lower():
        return '메모리가 부족했습니다. 구간을 줄여서 다시 시도해 주세요.'
    if 'calibration' in text.lower():
        return '이 카메라의 경기장 보정을 사용할 수 없습니다.'
    return f'{name} 단계에서 오류가 났습니다. ' + text[-200:]


def run(folder, name, command, watch=None, total=None):
    """Run one step; while it runs, `watch()` -> fraction (0-1) keeps the percent and the remaining time up to date."""
    low, high = SHARE[name]
    step(folder, 'running', name, low)
    started = time.time()
    log = open(folder / f'{name}.log', 'w', encoding='utf-8')
    process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, text=True)
    while process.poll() is None:
        time.sleep(5)
        fraction = watch() if watch else None
        if fraction is not None:
            used = time.time() - started
            eta = used * (1 - fraction) / fraction if fraction > 0.02 else None
            step(folder, 'running', name, low + (high - low) * min(1.0, fraction), None, eta)
    log.close()
    if process.returncode != 0:
        fail(folder, name, (folder / f'{name}.log').read_text(encoding='utf-8', errors='replace'))
    step(folder, 'running', name, high)


def main():
    folder = Path(sys.argv[1])
    job = json.loads((folder / 'job.json').read_text(encoding='utf-8'))
    env = os.environ
    try:
        cameras = json.loads(Path(env['FOOTBALL_REPORT_CAMERAS']).read_text(encoding='utf-8'))
    except (KeyError, OSError, ValueError):
        fail(folder, 'setup', 'camera settings missing')
    if job['camera'] not in cameras:
        fail(folder, 'setup', f'Camera {job["camera"]} has no entry in the camera settings')
    camera = cameras[job['camera']]
    video = str(folder / job['video'])
    cache = folder / 'cache'
    python, ffmpeg = sys.executable, env.get('FOOTBALL_REPORT_FFMPEG', 'ffmpeg')
    chunks = max(1, int((job['end'] - job['start']) / CHUNK_SECONDS + 0.999))
    run(folder, 'detect', [python, str(HERE / 'cache_detections.py'), video, str(job['start']), str(job['end']), camera.get('detector_camera', job['camera']), str(cache),
                           '--model', env['FOOTBALL_REPORT_DETECTOR'], '--confidence', '0.05', '--ffmpeg', ffmpeg],
        watch=lambda: len(list(cache.glob('chunk_*.npz'))) / chunks if cache.is_dir() else 0.0)
    run(folder, 'track', [python, str(HERE / 'track_from_cache.py'), str(cache), env['FOOTBALL_REPORT_CLASSIFIER'], str(folder / 'tracks.json'), '--from-second', str(job['start'])])
    command = [python, str(HERE / 'build_review_video.py'), str(folder / 'tracks.json'), env['FOOTBALL_REPORT_CALIBRATIONS'], job['camera'], video, str(folder),
               '--team', job['team'], '--direction', str(job['direction']), '--half-name', job['half_name'], '--ffmpeg', ffmpeg]
    if job.get('goals'):
        command += ['--goals', ','.join(str(g) for g in job['goals'])]
    command += ['--detector', env['FOOTBALL_REPORT_DETECTOR']]
    if env.get('FOOTBALL_REPORT_BALL_CANDIDATES') and env.get('FOOTBALL_REPORT_BALL_RERANKER'):
        command += ['--ball-candidates', env['FOOTBALL_REPORT_BALL_CANDIDATES'], '--ball-reranker', env['FOOTBALL_REPORT_BALL_RERANKER']]
    if camera.get('pitch_length'):
        command += ['--pitch-length', str(camera['pitch_length']), '--pitch-width', str(camera['pitch_width'])]
    if camera.get('bg'):
        command += ['--reference-bg', *[str(v) for v in camera['bg']]]
    if camera.get('shift_schedule'):
        command += ['--shift-schedule', camera['shift_schedule']]
    run(folder, 'report', command)
    for leftover in (cache,):
        subprocess.run(['cmd', '/c', 'rmdir', '/s', '/q', str(leftover)], capture_output=True) if os.name == 'nt' else None
    step(folder, 'done', 'done', 100)


if __name__ == '__main__':
    try:
        main()
    except KeyError as missing:
        fail(Path(sys.argv[1]), 'setup', f'missing setting {missing}')
