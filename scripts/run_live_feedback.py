"""Live tactical feedback from a video file, a camera or a stream (RTSP / HTTP / device number).

python scripts/run_live_feedback.py <source> <calibrations.json> <camera> --direction 1 --team B --detector yolo11n.pt [--classifier model.pt]
       [--reference-bg a b tx ty] [--shift 0 0] [--pitch-length 89 --pitch-width 62] [--analysis-fps 5] [--start 64 --seconds 300] [--realtime]
       [--alerts alerts.jsonl] [--video-out preview.mp4] [--camera-compensate --reference-image photo.jpg] [--no-latest-input]

Every analysed frame goes through person detection and tracking, team labelling (the team-role model when given, otherwise the shirt colour rule: bright or
neon shirts are team A, dark shirts team B), the pitch calibration and then app.live_feedback.LiveAnalyzer, which raises short coaching alerts. Alerts are
printed, appended to a JSON-lines file and drawn on the preview video. The calibration is the one saved for the camera setting; a moved camera needs a new
calibration (see docs/live-feedback.md).
"""
import argparse
import json
import sys
import threading
import time
from collections import Counter
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from app.live_feedback import LiveAnalyzer  # noqa: E402
from app.camera_drift import CameraDriftTracker  # noqa: E402
from app.latest_frame import DelayStats, LatestFrameQueue  # noqa: E402
from app.live_input import ReconnectingReader, heartbeat_record, status_record  # noqa: E402
from app.live_control import ControlWatcher  # noqa: E402
from app.live_positions import PositionLog  # noqa: E402
from app.hard_frames import HardFrameCollector  # noqa: E402
from app.pitch_map import feet_to_metres, fit  # noqa: E402
from app.team_role_features import FEATURE_NAMES, box_features  # noqa: E402
from app.team_role_infer import LETTER, load_model, predict  # noqa: E402
from app.team_color_profile import ProfileClassifier, load_profile, shirt_colour  # noqa: E402
from app.track_vote import TRACKER_SETTINGS  # noqa: E402
import track_review_clip as tile_detector  # noqa: E402

COLOUR = {'good': (182, 196, 46), 'poor': (101, 138, 255), 'info': (255, 200, 130)}
TEAM_BGR = {'A': (74, 216, 255), 'B': (255, 198, 124)}


class TeamVotes:
    """A running vote per track: the label is the one most often seen so far, once at least `minimum` frames agree."""

    def __init__(self, classifier=None, minimum=3, profile=None, own_letter='B', other_letter='A', neon_band=None, neon_min=0.22, dark_min=0.30):
        self.model = load_model(classifier) if classifier else None
        self.profile = ProfileClassifier(profile) if profile else None      # the team colours the coach chose for this match (--team-profile); replaces the model and the fixed colour rule
        self.profile_letters = {'own': own_letter, 'opponent': other_letter}
        self.own_letter_, self.other_letter_ = own_letter, other_letter
        self.votes, self.minimum = {}, minimum
        self.neon_band, self.neon_min, self.dark_min = neon_band, neon_min, dark_min    # --neon-band: this venue's own hue band for the bibs (the first match's band 22-44 misses greener bibs)
        self.neon = FEATURE_NAMES.index('neon')
        self.dark = FEATURE_NAMES.index('dark')

    def observe(self, tid, frame, box):
        h, w = frame.shape[:2]
        if self.profile:
            side = self.profile.classify(shirt_colour(frame, box))
            if side:
                self.votes.setdefault(tid, Counter())[self.profile_letters[side]] += 1
            return
        features = box_features(frame, [box[0] / w, box[1] / h, box[2] / w, box[3] / h])
        if self.neon_band and not self.model:
            bh, bw = box[3] - box[1], box[2] - box[0]
            patch = frame[int(box[1] + .18 * bh):int(box[1] + .55 * bh) + 1, int(box[0] + .2 * bw):int(box[2] - .2 * bw) + 1]
            if patch.size == 0:
                return
            hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV).reshape(-1, 3)
            share = ((hsv[:, 1] > 90) & (hsv[:, 2] > 110) & (hsv[:, 0] >= self.neon_band[0]) & (hsv[:, 0] <= self.neon_band[1])).mean()
            letter = 'A' if share >= self.neon_min else ('B' if features[self.dark] >= self.dark_min else None)
            if letter:
                self.votes.setdefault(tid, Counter())[letter] += 1
            return
        if self.model:
            probabilities = predict(self.model, features[None])[0]
            letter = LETTER.get(self.model['classes'][int(np.argmax(probabilities))])
        else:
            letter = 'A' if features[self.neon] >= 0.10 else ('B' if features[self.dark] >= 0.30 else None)
        if letter:
            self.votes.setdefault(tid, Counter())[letter] += 1

    def label(self, tid):
        counts = self.votes.get(tid)
        if not counts:
            return None
        letter, n = counts.most_common(1)[0]
        return letter if n >= self.minimum and letter in ('A', 'B') else None


ZOOM_TILE = 256          # pixels of a tile of the extra pass over the penalty area; it is read at 4 times its size (imgsz 1024)
ZOOM_HEAD_ROOM = 110     # pixels above the feet line that still hold the bodies of the players


def box_region(fitted, direction, width, height, bg, length=89.0):
    """The part of the frame that shows the penalty area of the goal the focus team attacks, with room above the feet line for the bodies: (x0, y0, x1, y1) in pixels or None.
    The area is 20 m deep and 44 m wide plus a margin; the calibration maps it back to the picture (the small camera-setting transform bg is undone in its translation only)."""
    inverse = np.linalg.inv(fitted['H'])
    xs, ys = [], []
    for u in (length / 2 - 22.0, length / 2 + 1.0):
        for v in (-24.0, 0.0, 24.0):
            p = inverse @ np.array([direction * u, v, 1.0])
            if p[2] <= 0:
                return None
            px, py = p[0] / p[2] * width, p[1] / p[2] * height
            if bg:
                px, py = px - bg[2], py - bg[3]
            xs.append(px)
            ys.append(py)
    x0, x1 = max(0, int(min(xs)) - 40), min(width, int(max(xs)) + 40)
    y0, y1 = max(0, int(min(ys)) - ZOOM_HEAD_ROOM), min(height, int(max(ys)) + 30)
    return (x0, y0, x1, y1) if x1 - x0 > 64 and y1 - y0 > 64 else None


def detect_zoom(model, image, region, device, confidence):
    """Persons in `region` found with small tiles read at four times their size (the penalty area is crowded and its players are small)."""
    x0, y0, x1, y1 = region
    found = []
    for y in [y0 + v for v in tile_detector.starts(y1 - y0, ZOOM_TILE, 0.3)]:
        for x in [x0 + v for v in tile_detector.starts(x1 - x0, ZOOM_TILE, 0.3)]:
            result = model.predict(image[y:y + ZOOM_TILE, x:x + ZOOM_TILE], device=device, imgsz=1024, conf=confidence, classes=[0], max_det=60, verbose=False)[0]
            if result.boxes is None:
                continue
            for box, score in zip(result.boxes.xyxy.cpu().numpy(), result.boxes.conf.cpu().numpy()):
                found.append([box[0] + x, box[1] + y, box[2] + x, box[3] + y, float(score)])
    return found


def merge_detections(found):
    found = sorted(found, key=lambda d: -d[4])
    kept = []
    for d in found:
        if all(tile_detector.overlap_share(d, k) <= 0.6 for k in kept):
            kept.append(d)
    return kept


def beat_stats(queue, delays, camera_state):
    """What a heartbeat line says about the run: the latest-frame queue (decoded, delivered, dropped), the delay from reading a frame to the end of its analysis, the camera state."""
    out = {'delay': delays.summary(), 'camera': camera_state}
    if queue:
        out['queue'] = queue.stats()
    return out


def load_reference_image(args, record):
    """The photo the calibration clicks were made on: --reference-image, or the ref_token photo of the calibration inside the review store."""
    path = Path(args.reference_image) if args.reference_image else None
    if path is None and args.store and record.get('ref_token'):
        path = Path(args.store) / 'pending' / (str(record['ref_token']) + '.jpg')
    if path is None or not path.is_file():
        raise SystemExit('--camera-compensate needs the calibration photo: give --reference-image, or --store with a calibration that names its ref_token.')
    image = cv2.imread(str(path))
    if image is None:
        raise SystemExit(f'Could not read the reference photo {path.name}.')
    return image


def banner(frame, alert, age):
    """The alert as a strip at the bottom of the preview, fading after a few seconds."""
    if age > 8:
        return
    h, w = frame.shape[:2]
    overlay = frame.copy()
    bar = 130 if alert.get('detail') else 90
    cv2.rectangle(overlay, (0, h - bar), (w, h), (24, 17, 11), -1)
    cv2.rectangle(overlay, (0, h - bar), (10, h), COLOUR.get(alert['polarity'], COLOUR['info']), -1)
    cv2.addWeighted(overlay, 0.8, frame, 0.2, 0, frame)
    from PIL import Image, ImageDraw, ImageFont
    image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    d = ImageDraw.Draw(image)
    d.text((28, h - bar + 8), alert['title'], font=ImageFont.truetype('C:/Windows/Fonts/malgunbd.ttf', 26), fill=(255, 255, 255))
    d.text((28, h - bar + 44), alert['text'], font=ImageFont.truetype('C:/Windows/Fonts/malgun.ttf', 24), fill=(238, 243, 247))
    if alert.get('detail'):
        d.text((28, h - bar + 84), alert['detail']['line'], font=ImageFont.truetype('C:/Windows/Fonts/malgun.ttf', 22), fill=(130, 230, 200))
    frame[:] = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)


def lane_picture(frame, detail, boxes):
    """A copy of the frame with the passing lanes of an alert: the most advanced player ringed in amber, dashed lines to the teammates (green: open, red: blocked by an opponent)."""
    image = frame.copy()
    feet = {tid: (int((b[0] + b[2]) / 2), int(b[3])) for tid, b in boxes.items()}
    start = feet.get(int(detail['carrier'])) if str(detail['carrier']).lstrip('-').isdigit() else None
    if start is None:
        return image
    for lane in detail['lanes'][:6]:
        end = feet.get(int(lane['track'])) if str(lane['track']).lstrip('-').isdigit() else None
        if end is None:
            continue
        colour = (182, 196, 46) if lane['open'] else (101, 101, 255)
        length = max(1.0, ((end[0] - start[0]) ** 2 + (end[1] - start[1]) ** 2) ** 0.5)
        steps = max(2, int(length // 14))
        for k in range(0, steps, 2):
            a = (int(start[0] + (end[0] - start[0]) * k / steps), int(start[1] + (end[1] - start[1]) * k / steps))
            b = (int(start[0] + (end[0] - start[0]) * (k + 1) / steps), int(start[1] + (end[1] - start[1]) * (k + 1) / steps))
            cv2.line(image, a, b, colour, 2, cv2.LINE_AA)
        cv2.circle(image, end, 12, colour, 2, cv2.LINE_AA)
    cv2.circle(image, start, 14, (87, 200, 255), 3, cv2.LINE_AA)
    return image


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('source', help='video file, stream URL or camera number')
    parser.add_argument('calibrations')
    parser.add_argument('camera')
    parser.add_argument('--neon-band', type=int, nargs=2, metavar=('LOW', 'HIGH'), help='OpenCV hue band (0-179) of the opponent bibs for the colour rule (default: the rule of the first match); this venue: 30 70')
    parser.add_argument('--neon-min', type=float, default=0.22, help='share of bib-coloured pixels that makes a box the bib team (with --neon-band)')
    parser.add_argument('--dark-min', type=float, default=0.30, help='share of dark pixels that makes a box the dark team (with --neon-band)')
    parser.add_argument('--vote-min', type=int, default=3, help='frames of one track that have to agree before the track gets a team letter (default 3; 1 labels a track at once)')
    parser.add_argument('--pitch-margin', type=float, help='metres outside the touchlines and goal lines that still count as the pitch (default 2.0; a smaller value keeps referees and substitutes at the line out)')
    parser.add_argument('--direction', type=int, choices=(1, -1), required=True, help='+1 when the focus team attacks toward +x (image right)')
    parser.add_argument('--team', choices=('A', 'B'), default='B')
    parser.add_argument('--detector', default='yolo11n.pt')
    parser.add_argument('--classifier')
    parser.add_argument('--team-profile', help='team_profile.json the coach saved on /team-select (<store>/service/team_profile.json): the own team is the colour group the coach chose, the other team the other group; without the file the fixed rule of this first match stays (dark shirts are team B)')
    parser.add_argument('--reference-bg', type=float, nargs=4)
    parser.add_argument('--shift', type=float, nargs=2, default=(0.0, 0.0))
    parser.add_argument('--pitch-length', type=float, default=89.0)
    parser.add_argument('--pitch-width', type=float, default=62.0)
    parser.add_argument('--analysis-fps', type=float, default=5.0)
    parser.add_argument('--start', type=float, default=0.0, help='seconds to skip in a file')
    parser.add_argument('--seconds', type=float, default=0.0, help='stop after this many seconds of video (0 = to the end)')
    parser.add_argument('--source-fps', type=float, help='frame rate of the source when the file does not report it correctly')
    parser.add_argument('--realtime', action='store_true', help='pace a file like a live feed')
    parser.add_argument('--alerts', default='alerts.jsonl')
    parser.add_argument('--store', help='the review store of the server: the alerts then go to <store>/alerts/<session>/ and show up on the page /alerts for rating')
    parser.add_argument('--session', default='', help='name of this run (letters, digits, - and _); default: the date and time')
    parser.add_argument('--video-out')
    parser.add_argument('--confidence', type=float, default=0.10)
    parser.add_argument('--tile-camera', choices=('cam1', 'cam3', 'cam4'), help='which picture layout the tile detector uses (the part of the frame that is pitch); default: the camera name')
    parser.add_argument('--box-zoom', action='store_true', help='extra detection pass over the penalty area of the attacked goal (about 1.4 times slower: no longer real time on this machine)')
    parser.add_argument('--max-retries', type=int, default=8, help='a stream or camera that stops is opened again this many times in a row (waits of 1, 2, 4 ... 30 s) before the run ends')
    parser.add_argument('--max-frame-errors', type=int, default=50, help='this many frames in a row that fail in the analysis end the run; a single failed frame is skipped')
    parser.add_argument('--frames-log', help='write every analysed frame (time and the metre positions of both teams as the alert rules receive them) to this file, one JSON line per frame, so that the alert rules can be replayed without the video (scripts/replay_frames_log.py); off by default')
    parser.add_argument('--collect-hard-frames', metavar='FOLDER', help='save frames where the detector probably missed players (a sudden drop in the person count, too few players of the focus team) to this folder, with time, camera, reasons and boxes, for the user to draw boxes on later (app/hard_frames.py, wiki/hard-frames.md); a folder of its own, never the review store; off by default')
    parser.add_argument('--positions', help='write the metre positions of both teams, one line per second, to this file (positions.jsonl) so that a half can be summed up at half time; off by default')
    parser.add_argument('--latest-input', action=argparse.BooleanOptionalAction, default=None, help='keep only the newest frame so that a slow analysis never builds up a delay (the frames in between are counted and dropped); default: on for a stream or camera, off for a file (--latest-input paces a file at its own frame rate)')
    parser.add_argument('--heartbeat-seconds', type=float, default=10.0, help='a heartbeat line (input alive, frames dropped, delay of the analysis) goes to the alerts file this often while frames arrive; 0 = none')
    parser.add_argument('--camera-compensate', action='store_true', help='follow a small move of the camera against the calibration photo and shift the calibration by it; a move that is too large, or a picture that cannot be matched for too long, holds the analysis back and writes camera_moved (not with --reference-bg)')
    parser.add_argument('--reference-image', help='the photo the calibration clicks were made on (for --camera-compensate); default: the ref_token photo of the calibration inside --store')
    parser.add_argument('--max-camera-shift', type=float, default=24.0, help='a shift of the camera larger than this many pixels (of the full frame) is not compensated')
    parser.add_argument('--detector-half', action='store_true', help='run the detector in FP16 (GPU only; NOT measured on this machine yet)')
    parser.add_argument('--detector-batch', type=int, default=1, help='tiles per detector call (GPU only; NOT measured on this machine yet)')
    parser.add_argument('--detector-imgsz', type=int, default=768, help='size the 384 px tiles are enlarged to before the detector (768 = the live setting; larger values were measured only for ft_n2 on boxes a human confirmed, see wiki/detector-experiments.md)')
    parser.add_argument('--device', default='0', help='0 for the first GPU, cpu for no GPU')
    args = parser.parse_args()
    if args.camera_compensate and args.reference_bg:
        raise SystemExit('--camera-compensate replaces --reference-bg (both would count the same move twice).')

    record = json.loads(Path(args.calibrations).read_text(encoding='utf-8')).get(args.camera)
    if not record:
        raise SystemExit(f'No saved calibration for {args.camera}.')
    record = {**record, 'pitch': {**(record.get('pitch') or {}), 'length': args.pitch_length, 'width': args.pitch_width}}
    fitted = fit(record)
    if 'H' not in fitted:
        raise SystemExit('Calibration refused: ' + fitted['error'])
    from ultralytics import YOLO
    detector = YOLO(args.detector)
    from ultralytics.engine.results import Boxes
    from ultralytics.trackers.byte_tracker import BYTETracker
    from ultralytics.utils import IterableSimpleNamespace, YAML
    from ultralytics.utils.checks import check_yaml
    config = IterableSimpleNamespace(**YAML.load(check_yaml('bytetrack.yaml')))
    for key, value in TRACKER_SETTINGS.items():
        setattr(config, key, value)
    config.track_high_thresh = config.new_track_thresh = 0.12
    config.track_low_thresh = 0.06
    byte_tracker = BYTETracker(args=config)
    device = 'cpu' if args.device == 'cpu' else int(args.device)
    tile_camera = args.tile_camera or args.camera
    margin_kw = {'margin': args.pitch_margin} if args.pitch_margin is not None else {}
    profile = load_profile(args.team_profile) if args.team_profile else None
    if args.team_profile and profile is None:
        raise SystemExit(f'Team profile file not found: {Path(args.team_profile).name}. Choose the own team on /team-select first, or run without --team-profile.')
    if profile:
        print(f"Team colours from the coach's choice ({profile['created']}): own team {profile.get('note') or 'chosen'}" + ('; --classifier is not used for the team letters.' if args.classifier else '.'))
    votes = TeamVotes(args.classifier, minimum=args.vote_min, profile=profile, own_letter=args.team, other_letter='A' if args.team == 'B' else 'B', neon_band=tuple(args.neon_band) if args.neon_band else None, neon_min=args.neon_min, dark_min=args.dark_min)
    analyzer = LiveAnalyzer(args.direction, args.pitch_length, args.pitch_width, args.analysis_fps)
    frames_log = open(args.frames_log, 'a', encoding='utf-8') if args.frames_log else None
    if frames_log:
        frames_log.write(json.dumps({'type': 'header', 'direction': args.direction, 'pitch_length': args.pitch_length, 'pitch_width': args.pitch_width, 'fps': args.analysis_fps, 'team': args.team}) + chr(10))
    other = 'A' if args.team == 'B' else 'B'
    zoom_region = None

    source = int(args.source) if args.source.isdigit() else args.source
    is_file = isinstance(source, str) and Path(source).exists()
    first = cv2.VideoCapture(source)
    if not first.isOpened():
        raise SystemExit('Could not open the source.')
    if args.box_zoom:
        zoom_region = box_region(fitted, args.direction, int(first.get(cv2.CAP_PROP_FRAME_WIDTH)), int(first.get(cv2.CAP_PROP_FRAME_HEIGHT)), tuple(args.reference_bg) if args.reference_bg else None, args.pitch_length)
        print('Extra zoom pass over the penalty area:', zoom_region or 'off (the area cannot be placed in the picture)')
    fps = args.source_fps or first.get(cv2.CAP_PROP_FPS) or 25.0
    step = max(1, int(round(fps / args.analysis_fps)))
    if is_file and args.start:
        first.set(cv2.CAP_PROP_POS_FRAMES, int(args.start * fps))
    opened = [first]                                                                    # the first capture is used once; a reconnect opens a new one

    def open_source():
        return opened.pop() if opened else cv2.VideoCapture(source)
    alerts_path = Path(args.alerts)
    if args.store:
        import re
        from datetime import datetime
        session = args.session or datetime.now().strftime('run-%Y%m%d-%H%M%S')
        if not re.match(r'^[A-Za-z0-9_-]{1,40}$', session):
            raise SystemExit('The session name may only hold letters, digits, - and _ (40 at most).')
        alerts_path = Path(args.store) / 'alerts' / session / 'alerts.jsonl'
        alerts_path.parent.mkdir(parents=True, exist_ok=True)
    counter = sum(1 for _ in open(alerts_path, encoding='utf-8')) if alerts_path.exists() else 0        # the number of an alert is its line in the file, also when a run is continued
    writer, alerts_out = None, open(alerts_path, 'a', encoding='utf-8')
    wall0, index, shown = time.time(), 0, None
    monotonic0 = time.monotonic()
    collector = HardFrameCollector(args.collect_hard_frames, args.camera, Path(args.detector).name) if args.collect_hard_frames else None
    position_log = PositionLog(args.positions, args.team, other, args.direction, args.pitch_length, args.pitch_width, args.start if is_file else 0.0) if args.positions else None
    control = ControlWatcher(alerts_path.parent / 'control.jsonl')                      # the button of the second half (app/live_control.py)
    errors = 0
    write_lock = threading.Lock()                                                       # the reader thread writes the notes of a lost input while the main loop writes alerts

    def write_row(record):
        nonlocal counter
        with write_lock:
            alerts_out.write(json.dumps(record, ensure_ascii=False) + '\n')
            alerts_out.flush()
            counter += 1

    def note(kind, text):
        """A loss or a recovery of the input goes at once to the alerts file (not rated as an alert) and, when a frame is there again, to the banner."""
        nonlocal shown
        now = args.start + index / fps if is_file else time.time() - wall0
        print(f'[input] {text}')
        record = status_record(kind, now)
        write_row(record)
        shown = (record, now)
    reader = ReconnectingReader(open_source, is_file=is_file, max_retries=args.max_retries, notify=note)
    use_queue = (not is_file) if args.latest_input is None else args.latest_input
    queue = LatestFrameQueue(reader, pace_fps=fps if is_file else None) if use_queue else None
    delays = DelayStats()
    drift = None
    if args.camera_compensate:
        drift = CameraDriftTracker(load_reference_image(args, record), tile_detector.PITCH_TOP[tile_camera], args.max_camera_shift)
        if not drift.usable:
            raise SystemExit('The reference photo has too few features on the pitch part for --camera-compensate.')
    camera_ok, camera_state = True, 'off' if drift is None else 'unknown'
    next_analysis, last_beat, last_frame_at = (args.start if is_file else 0.0), time.monotonic(), time.monotonic()
    stats = {'frames': 0, 'team': 0, 'other': 0}
    print(f'Live feedback for team {args.team}, attacking {"right" if args.direction > 0 else "left"}; analysing every {step} frame(s) of {fps:.1f} fps'
          + ('; newest frame only.' if queue else '.') + (' Camera compensation on.' if drift else ''))
    try:
        while True:
            taken = time.monotonic()
            if queue:
                try:
                    item = queue.get(timeout=1.0)
                except TimeoutError:                                                    # nothing arrived this second (a lost stream waits in the reader thread)
                    if args.heartbeat_seconds and time.monotonic() - last_beat >= args.heartbeat_seconds and time.monotonic() - last_frame_at < 2 * args.heartbeat_seconds:
                        last_beat = time.monotonic()
                        write_row(heartbeat_record(time.time() - wall0, beat_stats(queue, delays, camera_state)))
                    continue
                if item is None:
                    if queue.error is not None:
                        print(f'The source reader failed: {type(queue.error).__name__}: {queue.error}')
                    print(f'The source ended or could not be read after {index} frames' + (' (it did not come back).' if reader.gave_up else '.'))
                    break
                index, frame, taken = item
                last_frame_at = taken
                t = args.start + (index - 1) / fps if is_file else taken - monotonic0
                if t + 1e-7 < next_analysis:
                    continue
                if t - next_analysis > 2 * step / fps:                                  # the analysis fell behind (frames were dropped) or the source jumped: the schedule restarts from this frame
                    next_analysis = t
                next_analysis += step / fps
            else:
                ok, frame = reader.read()
                if not ok:
                    print(f'The source ended or could not be read after {index} frames' + (' (it did not come back).' if reader.gave_up else '.'))
                    break
                index += 1
                last_frame_at = time.monotonic()
                if (index - 1) % step:
                    continue
                t = args.start + (index - 1) / fps if is_file else time.time() - wall0
            if args.seconds and t - (args.start if is_file else 0) > args.seconds:
                break
            if args.realtime and is_file and not queue:
                lag = (t - args.start) - (time.time() - wall0)
                if lag > 0:
                    time.sleep(lag)
            if drift is not None:
                state = drift.update(frame, t)
                if state == 'ok' and not camera_ok:
                    camera_ok = True
                    note('camera_back', 'camera')
                elif state != 'ok' and camera_ok:
                    camera_ok = False
                    note('camera_moved', 'camera')
                camera_state = state
                if not camera_ok:
                    continue                                                            # the calibration does not fit this picture: no positions, no alerts
                frame_shift = (args.shift[0] + drift.shift[0], args.shift[1] + drift.shift[1])
            else:
                frame_shift = tuple(args.shift)
            try:
                found = tile_detector.detect(detector, frame, tile_camera, device, args.confidence, batch_size=args.detector_batch, half=args.detector_half, imgsz=args.detector_imgsz)
                if zoom_region:
                    found = merge_detections(found + detect_zoom(detector, frame, zoom_region, device, args.confidence))
                array = np.array([[*d[:4], d[4], 0] for d in found], np.float32).reshape(-1, 6)
                tracked = byte_tracker.update(Boxes(array, frame.shape[:2]), None)
                mine, theirs, drawn = [], [], []
                for row in tracked:
                    box, tid = row[:4], int(row[4])
                    votes.observe(tid, frame, box)
                    letter = votes.label(tid)
                    if letter is None:
                        continue
                    point = feet_to_metres(fitted, box, frame.shape[1], frame.shape[0], frame_shift, tuple(args.reference_bg) if args.reference_bg else None, **margin_kw)
                    if point is None:
                        continue
                    (mine if letter == args.team else theirs).append((tid, point[0], point[1]))
                    drawn.append((box, letter))
                stats['frames'] += 1
                if collector:
                    try:
                        collector.observe(float(t), frame, found, len(mine))              # a failure of the collection never stops the analysis
                    except Exception as error:
                        print(f'[hard frames] not saved ({type(error).__name__}: {error})')
                stats['team'] += len(mine)
                stats['other'] += len(theirs)
                if frames_log:
                    frames_log.write(json.dumps({'t': round(float(t), 3), 'team': [[tid, round(x, 2), round(y, 2)] for tid, x, y in mine], 'other': [[tid, round(x, 2), round(y, 2)] for tid, x, y in theirs]}) + chr(10))
                for command in control.poll():                                           # second half: the other direction and a new analyser, no restart
                    args.direction = command['direction']
                    if args.box_zoom:                                                    # the penalty area of the goal that is attacked now
                        zoom_region = box_region(fitted, args.direction, frame.shape[1], frame.shape[0], tuple(args.reference_bg) if args.reference_bg else None, args.pitch_length)
                    analyzer = LiveAnalyzer(args.direction, args.pitch_length, args.pitch_width, args.analysis_fps)
                    if position_log:
                        position_log.write({'type': 'half', 'half': 2, 'direction': args.direction, 'time': round(float(t), 1)})
                    write_row(status_record('half_switch', t))
                    print(f'[half] second half: team {args.team} attacks {"right" if args.direction > 0 else "left"} from now on.')
                new = analyzer.update(t, mine, theirs)
                if position_log and analyzer.last_sample >= 0:
                    position_log.add(t, analyzer.held('team', analyzer.last_sample), analyzer.held('other', analyzer.last_sample))
                boxes_now = {int(r[4]): r[:4] for r in tracked}
                for alert in new:
                    shown = (alert, t)
                    if alert.get('detail'):
                        picture = lane_picture(frame, alert['detail'], boxes_now)
                        cv2.imwrite(str(alerts_path.with_name(f'alerts_{counter:04d}.jpg')), picture)
                        frame = picture
                    alert['latency_ms'] = round(1000 * (time.monotonic() - taken))              # from reading the frame to writing the alert; the bench screen adds the time since the line was written
                    write_row(alert)
                    print(f"[{int(alert['time'] // 60)}:{int(alert['time'] % 60):02d}] {alert['title']}: {alert['text']} ({alert['latency_ms']} ms after the frame)")
                if args.video_out:
                    for box, letter in drawn:
                        cv2.rectangle(frame, (int(box[0]), int(box[1])), (int(box[2]), int(box[3])), TEAM_BGR[letter], 1, cv2.LINE_AA)
                    if shown:
                        banner(frame, shown[0], t - shown[1])
                    if writer is None:
                        writer = cv2.VideoWriter(args.video_out, cv2.VideoWriter_fourcc(*'mp4v'), args.analysis_fps, (frame.shape[1], frame.shape[0]))
                    writer.write(frame)
                errors = 0
                delays.add(time.monotonic() - taken)
                if args.heartbeat_seconds and time.monotonic() - last_beat >= args.heartbeat_seconds:
                    last_beat = time.monotonic()
                    write_row(heartbeat_record(t, beat_stats(queue, delays, camera_state)))
            except Exception as error:                                                  # one bad frame is skipped; many in a row end the run
                errors += 1
                print(f'Frame {index} could not be analysed ({type(error).__name__}: {error}); skipped ({errors} in a row).')
                if errors >= args.max_frame_errors:
                    print('Too many failed frames in a row; the run stops.')
                    break
    finally:
        if queue:
            queue.close()
        else:
            reader.release()
        alerts_out.close()
        if position_log:
            position_log.close()
        if frames_log:
            frames_log.close()
        if writer:
            writer.release()
    n = max(1, stats['frames'])
    boxes = {sec: n for sec, n in analyzer.box_history.items() if n >= 2}
    if boxes:
        print('Seconds with 2 or more of our players in the box (second of video: players):', ', '.join(f'{int(k)}:{v}' for k, v in sorted(boxes.items())))
    if analyzer.placed:
        m = len(analyzer.placed)
        print(f"Per analysed second (what the alerts see): team {args.team} {sum(p[0] for p in analyzer.placed) / m:.1f} players with holding against {sum(p[2] for p in analyzer.placed) / m:.1f} in the last frame alone; "
              f"team {other} {sum(p[1] for p in analyzer.placed) / m:.1f} against {sum(p[3] for p in analyzer.placed) / m:.1f}.")
    if collector:
        print('Hard frames:', collector.summary())
    print(f"Finished: {stats['frames']} frames analysed, on average {stats['team'] / n:.1f} players of team {args.team} and {stats['other'] / n:.1f} of team {other} placed on the pitch.")


if __name__ == '__main__':
    main()
