"""Bounded review clips from uploads, optionally with a verified source frame.

Wall-clock analysis cannot be synchronized with a file interval. Only an
identified source frame with matching decoded pixels can be attached.
"""
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import threading
import uuid

import cv2
from app.sequence_history import read_verified_frame

ROOT = Path(__file__).resolve().parent.parent
UPLOADS = ROOT / 'uploads'
SEQUENCES = ROOT / 'sequences'
MAX_DURATION_S = 20.0
MAX_CLIP_BYTES = 50 * 1024 * 1024
MAX_TOTAL_BYTES = 1024 * 1024 * 1024
MAX_ITEMS = 50
ID = re.compile(r'^[0-9a-f]{32}$')
write_lock = threading.Lock()
LIMITATIONS = ('사용자가 지정한 검토 구간입니다. 프레임 기준 시각은 근사치이며 오디오는 저장하지 않습니다. '
               '영상 구간과 분석 결과의 동기화가 검증되지 않아 선수 위치, 지표, 코칭을 제공하지 않습니다.')


class SequenceError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status, self.message = status, message


def find_ffmpeg():
    override = os.environ.get('FOOTBALL_FFMPEG')
    if override:
        path = Path(override)
        if path.is_file(): return str(path.resolve())
        raise SequenceError(503, 'FOOTBALL_FFMPEG does not point to a file')
    local = ROOT / 'bin' / ('ffmpeg.exe' if os.name == 'nt' else 'ffmpeg')
    if local.is_file(): return str(local)
    # Existing per-workspace development binary, if present. No global install.
    dev = ROOT.parent.parent / 'work' / 'ffmpeg-local' / 'ffmpeg-9.0.2-essentials_build' / 'bin' / 'ffmpeg.exe'
    if dev.is_file(): return str(dev)
    path = shutil.which('ffmpeg')
    if path: return path
    raise SequenceError(503, 'FFmpeg not available; set FOOTBALL_FFMPEG or install project bin/ffmpeg')


def safe_source(source):
    try:
        path = Path(source)
        if UPLOADS.is_symlink() or path.is_symlink() or not path.is_file() or path.suffix.lower() != '.mp4': raise ValueError
        resolved = path.resolve(strict=True)
        resolved.relative_to(UPLOADS.resolve(strict=True))
        if resolved.parent != UPLOADS.resolve(strict=True): raise ValueError
        return resolved
    except (OSError, ValueError, TypeError):
        raise SequenceError(409, 'An uploaded MP4 must be selected')


def validate_times(start, end):
    if (isinstance(start, bool) or isinstance(end, bool) or not isinstance(start, (int, float))
            or not isinstance(end, (int, float)) or not math.isfinite(start) or not math.isfinite(end)
            or start < 0 or end <= start or end-start > MAX_DURATION_S):
        raise SequenceError(400, 'Choose a non-empty interval of at most 20 seconds')
    return float(start), float(end)


def metadata_path(identifier):
    if not isinstance(identifier, str) or not ID.fullmatch(identifier):
        raise SequenceError(404, 'Sequence not found')
    if SEQUENCES.is_symlink() or not SEQUENCES.is_dir():
        raise SequenceError(404, 'Sequence not found')
    path = SEQUENCES / identifier
    if path.is_symlink() or not path.is_dir(): raise SequenceError(404, 'Sequence not found')
    return path


def items():
    if not SEQUENCES.exists(): return []
    if SEQUENCES.is_symlink() or not SEQUENCES.is_dir(): raise SequenceError(503, 'Sequence storage unavailable')
    result = []
    for path in SEQUENCES.iterdir():
        if not ID.fullmatch(path.name) or path.is_symlink() or not path.is_dir(): continue
        meta, video = path / 'metadata.json', path / 'video.mp4'
        if meta.is_symlink() or video.is_symlink() or not meta.is_file() or not video.is_file(): continue
        try:
            item = json.loads(meta.read_text(encoding='utf-8'))
            if item.get('id') == path.name and item.get('status') == 'ready': result.append(item)
        except (OSError, ValueError, TypeError): continue
    return sorted(result, key=lambda x: x.get('created_at', ''), reverse=True)


def video_path(identifier):
    folder = metadata_path(identifier)
    video, meta = folder / 'video.mp4', folder / 'metadata.json'
    if video.is_symlink() or meta.is_symlink() or not video.is_file() or not meta.is_file():
        raise SequenceError(404, 'Sequence not found')
    try:
        item = json.loads(meta.read_text(encoding='utf-8'))
        if item.get('id') != identifier or item.get('status') != 'ready': raise ValueError
    except (OSError, ValueError, TypeError, AttributeError):
        raise SequenceError(404, 'Sequence not found')
    return video


def snapshot_path(identifier):
    folder = metadata_path(identifier)
    # Reuse the readiness and symlink checks for the clip metadata.
    video_path(identifier)
    image = folder / 'snapshot.jpg'
    if image.is_symlink() or not image.is_file(): raise SequenceError(404, 'Snapshot not found')
    return image


def create(source, start, end, created_at, *, snapshot=None):
    start, end = validate_times(start, end)
    source = safe_source(source)
    binary = find_ffmpeg()
    if not write_lock.acquire(blocking=False): raise SequenceError(409, 'Another sequence is being created')
    folder = None
    complete = False
    try:
        cap = cv2.VideoCapture(str(source))
        try:
            fps, frames = cap.get(cv2.CAP_PROP_FPS), cap.get(cv2.CAP_PROP_FRAME_COUNT)
            if not cap.isOpened() or not math.isfinite(fps) or not 1 <= fps <= 240 or not math.isfinite(frames) or frames <= 0:
                raise SequenceError(422, 'Cannot determine video duration')
            duration = frames / fps
            if start >= duration or end > duration + 0.05:
                raise SequenceError(400, 'Interval exceeds video duration (approximate)')
        finally:
            cap.release()
        SEQUENCES.mkdir(parents=True, exist_ok=True)
        if SEQUENCES.is_symlink() or not SEQUENCES.is_dir(): raise SequenceError(503, 'Sequence storage unavailable')
        # Include incomplete UUID directories in quota accounting after a crash.
        folders = [p for p in SEQUENCES.iterdir() if ID.fullmatch(p.name) and p.is_dir() and not p.is_symlink()]
        if len(folders) >= MAX_ITEMS: raise SequenceError(507, 'Sequence storage is full')
        total = sum(p.stat().st_size for folder in folders for p in (folder / 'video.mp4', folder / 'snapshot.jpg') if p.is_file() and not p.is_symlink())
        if total + MAX_CLIP_BYTES + 2_000_000 > MAX_TOTAL_BYTES: raise SequenceError(507, 'Sequence storage is full')
        identifier = uuid.uuid4().hex
        folder = SEQUENCES / identifier
        folder.mkdir(exist_ok=False)
        target = folder / 'video.mp4'
        command = [binary, '-hide_banner', '-loglevel', 'error', '-nostdin', '-ss', str(start), '-i', str(source),
                   '-t', str(end-start), '-map', '0:v:0', '-an', '-vf', r'scale=trunc(min(1920\,iw)/2)*2:-2',
                   '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '28', '-pix_fmt', 'yuv420p',
                   '-movflags', '+faststart', '-n', str(target)]
        try:
            result = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL, timeout=120, check=False,
                                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        except (OSError, subprocess.TimeoutExpired): raise SequenceError(503, 'Video encoder unavailable or timed out')
        if result.returncode != 0 or not target.is_file() or not 0 < target.stat().st_size <= MAX_CLIP_BYTES:
            raise SequenceError(422, 'Could not create a review video')
        check = cv2.VideoCapture(str(target))
        try:
            ok, frame = check.read()
            if not ok or frame is None or not frame.size: raise SequenceError(422, 'Review video has no readable frame')
        finally:
            check.release()
        item = {'id': identifier, 'start_s': start, 'end_s': end, 'status': 'ready', 'created_at': created_at,
                'players': [], 'metrics': {'team_width_m': None, 'team_length_m': None}, 'feedback': [],
                'limitations': LIMITATIONS}
        # Never infer snapshot data from the latest wall-clock analysis. A saved
        # analyzed frame must fall within this source-time range and its decoded
        # pixels must exactly match those that were analyzed.
        if snapshot is not None and start <= snapshot['source_time_s'] < end:
            image = read_verified_frame(source, snapshot)
            if image is not None:
                (folder / 'snapshot.jpg').write_bytes(image)
                item.update(players=snapshot['players'], metrics=snapshot['metrics'], feedback=snapshot['feedback'], team_colors=snapshot['team_colors'],
                            snapshot_available=True, snapshot_frame_index=snapshot['frame_index'],
                            snapshot_source_time_s=round(snapshot['source_time_s'], 3),
                            snapshot_offset_s=round(snapshot['source_time_s'] - start, 3),
                            limitations=('선수 위치와 지표는 표시된 실제 분석 프레임 한 장의 관측값입니다. '
                                         '영상과의 시간은 CFR 확인을 전제로 한 근사값이며 전체 구간의 움직임은 아닙니다. '
                                         '팀 분류·보정·가림과 화면 밖 선수를 확인하세요. 오디오는 저장하지 않습니다.'))
        (folder / 'metadata.json').write_text(json.dumps(item, ensure_ascii=False), encoding='utf-8')
        complete = True
        return item
    finally:
        if folder is not None and not complete:
            # Only files in the unique directory generated by this call are removed.
            for name in ('metadata.json', 'video.mp4', 'snapshot.jpg'):
                (folder / name).unlink(missing_ok=True)
            folder.rmdir()
        write_lock.release()
