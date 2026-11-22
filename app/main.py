import json
import os
import asyncio
import threading
import time
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

os.environ.setdefault('YOLO_CONFIG_DIR', str(Path(__file__).resolve().parent.parent / '.ultralytics'))
os.environ.setdefault('YOLO_AUTOINSTALL', 'false')

import cv2
import numpy as np
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.responses import Response, FileResponse
from pydantic import BaseModel, Field, ConfigDict
from app.movement import MovementTracker
from app.team_consensus import TeamConsensus
from app.guarded_team import classify_guarded
from app.camera_guard import CameraMotionGuard
from app.ball_detection import ball_class_id, tiled_ball_candidates
from app.formation_observation import FormationObserver, observation_feedback
from app import sequence_store
from app.sequence_history import SequenceHistory
from app.cors import configure_cors
from app.manual_tracks import ManualTracks
from app.live_bookmarks import LiveBookmarks
from app.team_suggestions import TeamSuggestions
from app.experimental_map import ExperimentalMap
from app.experimental_coaching import observations as experimental_observations
from app.training_labels import TrainingLabels

app = FastAPI(title="Football coaching prototype")
configure_cors(app)
lock = threading.Lock()
status = dict(status="idle", source=None, fps=None, latency_ms=None, message=None)
# Monotonic time of the latest frame decoded from an RTSP input. This is not
# the camera timestamp or a measure of end-to-end transmission latency.
live_input = dict(last_decoded_monotonic=None)
LIVE_STALL_SECONDS = 3.0
analysis = dict(timestamp=None, players=[], ball_candidates=[], ball_detection_available=False, calibration_status='not_configured', team_colors=dict(home=None, away=None), own_team=None, metrics=dict(team_width_m=None, team_length_m=None), movements=[], formation_changes=[], feedback=[], coaching_diagnostics=dict(state='not_started', reasons=[], warnings=[]), demo=False)
preview = dict(jpeg=None, decoded_monotonic=None, decoded_at=None)
PREVIEW_INTERVAL_S = 0.1
PREVIEW_MAX_AGE_S = 3.0
worker = None
stop_event = threading.Event()
source_lock = threading.RLock()
upload_lock = threading.Lock()
sequence_history = SequenceHistory()
source_mode = 'live'
manual_tracks = ManualTracks(ttl_s=10., snapshot_ttl_s=60.)
live_bookmarks = LiveBookmarks()
training_labels = TrainingLabels(Path(__file__).resolve().parents[3] / 'work' / 'human-labels')
manual_mode = False
last_analysis_monotonic = None
last_map_generation = None
UPLOAD_DIR = Path(__file__).resolve().parent.parent / 'uploads'
UPLOAD_MAX_BYTES = 256 * 1024 * 1024
UPLOAD_TOTAL_BYTES = 2 * 1024 * 1024 * 1024
UPLOAD_MAX_FILES = 20


class Start(BaseModel):
    source: str
    config: str = "config.json"


class SequenceRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')
    start_s: float
    end_s: float


class ManualTrackRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')
    id: str = Field(min_length=1, max_length=128)
    token: str = Field(min_length=1, max_length=128)
    snapshot_token: str = Field(min_length=1, max_length=128)
    role: Literal['player', 'referee', 'goalkeeper', 'unknown']
    team: Literal['home', 'away', 'unknown'] = 'unknown'


class TrainingLabelRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')
    token: str = Field(pattern=r'^[0-9a-f]{32}$')
    track_id: str = Field(min_length=1, max_length=128)
    role: Literal['player', 'referee', 'goalkeeper', 'spectator', 'shadow', 'duplicate', 'unknown']
    team_group: Literal['team_a', 'team_b', 'white', 'blue', 'red', 'yellow', 'other', 'unknown']
    shirt_color: Literal['white', 'blue', 'yellow', 'red', 'other', 'unknown']
    shirt_detail: str = Field(default='', max_length=120)
    only_if_new: bool = False


class RestoreTrainingLabelRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')
    token: str = Field(pattern=r'^[0-9a-f]{32}$')


class ManualTrainingBoxRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')
    token: str = Field(pattern=r'^[0-9a-f]{32}$')
    bbox: list[float] = Field(min_length=4, max_length=4)


def local_label_request(request):
    if request.client is None or request.client.host not in ('127.0.0.1', '::1'):
        raise HTTPException(403, 'Local browser only')
    if request.headers.get('origin') != f'{request.url.scheme}://{request.url.netloc}':
        raise HTTPException(403, 'Origin mismatch')


@app.post('/api/v1/training-labels/snapshot')
def freeze_training_label(request: Request):
    local_label_request(request)
    snapshot = training_labels.freeze()
    if snapshot is None:
        raise HTTPException(409, 'No recent analysis frame')
    return snapshot


@app.post('/api/v1/training-labels')
def save_training_label(data: TrainingLabelRequest, request: Request):
    local_label_request(request)
    if data.role in ('referee', 'spectator', 'shadow', 'duplicate', 'unknown') and data.team_group != 'unknown':
        raise HTTPException(422, 'Team must be unknown for this role')
    try:
        identifier = training_labels.save(data.token, data.track_id, data.role, data.team_group, data.shirt_color, data.shirt_detail, only_if_new=data.only_if_new)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {'saved': True, 'id': identifier}


@app.post('/api/v1/training-labels/manual-box')
def add_manual_training_box(data: ManualTrainingBoxRequest, request: Request):
    local_label_request(request)
    try:
        person = training_labels.add_manual_box(data.token, data.bbox)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {'token': data.token, 'person': person}


@app.post('/api/v1/training-labels/suggestions')
def suggest_training_labels(data: RestoreTrainingLabelRequest, request: Request):
    local_label_request(request)
    try:
        return {'suggestions': training_labels.suggest(data.token), 'confirmed_ids': training_labels.confirmed_ids(data.token)}
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.post('/api/v1/training-labels/restore')
def restore_training_label(data: RestoreTrainingLabelRequest, request: Request):
    local_label_request(request)
    try:
        return training_labels.restore(data.token)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.post('/api/v1/training-labels/latest')
def latest_training_label(request: Request):
    local_label_request(request)
    snapshot = training_labels.latest_pending()
    if not snapshot:
        raise HTTPException(404, 'No saved snapshot')
    return snapshot


def set_state(target, **values):
    with lock:
        target.update(values)


@app.get('/api/v1/status')
def get_status():
    with lock:
        result = dict(status)
        last_decoded = live_input['last_decoded_monotonic']
    source = result.get('source')
    is_live = bool(source and source.startswith('rtsp://'))
    stalled = False
    age = None
    if is_live and result['status'] == 'running' and last_decoded is not None:
        age = max(0., time.monotonic() - last_decoded)
        stalled = age > LIVE_STALL_SECONDS
        if stalled:
            result['message'] = '입력 지연: 새 디코딩 프레임을 기다리는 중입니다.'
    result['input_stalled'] = stalled
    result['decoded_frame_age_ms'] = round(age * 1000, 1) if age is not None else None
    if source and not source.startswith('rtsp://'):
        try:
            if Path(source).resolve().is_relative_to(UPLOAD_DIR.resolve()):
                result['source'] = '업로드 영상'
        except (OSError, ValueError):
            result['source'] = '로컬 영상'
    with source_lock:
        result['input_mode'] = source_mode
    return result


@app.get('/api/v1/source-mode')
def get_source_mode():
    with source_lock:
        return {'mode': source_mode}


@app.get('/api/v1/analysis')
def get_analysis():
    with lock:
        result = json.loads(json.dumps(analysis))
        mode = manual_mode
        stale = mode and (status['status'] != 'running' or last_analysis_monotonic is None or time.monotonic()-last_analysis_monotonic > 1.)
        map_stale = status['status'] != 'running' or last_analysis_monotonic is None or time.monotonic()-last_analysis_monotonic > 1.
        map_generation = last_map_generation
    if (map_stale or (isinstance(result.get('experimental_map'), dict) and map_generation != manual_tracks.generation())) and 'experimental_map' in result:
        result['experimental_map'] = {'status': 'stale', 'players': []}
    invalid_assignment = False
    if mode and not stale:
        for player in result['players']:
            token, team, role = manual_tracks.get(player['id'])
            if token != player.get('annotation_token'):
                player['team'], player['role'], player['annotation_token'] = 'unknown', None, None
                invalid_assignment = True
            elif team != player['team'] or role != player.get('role'):
                # Apply a just-confirmed label to its matching track immediately.
                # Existing metrics still describe the preceding frame and must
                # not be reused until the worker recomputes them.
                player['team'], player['role'] = team, role
                invalid_assignment = True
    if stale or invalid_assignment:
        if stale:
            for player in result['players']:
                player['team'], player['role'] = 'unknown', None
                if 'suggested_color_group' in player:
                    player['suggested_color_group'] = None
        result['metrics'] = dict(team_width_m=None, team_length_m=None)
        result['feedback'], result['movements'], result['formation_changes'] = [], [], []
        result['coaching_diagnostics'] = dict(state='blocked', reasons=['manual_frame_stale' if stale else 'manual_confirmation_changed'], warnings=['track_identity_unverified'])
    # Separate, explicitly provisional field: never substitute for verified coaching.
    result['experimental_feedback'] = experimental_observations(result.get('experimental_map'))
    return result


@app.get('/api/v1/manual-snapshot')
def get_manual_snapshot():
    with lock:
        ready = manual_mode and status['status'] == 'running' and last_analysis_monotonic is not None and time.monotonic()-last_analysis_monotonic <= 1.
    snapshot = manual_tracks.get_snapshot() if ready else None
    if snapshot is None:
        raise HTTPException(409, 'No recent analyzed frame available')
    return JSONResponse(content=snapshot, headers={'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'})


@app.post('/api/v1/manual-track')
def assign_manual_track(request: ManualTrackRequest):
    if (request.role in ('player', 'goalkeeper')) != (request.team in ('home', 'away')):
        raise HTTPException(400, 'A player or goalkeeper must have a team; other roles must use unknown')
    with lock:
        ready = manual_mode and status['status'] == 'running' and last_analysis_monotonic is not None and time.monotonic()-last_analysis_monotonic <= 1.
    if not ready or not manual_tracks.assign(request.snapshot_token, request.id, request.token, request.role, request.team):
        raise HTTPException(409, 'Track is no longer available for confirmation')
    return {'accepted': True, 'expires_in_s': manual_tracks.ttl_s}


@app.get('/api/v1/live-bookmarks')
def get_live_bookmarks():
    return JSONResponse({'items': live_bookmarks.list()}, headers={'Cache-Control': 'no-store'})


@app.post('/api/v1/live-bookmarks')
def add_live_bookmark(request: Request):
    origin = request.headers.get('origin')
    if origin and origin != f'{request.url.scheme}://{request.url.netloc}':
        raise HTTPException(403, 'Origin mismatch')
    with lock:
        allowed = status['status'] == 'running' and str(status.get('source') or '').startswith('rtsp://') and not stop_event.is_set()
    if not allowed:
        raise HTTPException(409, 'Live input unavailable')
    try:
        return live_bookmarks.mark()
    except ValueError as error:
        raise HTTPException(409, str(error)) from None


@app.get('/api/v1/live-bookmarks/{identifier}/frame.jpg')
def get_live_bookmark_frame(identifier: str):
    frame = live_bookmarks.image(identifier)
    if frame is None:
        raise HTTPException(404, 'Bookmark not found')
    return Response(frame, media_type='image/jpeg', headers={'Cache-Control':'no-store', 'X-Content-Type-Options':'nosniff'})


@app.get('/api/v1/sequences')
def list_sequences():
    try:
        return {'items': sequence_store.items()}
    except sequence_store.SequenceError as exc:
        raise HTTPException(exc.status, exc.message)


@app.post('/api/v1/sequences')
def create_sequence(request: SequenceRequest):
    if not upload_lock.acquire(blocking=False):
        raise HTTPException(409, 'Input is busy')
    try:
        with source_lock:
            with lock:
                source = status.get('source') if source_mode == 'file' else None
        snapshot = sequence_history.find(source, request.start_s, request.end_s)
        return sequence_store.create(source, request.start_s, request.end_s, datetime.now(timezone.utc).isoformat(), snapshot=snapshot)
    except sequence_store.SequenceError as exc:
        raise HTTPException(exc.status, exc.message)
    finally:
        upload_lock.release()


@app.get('/api/v1/sequences/{identifier}/video')
def get_sequence_video(identifier: str):
    try:
        return FileResponse(sequence_store.video_path(identifier), media_type='video/mp4',
                            headers={'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'})
    except sequence_store.SequenceError as exc:
        raise HTTPException(exc.status, exc.message)


@app.get('/api/v1/sequences/{identifier}/snapshot.jpg')
def get_sequence_snapshot(identifier: str):
    try:
        return FileResponse(sequence_store.snapshot_path(identifier), media_type='image/jpeg',
                            headers={'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'})
    except sequence_store.SequenceError as exc:
        raise HTTPException(exc.status, exc.message)


@app.get('/api/v1/frame.jpg')
def get_frame():
    with lock:
        jpeg, decoded, timestamp = preview['jpeg'], preview['decoded_monotonic'], preview['decoded_at']
        running = status['status'] == 'running' and not stop_event.is_set()
    age = time.monotonic() - decoded if decoded is not None else None
    headers = {'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'}
    if not running or jpeg is None or age is None or age < 0 or age > PREVIEW_MAX_AGE_S:
        return Response(status_code=204, headers=headers)
    headers.update({'X-Frame-Timestamp': timestamp, 'X-Frame-Age-Ms': str(round(age * 1000))})
    return Response(content=jpeg, media_type='image/jpeg', headers=headers)


def publish_preview(frame, decoded_monotonic, decoded_at, tracks=None, groups=None):
    # Only an actual frame already processed by the analysis pipeline is used.
    if time.monotonic() - decoded_monotonic > PREVIEW_MAX_AGE_S:
        return
    height, width = frame.shape[:2]
    ratio = min(1.0, 960 / width, 540 / height)
    if ratio < 1:
        frame = cv2.resize(frame, (max(1, round(width * ratio)), max(1, round(height * ratio))), interpolation=cv2.INTER_AREA)
    ok, encoded = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 65])
    if ok and encoded.nbytes <= 2_000_000:
        clean = encoded.tobytes()
        shown = clean
        if tracks:
            # Draw on a copy of this exact processed frame. This is a detection
            # overlay only; colors are unverified shirt groups, not teams.
            marked = frame.copy()
            target_h, target_w = marked.shape[:2]
            for box, track_id in tracks[:200]:
                if len(box) != 4 or not np.isfinite(box).all():
                    continue
                x1, y1, x2, y2 = (int(round(float(v) * ratio)) for v in box)
                x1, x2 = max(0, x1), min(target_w - 1, x2)
                y1, y2 = max(0, y1), min(target_h - 1, y2)
                if x2 <= x1 or y2 <= y1:
                    continue
                group = (groups or {}).get(str(track_id))
                color = (255, 180, 60) if group == 0 else (80, 105, 255) if group == 1 else (175, 175, 175)
                cv2.rectangle(marked, (x1, y1), (x2, y2), color, 1)
            success, annotated = cv2.imencode('.jpg', marked, [cv2.IMWRITE_JPEG_QUALITY, 65])
            if success and annotated.nbytes <= 2_000_000:
                shown = annotated.tobytes()
        set_state(preview, jpeg=shown, decoded_monotonic=decoded_monotonic, decoded_at=decoded_at)
        return clean  # Manual confirmation always uses the untouched image.


@app.post('/api/v1/start')
def start(request: Start):
    global worker
    if not upload_lock.acquire(blocking=False):
        raise HTTPException(409, 'Input is busy')
    try:
        with source_lock:
            return start_locked(request)
    finally:
        upload_lock.release()


def start_locked(request: Start):
    global worker, manual_mode, last_analysis_monotonic
    if request.source.startswith('rtsp://') and source_mode != 'live':
        raise HTTPException(409, 'File input is selected')
    if worker and worker.is_alive():
        raise HTTPException(409, 'Analysis is already running')
    try:
        config = json.loads(Path(request.config).read_text(encoding='utf-8'))
        validate_config(config)
    except (OSError, ValueError, KeyError, TypeError) as e:
        raise HTTPException(400, f'Invalid configuration: {e}')
    if not request.source.startswith('rtsp://') and not Path(request.source).is_file():
        raise HTTPException(400, 'Local input file not found')
    sequence_history.reset(request.source if not request.source.startswith('rtsp://') else None)
    live_bookmarks.clear_latest()
    stop_event.clear()
    manual_tracks.reset()
    with lock:
        manual_mode = config.get('manual_player_assignments', False)
        last_analysis_monotonic = None
    set_state(live_input, last_decoded_monotonic=None)
    set_state(preview, jpeg=None, decoded_monotonic=None, decoded_at=None)
    set_state(analysis, timestamp=None, players=[], ball_candidates=[], ball_detection_available=False, calibration_status='not_configured', team_colors=team_colors(config.get('team_hsv', {})), own_team=config.get('own_team', 'home'), metrics=dict(team_width_m=None, team_length_m=None), movements=[], formation_changes=[], feedback=[], coaching_diagnostics=dict(state='not_started', reasons=[], warnings=[]))
    set_state(status, status='running', source=request.source, fps=None, latency_ms=None, message='Starting')
    worker = threading.Thread(target=run, args=(request.source, config), daemon=True)
    worker.start()
    return {'started': True}


@app.post('/api/v1/stop')
def stop():
    stop_event.set()
    return {'stopping': True}


async def stop_existing():
    stop_event.set()
    existing = worker
    if existing and existing.is_alive():
        await asyncio.to_thread(existing.join, 12)
        if existing.is_alive():
            raise HTTPException(409, 'Current input is still stopping')


@app.post('/api/v1/live')
async def use_live():
    global source_mode
    if not upload_lock.acquire(blocking=False):
        raise HTTPException(409, 'An upload is in progress')
    try:
        with source_lock:
            source_mode = 'file'  # Prevent supervisor restarts while stopping.
        await stop_existing()
        with source_lock:
            source_mode = 'live'
            start_locked(Start(source='rtsp://127.0.0.1:18554/match'))
        return {'started': True, 'input_mode': 'live'}
    finally:
        upload_lock.release()


@app.post('/api/v1/upload')
async def upload_video(request: Request):
    global source_mode
    if request.headers.get('content-type', '').split(';')[0].lower() != 'video/mp4':
        raise HTTPException(415, 'Only MP4 video is accepted')
    declared = request.headers.get('content-length')
    if declared:
        try:
            if int(declared) < 1 or int(declared) > UPLOAD_MAX_BYTES:
                raise HTTPException(413, 'Video exceeds the 256 MiB limit')
        except ValueError:
            raise HTTPException(400, 'Invalid content length')
    if not upload_lock.acquire(blocking=False):
        raise HTTPException(409, 'An upload is in progress')
    temporary = None
    try:
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        current = [p for p in UPLOAD_DIR.iterdir() if p.is_file() and not p.is_symlink()]
        existing_bytes = sum(p.stat().st_size for p in current)
        if len(current) >= UPLOAD_MAX_FILES or existing_bytes >= UPLOAD_TOTAL_BYTES:
            raise HTTPException(507, 'Upload storage is full')
        temporary = UPLOAD_DIR / (uuid.uuid4().hex + '.part.mp4')
        total = 0
        with temporary.open('xb') as output:
            stream = request.stream().__aiter__()
            while True:
                try:
                    chunk = await asyncio.wait_for(stream.__anext__(), timeout=30)
                except StopAsyncIteration:
                    break
                except TimeoutError:
                    raise HTTPException(408, 'Upload stalled')
                total += len(chunk)
                if total > UPLOAD_MAX_BYTES or existing_bytes + total > UPLOAD_TOTAL_BYTES:
                    raise HTTPException(413, 'Video exceeds the upload or storage limit')
                output.write(chunk)
        if not total:
            raise HTTPException(400, 'Video is empty')
        with temporary.open('rb') as source:
            header = source.read(64)
        if len(header) < 12 or header[4:8] != b'ftyp':
            raise HTTPException(415, 'File is not a recognizable MP4')
        def check_video(path):
            capture = cv2.VideoCapture(str(path))
            try:
                if not capture.isOpened(): return False
                ok, frame = capture.read()
                return bool(ok and frame is not None and frame.size)
            finally:
                capture.release()
        if not await asyncio.to_thread(check_video, temporary):
            raise HTTPException(415, 'MP4 cannot be decoded')
        target = UPLOAD_DIR / (uuid.uuid4().hex + '.mp4')
        temporary.replace(target)
        temporary = None
        with source_lock:
            source_mode = 'file'
        try:
            await stop_existing()
            with source_lock:
                start_locked(Start(source=str(target)))
        except Exception:
            with source_lock: source_mode = 'live'
            raise
        return {'accepted': True, 'input_mode': 'file', 'source': '업로드 영상'}
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        upload_lock.release()


def validate_config(c):
    if not isinstance(c.get('bytetrack_low_score_recovery', False), bool):
        raise ValueError('bytetrack_low_score_recovery must be boolean')
    if not isinstance(c.get('experimental_map', False), bool):
        raise ValueError('experimental_map must be boolean')
    if c.get('experimental_map'):
        candidate = c.get('calibration')
        if not isinstance(candidate, dict) or candidate.get('validated') is not False or not candidate.get('camera_guard_reference') or not candidate.get('camera_guard_feature_region'):
            raise ValueError('experimental map requires unvalidated calibration and a camera guard reference and region')
    if not isinstance(c.get('preview_track_boxes', False), bool):
        raise ValueError('preview_track_boxes must be boolean')
    if not isinstance(c.get('suggest_team_clusters', False), bool):
        raise ValueError('suggest_team_clusters must be boolean')
    if not isinstance(c.get('manual_player_assignments', False), bool):
        raise ValueError('manual_player_assignments must be boolean')
    if c.get('manual_player_assignments') and c.get('temporal_team_consensus', False):
        raise ValueError('manual player assignments cannot use automatic team consensus')
    if not isinstance(c.get('formation_observation', False), bool):
        raise ValueError('formation_observation must be boolean')
    if not isinstance(c.get('ball_tiled_detection', False), bool):
        raise ValueError('ball_tiled_detection must be boolean')
    if 'ball_model_path' in c and (not isinstance(c['ball_model_path'], str) or not c['ball_model_path'].strip()):
        raise ValueError('ball_model_path must be a non-empty string')
    if c.get('team_classifier', 'median') not in ('median', 'guarded_palette'):
        raise ValueError('team_classifier must be median or guarded_palette')
    tiled_setting = c.get('tiled_detection', False)
    if not isinstance(tiled_setting, bool) and tiled_setting != 'auto':
        raise ValueError('tiled_detection must be boolean or auto')
    if not isinstance(c.get('temporal_team_consensus', False), bool):
        raise ValueError('temporal_team_consensus must be boolean')
    if not isinstance(c.get('ball_detection', False), bool):
        raise ValueError('ball_detection must be boolean')
    if c.get('own_team', 'home') not in ('home', 'away'):
        raise ValueError('own_team must be home or away')
    imgsz = c.get('image_size', 640)
    if not isinstance(imgsz, int) or isinstance(imgsz, bool) or not 320 <= imgsz <= 1920 or imgsz % 32:
        raise ValueError('image_size must be a multiple of 32 between 320 and 1920')
    refs = c.get('team_hsv', {})
    if not isinstance(refs, dict):
        raise ValueError('team_hsv must be an object')
    for team in ('home', 'away'):
        if team in refs and (not isinstance(refs[team], list) or len(refs[team]) != 3 or not all(isinstance(x, int) and not isinstance(x, bool) and 0 <= x <= limit for x, limit in zip(refs[team], (179, 255, 255)))):
            raise ValueError('invalid HSV reference')
    cal = c.get('calibration')
    if cal:
        reference = cal.get('camera_guard_reference')
        if reference is not None and (not isinstance(reference, str) or not reference or len(reference) > 4096):
            raise ValueError('camera_guard_reference must be a non-empty local image path')
        pixels = cal.get('image_size_px')
        if pixels is not None and (not isinstance(pixels, list) or len(pixels) != 2 or any(not isinstance(v, int) or isinstance(v, bool) or v <= 0 for v in pixels)):
            raise ValueError('calibration image_size_px must contain positive integer width and height')
        region = cal.get('camera_guard_feature_region')
        if region is not None:
            if reference is None or pixels is None:
                raise ValueError('camera guard feature region requires a reference and image size')
            poly = np.asarray(region, dtype=np.float32)
            if (poly.shape != (4, 2) or not np.isfinite(poly).all() or not cv2.isContourConvex(poly)
                    or abs(cv2.contourArea(poly)) < 100 or (poly < 0).any()
                    or (poly[:, 0] >= pixels[0]).any() or (poly[:, 1] >= pixels[1]).any()):
                raise ValueError('camera guard feature region must be an ordered convex quadrilateral inside the image')
        dims = cal['field_size_m']
        if len(dims) != 2 or not all(np.isfinite(float(v)) and float(v) > 0 for v in dims):
            raise ValueError('field_size_m must contain positive length and width')
        src, dst = np.asarray(cal['image_points'], dtype=np.float32), np.asarray(cal['field_points_m'], dtype=np.float32)
        if src.shape != (4, 2) or dst.shape != (4, 2) or not np.isfinite(src).all() or not np.isfinite(dst).all():
            raise ValueError('calibration needs four finite point pairs')
        if not cv2.isContourConvex(src) or not cv2.isContourConvex(dst) or abs(cv2.contourArea(src)) < 100 or abs(cv2.contourArea(dst)) < 1:
            raise ValueError('calibration points must form ordered, nondegenerate convex quadrilaterals')
        if np.any(dst < 0) or np.any(dst > np.asarray(dims)):
            raise ValueError('field points exceed field dimensions')


def team_colors(refs):
    colors = {'home': None, 'away': None}
    for team in colors:
        if team in refs:
            hsv = np.array([[refs[team]]], dtype=np.uint8)
            rgb = cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB)[0, 0]
            colors[team] = '#%02x%02x%02x' % tuple(map(int, rgb))
    return colors


def classify(frame, box, refs):
    if not all(t in refs for t in ('home', 'away')):
        return 'unknown'
    x1, y1, x2, y2 = map(int, box)
    h, w = frame.shape[:2]
    crop = frame[max(0, y1):min(h, y1 + max(1, (y2-y1)//2)), max(0, x1):min(w, x2)]
    if crop.size == 0:
        return 'unknown'
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV).reshape(-1, 3)
    # Hue is not meaningful for white/grey jerseys. Keep low-saturation pixels
    # when a reference is achromatic, but never infer a color from near-black.
    achromatic = any(refs[t][1] <= 55 for t in ('home', 'away'))
    valid = (hsv[:, 2] > 45) & ((hsv[:, 1] > 55) | achromatic)
    if valid.sum() < max(30, len(hsv) // 2):
        return 'unknown'
    hsv = hsv[valid]
    # A player's bounding box can contain mostly pitch. Compare the upper-body
    # color to adjacent pixels and abstain when the two are indistinguishable.
    # This is a conservative guard, not foreground segmentation or role detection.
    top, bottom = max(0, y1), min(h, y1 + max(1, (y2-y1)//2))
    width = max(1, x2-x1)
    left = frame[top:bottom, max(0, x1-width):max(0, min(w, x1))]
    right = frame[top:bottom, max(0, min(w, x2)):min(w, x2+width)]
    neighbors = [part.reshape(-1, 3) for part in (left, right) if part.size]
    if neighbors:
        surrounding = cv2.cvtColor(np.concatenate(neighbors).reshape(1, -1, 3), cv2.COLOR_BGR2HSV).reshape(-1, 3)
        surrounding = surrounding[(surrounding[:, 2] > 45) & ((surrounding[:, 1] > 55) | achromatic)]
        if len(surrounding) >= 30:
            foreground_median = np.median(hsv, axis=0)
            background_median = np.median(surrounding, axis=0)
            difference = np.abs(foreground_median - background_median)
            hue_difference = min(difference[0], 180 - difference[0])
            hue_unreliable = foreground_median[1] <= 55 and background_median[1] <= 55
            if (hue_unreliable or hue_difference <= 5) and difference[1] <= 20 and difference[2] <= 20:
                return 'unknown'
    # Hue wraps at 180; references must be deliberately supplied for both teams.
    scores = []
    for team in ('home', 'away'):
        ref = np.asarray(refs[team], dtype=float)
        dh = np.abs(hsv[:, 0].astype(float)-ref[0]); dh = np.minimum(dh, 180-dh)
        if achromatic:
            # As saturation approaches zero, down-weight hue rather than
            # treating arbitrary grey hue as a meaningful shirt color.
            hue_weight = np.minimum(hsv[:, 1].astype(float), ref[1]) / 255
            d = np.sqrt((dh * 2 * hue_weight)**2 + ((hsv[:, 1]-ref[1])*.30)**2 + ((hsv[:, 2]-ref[2])*.25)**2)
        else:
            d = np.sqrt((dh * 2)**2 + ((hsv[:, 1]-ref[1])*.25)**2 + ((hsv[:, 2]-ref[2])*.15)**2)
        scores.append(float(np.median(d)))
    if min(scores) > 35 or abs(scores[0]-scores[1]) < 12:
        return 'unknown'
    return ('home', 'away')[int(scores[1] < scores[0])]


def active_calibration(cal, frame_shape):
    """Refuse stale/unknown source resolution; camera motion is not detected."""
    if not cal:
        return None, 'not_configured'
    if cal.get('validated') is not True:
        return None, 'not_validated'
    size = cal.get('image_size_px')
    if not isinstance(size, list) or len(size) != 2 or any(not isinstance(v, int) or isinstance(v, bool) or v <= 0 for v in size):
        return None, 'resolution_unverified'
    if tuple(size) != (frame_shape[1], frame_shape[0]):
        return None, 'resolution_mismatch'
    return cal, 'active'


def project(point, cal):
    if not cal or cal.get('validated') is not True:
        return None, None
    src = np.array(cal['image_points'], dtype=np.float32)
    dst = np.array(cal['field_points_m'], dtype=np.float32)
    # Float32 polygon/intersection round-off can put an exact boundary point
    # a few ten-thousandths of a pixel outside. This tolerance only absorbs
    # numerical noise; it is not a license to extrapolate outside the polygon.
    if not np.isfinite(point).all() or cv2.pointPolygonTest(src, tuple(map(float, point)), True) < -.01:
        return None, None
    mat = cv2.getPerspectiveTransform(src, dst)
    p = cv2.perspectiveTransform(np.array([[point]], dtype=np.float32), mat)[0][0]
    if not np.isfinite(p).all():
        return None, None
    length, width = cal['field_size_m']
    x, y = float(p[0])/length, float(p[1])/width
    # Field bounds use an absolute 1mm tolerance, then clamp to the field.
    if not (-.001 <= float(p[0]) <= length + .001 and -.001 <= float(p[1]) <= width + .001):
        return None, None
    return round(min(1., max(0., x)), 5), round(min(1., max(0., y)), 5)


def summarize(players, team, field_size=None):
    own = [p for p in players if p['team'] == team and p['x'] is not None and p['y'] is not None]
    metrics = dict(team_width_m=None, team_length_m=None)
    if len(own) < 2 or not field_size:
        return metrics, []
    xs, ys = [p['x'] for p in own], [p['y'] for p in own]
    metrics = dict(team_width_m=round((max(ys)-min(ys))*field_size[1], 2), team_length_m=round((max(xs)-min(xs))*field_size[0], 2))
    label = '홈팀' if team == 'home' else '어웨이팀'
    feedback = [dict(observation=f"화면에서 확인된 {label} {len(own)}명의 폭은 {metrics['team_width_m']}m, 길이는 {metrics['team_length_m']}m입니다.", interpretation='화면에서 보이는 선수들의 분포를 나타냅니다.', suggestion='경기 상황과 화면 밖 선수 위치를 함께 확인해 주세요.', limitations='화면 밖 선수, 팀 분류 오류, 보정 오차가 반영되지 않아 팀 전체 대형으로 단정할 수 없습니다.')]
    return metrics, feedback


def can_compute_team_metrics(config):
    """A person color is not proof of a field-player role."""
    return config.get('manual_player_assignments', False) is True


def mask_unconfirmed_player_teams(players, config):
    """Do not present a shirt-colour guess as a verified player team."""
    if can_compute_team_metrics(config):
        return players
    return [{**player, 'team': 'unknown'} for player in players]


def coaching_diagnostics(config, players, calibration_status, metrics):
    """Explain current observation gates; never infer role or validation."""
    reasons = []
    if calibration_status != 'active':
        reasons.append('calibration_unavailable')
    refs = config.get('team_hsv', {})
    manual = config.get('manual_player_assignments', False)
    if not manual:
        # The current generic person detector cannot tell an official from a
        # field player. Validating shirt colours does not validate their role.
        reasons.append('player_roles_unverified')
    if not manual and not all(team in refs for team in ('home', 'away')):
        reasons.append('team_references_missing')
    if not manual and config.get('team_classification_validated') is not True:
        reasons.append('team_classification_unverified')
    own_team = config.get('own_team', 'home')
    localized = sum(p.get('team') == own_team and p.get('x') is not None and p.get('y') is not None for p in players)
    if localized < 2:
        reasons.append('insufficient_located_team_members')
    available = metrics.get('team_width_m') is not None and metrics.get('team_length_m') is not None
    # A manually marked calibration, even when validated at one instant, does
    # not establish that the camera stayed fixed for the current frame.
    reference = (config.get('calibration') or {}).get('camera_guard_reference')
    camera_warning = 'camera_motion_guard_limited' if reference else 'camera_motion_unchecked'
    return {'state': 'observation_available' if available and not reasons else 'blocked', 'reasons': reasons,
            # Current person detector does not classify players versus officials.
            'warnings': (['track_identity_unverified'] if manual else ['player_roles_unverified']) +
                        ['offscreen_players_unobserved', camera_warning]}


def ball_candidates_from_boxes(boxes, width, height):
    """Generic sports-ball *image* candidates; not a tracked or pitch position."""
    if boxes is None or width <= 0 or height <= 0:
        return []
    result = []
    for box, confidence in zip(boxes.xyxy.cpu().numpy(), boxes.conf.cpu().numpy()):
        x1, y1, x2, y2 = map(float, box)
        if not np.isfinite([x1, y1, x2, y2, confidence]).all():
            continue
        x1, x2 = max(0., x1), min(float(width), x2)
        y1, y2 = max(0., y1), min(float(height), y2)
        if x1 >= x2 or y1 >= y2:
            continue
        result.append({'bbox_image_norm': [round(x1/width, 5), round(y1/height, 5), round(x2/width, 5), round(y2/height, 5)], 'confidence': round(float(confidence), 4)})
    return result


def reset_segment_state(tiled, model, suggestions, experimental_map):
    """Discard temporal assumptions after an explicitly signalled cut."""
    if tiled is not None:
        tiled.reset()
    else:
        predictor = getattr(model, 'predictor', None)
        for tracker in getattr(predictor, 'trackers', ()) or ():
            tracker.reset()
    if experimental_map is not None:
        experimental_map.clear()
    return TeamSuggestions() if suggestions is not None else None


def run(source, config):
    global last_analysis_monotonic, last_map_generation
    cap = None
    reader = None
    cal_config = config.get('calibration') or {}
    reference = cal_config.get('camera_guard_reference')
    # A user-selected region can contain static stadium features when the
    # calibrated pitch itself has too little texture for a camera guard.
    # It never expands the coordinate projection's calibrated polygon.
    guard_region = cal_config.get('camera_guard_feature_region', cal_config.get('image_points'))
    motion_guard = CameraMotionGuard(reference, guard_region) if reference else None
    exp_map = ExperimentalMap() if config.get('experimental_map', False) else None
    exp_generation = manual_tracks.generation()
    # A new run (including SRT reconnection) always starts with empty memory.
    consensus = TeamConsensus() if config.get('temporal_team_consensus', False) else None
    try:
        from ultralytics import YOLO
        import torch
        model = YOLO(config.get('model', 'yolo11n.pt'))
        # A distinct predictor prevents ball inference from changing ByteTrack state.
        ball_model = YOLO(config.get('ball_model_path', config.get('model', 'yolo11n.pt'))) if config.get('ball_detection', False) else None
        ball_class = ball_class_id(ball_model.names) if ball_model is not None else None
        ball_available = ball_class is not None
        device = 'cuda:0' if torch.cuda.is_available() else 'cpu'
        from app.tiled_tracking import TiledPlayerTracker, use_tiled_detection
        tiled = None
        tiled_setting = config.get('tiled_detection', False)
        detection_mode = None
        live = source.startswith('rtsp://')
        # FFmpeg timeouts are milliseconds. The single-slot capture prevents Python queue growth.
        cap = cv2.VideoCapture(source, cv2.CAP_FFMPEG, [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 8000, cv2.CAP_PROP_READ_TIMEOUT_MSEC, 5000])
        if not cap.isOpened():
            raise RuntimeError('Cannot open video source')
        media_fps = cap.get(cv2.CAP_PROP_FPS) if not live else 0
        try:
            uploaded_file = not live and Path(source).resolve().is_relative_to(UPLOAD_DIR.resolve())
        except (OSError, ValueError):
            uploaded_file = False
        pace_file = uploaded_file and np.isfinite(media_fps) and 1 <= media_fps <= 240
        timeline_verified = (not live and config.get('verified_constant_frame_rate') is True and np.isfinite(media_fps) and 1 <= media_fps <= 240)
        movement = MovementTracker()
        formation = FormationObserver() if config.get('formation_observation', False) else None
        suggestions = TeamSuggestions() if config.get('suggest_team_clusters', False) else None
        slot = {'frame': None, 'time': 0, 'decoded_at': None, 'seq': 0, 'done': False}
        slot_lock = threading.Lock()
        def capture():
            try:
                file_start = time.monotonic()
                file_frame = 0
                while not stop_event.is_set():
                    if pace_file:
                        delay = file_start + file_frame / media_fps - time.monotonic()
                        if delay > 0 and stop_event.wait(delay): break
                    ok, frame = cap.read()
                    if not ok:
                        break
                    file_frame += 1
                    if live:
                        set_state(live_input, last_decoded_monotonic=time.monotonic())
                    with slot_lock:
                        slot.update(frame=frame, time=time.monotonic(), decoded_at=datetime.now(timezone.utc).isoformat(), seq=slot['seq']+1)
                    if not live:
                        # Process every file frame; live mode intentionally drops stale frames.
                        while not stop_event.is_set():
                            with slot_lock:
                                consumed = slot['frame'] is None
                            if consumed: break
                            time.sleep(.002)
            finally:
                cap.release()
                with slot_lock: slot['done'] = True
        reader = threading.Thread(target=capture, daemon=True); reader.start()
        previous = time.monotonic()
        last_preview = 0.0
        last_label_frame = 0.0
        while not stop_event.is_set():
            with slot_lock:
                frame, grabbed, decoded_at, sequence, done = slot['frame'], slot['time'], slot['decoded_at'], slot['seq'], slot['done']
                slot['frame'] = None
            if frame is None:
                if done:
                    if live: raise RuntimeError('Stream disconnected')
                    break
                time.sleep(.005); continue
            if detection_mode is None:
                use_tiles = use_tiled_detection(tiled_setting, frame.shape[1], frame.shape[0])
                detection_mode = 'tiled' if use_tiles else 'whole frame'
                if use_tiles:
                    tiled = TiledPlayerTracker(model, device, config.get('image_size', 640), float(config.get('confidence', .35)),
                                               low_score_recovery=config.get('bytetrack_low_score_recovery', False))
            players = []
            calibration, calibration_status = active_calibration(config.get('calibration'), frame.shape)
            camera_status = None
            if (calibration is not None or exp_map is not None) and motion_guard is not None:
                camera_status = motion_guard.check(frame)
                if calibration is not None and camera_status != 'stable':
                    calibration, calibration_status = None, camera_status
            exp_ready = (exp_map is not None and camera_status == 'stable' and
                         cal_config.get('image_size_px') == [frame.shape[1], frame.shape[0]])
            generation_now = manual_tracks.generation()
            if generation_now != exp_generation:
                suggestions = reset_segment_state(tiled, model, suggestions, exp_map)
                if consensus is not None:
                    consensus.reset()
                movement.reset()
                if formation is not None:
                    formation.reset()
                exp_generation = generation_now
            exp_points = []
            if tiled:
                tracks = tiled.update(frame)
            else:
                results = model.track(frame, persist=True, tracker='bytetrack.yaml', classes=[0], verbose=False, device=device, imgsz=config.get('image_size', 640), conf=float(config.get('confidence', .35)))
                boxes = results[0].boxes
                tracks = [] if boxes is None or boxes.id is None else zip(boxes.xyxy.cpu().numpy(), boxes.id.int().cpu().tolist())
            tracks = list(tracks)
            track_counts = Counter(str(track_id) for _, track_id in tracks)
            if config.get('manual_player_assignments', False):
                manual_tracks.observe(str(track_id) for _, track_id in tracks)
            groups = suggestions.update(frame, tracks) if suggestions is not None else {}
            for box, track_id in tracks:
                x1,y1,x2,y2 = map(float, box)
                if config.get('manual_player_assignments', False):
                    token, team, role = manual_tracks.get(str(track_id))
                else:
                    team_fn = classify_guarded if config.get('team_classifier', 'median') == 'guarded_palette' else classify
                    team = team_fn(frame, box, config.get('team_hsv', {}))
                x,y = project(((x1+x2)/2,y2), calibration)
                player = dict(id=str(track_id), team=team, x=x, y=y)
                if exp_ready:
                    # Reuse polygon and finite-coordinate guards; never publish
                    # the temporary flag or use these coordinates for metrics.
                    ex, ey = project(((x1+x2)/2,y2), {**cal_config, 'validated': True})
                    if ex is not None and ey is not None and track_counts[str(track_id)] == 1:
                        exp_points.append({'id': str(track_id), 'x': ex, 'y': ey, 'team_hint': groups.get(str(track_id))})
                if suggestions is not None:
                    # Appearance-only candidates never establish role or team.
                    player['suggested_color_group'] = groups.get(str(track_id))
                if config.get('manual_player_assignments', False):
                    height, width = frame.shape[:2]
                    player.update(role=role, annotation_token=token,
                        bbox_image_norm=[max(0.,min(1.,v)) for v in (x1/width,y1/height,x2/width,y2/height)])
                players.append(player)
            if consensus is not None:
                players = consensus.update(players, time.monotonic())
            # The generic person detector does not establish that any color
            # candidate is a field player; keep API teams unknown until an
            # observer has explicitly confirmed each role and team.
            players = mask_unconfirmed_player_teams(players, config)
            ball_candidates = []
            if ball_available:
                if config.get('ball_tiled_detection', False):
                    ball_candidates = tiled_ball_candidates(ball_model, frame, class_id=ball_class, device=device, image_size=config.get('image_size', 640), confidence=float(config.get('confidence', .35)))
                else:
                    ball_result = ball_model.predict(frame, classes=[ball_class], verbose=False, device=device, imgsz=config.get('image_size', 640), conf=float(config.get('confidence', .35)))
                    ball_candidates = ball_candidates_from_boxes(ball_result[0].boxes, frame.shape[1], frame.shape[0])
            # Team-color validation alone is not evidence that a detected
            # person is a field player. Only explicitly confirmed player IDs
            # currently enter team extents and coaching.
            teams_confirmed = can_compute_team_metrics(config)
            metrics, feedback = summarize(players, config.get('own_team', 'home'), (calibration or {}).get('field_size_m') if teams_confirmed else None)
            calibration = calibration or {}
            movements, movement_feedback = movement.update(players, (sequence - 1) / media_fps if timeline_verified else None,
                calibration.get('field_size_m'), calibration_validated=calibration.get('validated') is True,
                teams_validated=teams_confirmed, timeline_reliable=timeline_verified)
            feedback.extend(movement_feedback)
            formation_changes = []
            if formation is not None:
                formation_changes = formation.update(players, config.get('own_team', 'home'),
                    (sequence - 1) / media_fps if timeline_verified else None, calibration.get('field_size_m'),
                    validated=timeline_verified and calibration.get('validated') is True and teams_confirmed)
                feedback.extend(observation_feedback(change) for change in formation_changes)
            if uploaded_file and timeline_verified:
                sequence_history.add(source, sequence - 1, media_fps, frame, players, metrics, feedback,
                    teams_validated=teams_confirmed,
                    calibration_validated=calibration.get('validated') is True,
                    team_colors=team_colors(config.get('team_hsv', {})))
            if time.monotonic() - last_preview >= PREVIEW_INTERVAL_S:
                jpeg = publish_preview(frame, grabbed, decoded_at, tracks if config.get('preview_track_boxes', False) else None, groups)
                if jpeg and os.environ.get('FOOTBALL_LABEL_REVIEW') == '1' and time.monotonic() - last_label_frame >= 0.5:
                    training_labels.publish(frame, tracks, decoded_at, 'live' if live else 'file', groups)
                    last_label_frame = time.monotonic()
                if jpeg and live:
                    live_bookmarks.publish(jpeg, decoded_at, grabbed, len(players), metrics, feedback)
                if jpeg and config.get('manual_player_assignments', False):
                    manual_tracks.publish_snapshot(jpeg, players, decoded_at)
                last_preview = time.monotonic()
            now = time.monotonic()
            experiment = None
            if exp_map is not None:
                if exp_ready:
                    # A visible track outside the projection polygon, or with
                    # duplicate IDs, is not a disappearance to extrapolate.
                    exp_map.forget(set(track_counts) - {p['id'] for p in exp_points})
                    experiment = {'status': 'reference_unverified', 'basis': 'manual_fixed_camera_reference',
                                  'field_size_m': cal_config['field_size_m'], 'uncertainty_m': None,
                                  'players': exp_map.update(exp_points, grabbed, cal_config['field_size_m'], allow_estimation=live, allowed_polygon=cal_config['field_points_m'])}
                    experiment['capacity'] = dict(exp_map.capacity)
                else:
                    exp_map.clear()
                    experiment = {'status': camera_status or 'reference_unavailable', 'players': []}
            diagnostic = coaching_diagnostics(config, players, calibration_status, metrics)
            with lock:
                analysis.update(timestamp=datetime.now(timezone.utc).isoformat(), players=players, ball_candidates=ball_candidates, ball_detection_available=ball_available, calibration_status=calibration_status, metrics=metrics, movements=movements, formation_changes=formation_changes, feedback=feedback, coaching_diagnostics=diagnostic, experimental_map=experiment, tracking_generation=exp_generation, demo=False)
                last_analysis_monotonic = time.monotonic()
                last_map_generation = exp_generation
            set_state(status, fps=round(1/max(now-previous, .0001), 2), latency_ms=round((now-grabbed)*1000, 1), message=f'Processing ({device}, {detection_mode}); latency is post-decode only')
            previous = now
        set_state(status, status='idle', fps=None, latency_ms=None, message='Stopped' if stop_event.is_set() else 'End of file')
    except Exception as e:
        set_state(analysis, timestamp=None, players=[], ball_candidates=[], ball_detection_available=False, calibration_status='not_configured', metrics=dict(team_width_m=None, team_length_m=None), movements=[], formation_changes=[], feedback=[], coaching_diagnostics=dict(state='not_started', reasons=[], warnings=[]))
        set_state(status, status='error', message=str(e), fps=None, latency_ms=None)
    finally:
        stop_event.set()
        manual_tracks.reset()
        if reader is not None:
            reader.join()
        elif cap is not None:
            cap.release()


@app.on_event('shutdown')
def shutdown():
    stop_event.set()
