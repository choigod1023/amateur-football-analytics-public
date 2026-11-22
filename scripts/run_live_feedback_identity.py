"""Identity-tracking line of the live analysis (merged from main on 2026-11-20; the match-day version is scripts/run_live_feedback.py).
Live tactical feedback from a video file, a camera or a stream (RTSP / HTTP / device number).

python scripts/run_live_feedback.py <source> <calibrations.json> <camera> --direction 1 --team B --detector yolo11n.pt [--classifier model.pt]
       [--reference-bg a b tx ty] [--shift 0 0] [--pitch-length 89 --pitch-width 62] [--analysis-fps 5] [--start 64 --seconds 300] [--realtime]
       [--alerts alerts.jsonl] [--video-out preview.mp4] [--camera-adaptation]

Every analysed frame goes through person detection and tracking, team labelling (the team-role model when given, otherwise the shirt colour rule: bright or
neon shirts are team A, dark shirts team B), the pitch calibration and then app.live_feedback.LiveAnalyzer, which raises short coaching alerts. Alerts are
printed, appended to a JSON-lines file and drawn on the preview video. The calibration is the one saved for the camera setting; a moved camera needs a new
calibration (see docs/live-feedback.md). Experimental --camera-adaptation instead
registers each frame directly against the saved reference, omits coordinates and
coaching when uncertain, and writes alerts.camera.json. It needs two consistent
registrations to resume. Saved pitch dimensions remain estimates. After a human
saves a replacement calibration, restart this CLI to load it; no automatic reload.
"""
import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from app.live_feedback import LiveAnalyzer  # noqa: E402
from app.camera_session import CameraSession  # noqa: E402
from app.pitch_map import feet_to_metres, fit  # noqa: E402
from app.team_role_features import FEATURE_NAMES, box_features  # noqa: E402
from app.team_role_infer import LETTER, load_model, predict  # noqa: E402
from app.track_vote import TRACKER_SETTINGS  # noqa: E402
from app.low_confidence_recovery import RecoveryDisplay
import track_review_clip as tile_detector  # noqa: E402

COLOUR = {'good': (182, 196, 46), 'poor': (101, 138, 255), 'info': (255, 200, 130)}
TEAM_BGR = {'A': (74, 216, 255), 'B': (255, 198, 124)}


def prepare_observation_tracks(t, frame, tracked, detections, *, identity_guard=None,
                               reconnect=None, observed=False, mode='all'):
    """Keep identity/review decisions on their original tracker geometry.

    Only subsequent classification/position observations may use measurement
    boxes. The optional display/observation policy cannot alter ID segmentation.
    """
    identity_events=[]
    if identity_guard is not None:
        tracked,identity_events=identity_guard.update(t,frame,tracked)
    aliases,reconnect_events=reconnect.update(t,tracked) if reconnect else ({},[])
    checks=[]
    if observed:
        from app.observation_boxes import current_detection_boxes
        tracked,checks=current_detection_boxes(tracked,detections,mode=mode)
    return tracked,identity_events,aliases,reconnect_events,checks


class TeamVotes:
    """A running vote per track: the label is the one most often seen so far, once at least `minimum` frames agree."""

    def __init__(self, classifier=None, minimum=3, guarded=False):
        self.model = load_model(classifier) if classifier else None
        self.votes, self.minimum = {}, minimum
        self.neon = FEATURE_NAMES.index('neon')
        self.dark = FEATURE_NAMES.index('dark')
        if guarded and not classifier:
            raise ValueError('Guarded team votes require a classifier')
        from app.team_vote_policy import WindowVote
        self.policy = WindowVote() if guarded else None
        self.guarded_labels = {}
        self.last_decisions = []
        self.last_seen = {}
        self.last_time = None
        self.last_resets = []
        self.crowded_ids = set()
        self.max_gap = .6  # Same short-gap horizon as IdentityGuard.

    def reset(self):
        self.votes.clear()
        self.guarded_labels.clear()
        self.last_decisions = []
        self.last_seen.clear()
        self.crowded_ids.clear()
        self.last_time = None
        self.last_resets = []
        if self.policy:
            self.policy.rows.clear()

    def _advance_time(self, ids, t):
        self.last_resets = []
        if t is None:
            return  # Compatibility for image-only callers without a stream clock.
        t = float(t)
        if not np.isfinite(t):
            raise ValueError('Finite observation time required')
        if self.last_time is not None and t < self.last_time:
            self.reset()
            self.last_resets.append({'reason':'clock_reversed','time':t})
        self.last_time = t
        for tid in ids:
            previous = self.last_seen.get(tid)
            if previous is not None and t - previous > self.max_gap + 1e-9:
                self.votes.pop(tid, None)
                self.guarded_labels.pop(tid, None)
                if self.policy:
                    self.policy.rows.pop(tid, None)
                self.last_resets.append({'id':str(tid),'reason':'observation_gap',
                                         'time':t,'gap_s':t-previous})
            self.last_seen[tid] = t

    def observe(self, tid, frame, box, t=None):
        if self.policy:
            self.observe_many(frame, [list(box[:4])+[tid]], t=t)
            return
        self._advance_time([tid], t)
        self.crowded_ids.discard(tid)  # Single-crop callers supply no overlap context.
        h, w = frame.shape[:2]
        features = box_features(frame, [box[0] / w, box[1] / h, box[2] / w, box[3] / h])
        if self.model:
            probabilities = predict(self.model, features[None])[0]
            letter = LETTER.get(self.model['classes'][int(np.argmax(probabilities))])
        else:
            letter = 'A' if features[self.neon] >= 0.10 else ('B' if features[self.dark] >= 0.30 else None)
        if letter:
            self.votes.setdefault(tid, Counter())[letter] += 1

    def observe_many(self, frame, tracked, t=None):
        """Keep the same per-person features/votes, but invoke the CPU model once."""
        self.last_decisions = []
        self._advance_time([int(row[4]) for row in tracked], t)
        from app.identity_guard import _overlap
        self.crowded_ids = {int(row[4]) for i,row in enumerate(tracked)
                            if any(j!=i and _overlap(row[:4],other[:4])>=.35
                                   for j,other in enumerate(tracked))}
        # After an overlap the raw ID may belong to the other player. Do not
        # inherit its old team vote or learn a mixed-shirt crop. Reconfirm cleanly.
        for tid in self.crowded_ids:
            self.votes.pop(tid, None)
            self.guarded_labels.pop(tid, None)
            if self.policy:
                self.policy.rows.pop(tid, None)
            self.last_resets.append({'id':str(tid),'reason':'overlap_identity_uncertain','time':t})
        if len(tracked) == 0:
            return
        h, w = frame.shape[:2]
        features = np.asarray([box_features(frame, [row[0] / w, row[1] / h,
                                                  row[2] / w, row[3] / h]) for row in tracked])
        if self.model:
            probabilities = predict(self.model, features)
            if len(probabilities) != len(tracked):
                raise ValueError('Role model returned a different number of person results')
            letters = [LETTER.get(self.model['classes'][int(np.argmax(p))]) for p in probabilities]
        else:
            letters = ['A' if f[self.neon] >= .10 else ('B' if f[self.dark] >= .30 else None)
                       for f in features]
        for row, letter in zip(tracked, letters):
            if letter and int(row[4]) not in self.crowded_ids:
                self.votes.setdefault(int(row[4]), Counter())[letter] += 1
        self.last_decisions = []
        if self.policy:
            from app.team_vote_policy import confident
            from app.identity_guard import _overlap
            for i,(row,letter,prob) in enumerate(zip(tracked,letters,probabilities)):
                tid=int(row[4])
                crowded=any(j!=i and _overlap(row[:4],other[:4])>=.35 for j,other in enumerate(tracked))
                accepted=confident(prob) and not crowded
                self.guarded_labels[tid]=self.policy.update(tid,letter if accepted else None)
                self.last_decisions.append({'id':str(tid),'argmax':letter,'probabilities':list(map(float,prob)),
                    'crowded':crowded,'current_crop_accepted':accepted,'label':self.guarded_labels[tid]})

    def label(self, tid):
        if tid in self.crowded_ids:
            return None
        if self.policy:
            return self.guarded_labels.get(tid)
        counts = self.votes.get(tid)
        if not counts:
            return None
        letter, n = counts.most_common(1)[0]
        return letter if n >= self.minimum and letter in ('A', 'B') else None


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
    parser.add_argument('--direction', type=int, choices=(1, -1), required=True, help='+1 when the focus team attacks toward +x (image right)')
    parser.add_argument('--team', choices=('A', 'B'), default='B')
    parser.add_argument('--detector', default='yolo11n.pt')
    parser.add_argument('--classifier')
    parser.add_argument('--guard-team-votes', action='store_true', help='Experimental confidence/margin and finite-window team abstention; not validated for deployment')
    parser.add_argument('--observed-detection-boxes', action='store_true', help='Experimental: observe the exact matched current detection box, preserving tracker state and ID')
    parser.add_argument('--observation-box-mode', choices=('all','shape-outliers'), default='all', help='Experimental shape-outliers replaces width/height discrepancies above 2x only')
    parser.add_argument('--reference-bg', type=float, nargs=4)
    parser.add_argument('--shift', type=float, nargs=2, default=(0.0, 0.0))
    parser.add_argument('--pitch-length', type=float, help='override saved pitch length only when measured')
    parser.add_argument('--pitch-width', type=float, help='override saved pitch width only when measured')
    parser.add_argument('--camera-adaptation', action='store_true', help='experimental per-frame transfer from saved ref_token; abstains and freezes one review scene on failure')
    parser.add_argument('--publish-dir', help='optional local dashboard snapshot directory')
    parser.add_argument('--observations', help='new JSONL measurement file; refuses overwrite')
    parser.add_argument('--motion-guard', action='store_true', help='experimental appearance discontinuity guard and bounded observed-foot display filter')
    parser.add_argument('--analysis-fps', type=float, default=5.0)
    parser.add_argument('--tracking-fps', type=float, help='update detection/tracking faster while keeping coaching at analysis-fps')
    parser.add_argument('--tracking-camera-motion', action='store_true', help='experimental background motion compensation for pixel tracking, not pitch calibration')
    parser.add_argument('--geometric-confirmation', action='store_true', help='confirm tentative tracks by unambiguous repeated IoU instead of confidence-fused IoU')
    parser.add_argument('--active-priority-tracking', action='store_true', help='associate visible tracks before matching lost identities')
    parser.add_argument('--detector-batch-size', type=int, default=1, help='batch identical spatial tiles; 1 preserves sequential inference')
    parser.add_argument('--detector-half', action='store_true', help='GPU FP16 inference; requires separate accuracy validation')
    parser.add_argument('--detector-tile-size', type=int, choices=(640,768), default=768)
    parser.add_argument('--opencv-threads', type=int, help='limit OpenCV workers in this process only')
    parser.add_argument('--torch-cpu-threads', type=int, help='limit small CPU classifier workers in this process only')
    parser.add_argument('--grab-skipped-frames', action='store_true', help='avoid BGR conversion for source frames not used by tracking')
    parser.add_argument('--async-preview', action='store_true', help='publish coherent preview snapshots through a bounded latest-frame worker')
    parser.add_argument('--latest-input', action='store_true', help='bound input backlog; file input requires --realtime pacing')
    parser.add_argument('--tracking-camera-alignment-guard', action='store_true', help='only apply camera warp when current detections support better association')
    parser.add_argument('--tracking-camera-downscale', type=int, choices=(2,4), default=2)
    parser.add_argument('--start', type=float, default=0.0, help='seconds to skip in a file')
    parser.add_argument('--seconds', type=float, default=0.0, help='stop after this many seconds of video (0 = to the end)')
    parser.add_argument('--source-fps', type=float, help='frame rate of the source when the file does not report it correctly')
    parser.add_argument('--realtime', action='store_true', help='pace a file like a live feed')
    parser.add_argument('--alerts', default='alerts.jsonl')
    parser.add_argument('--store', help='the review store of the server: the alerts then go to <store>/alerts/<session>/ and show up on the page /alerts for rating')
    parser.add_argument('--session', default='', help='name of this run (letters, digits, - and _); default: the date and time')
    parser.add_argument('--video-out')
    parser.add_argument('--confidence', type=float, default=0.10)
    parser.add_argument('--recover-low-confidence', action='store_true',
                        help='supplement display with isolated weak observations; never modify tracker, team votes or coaching')
    parser.add_argument('--reviewed-links-store', help='apply source-fingerprinted human reappearance boundaries for a recorded file only')
    parser.add_argument('--tile-camera', choices=('cam1', 'cam3'), help='which picture layout the tile detector uses (the part of the frame that is pitch); default: the camera name')
    parser.add_argument('--device', default='0', help='0 for the first GPU, cpu for no GPU')
    args = parser.parse_args()
    if args.observed_detection_boxes and args.reviewed_links_store:
        parser.error('--observed-detection-boxes cannot reuse --reviewed-links-store: reviewed boundary boxes must be revalidated')
    if args.observation_box_mode!='all' and not args.observed_detection_boxes:
        parser.error('--observation-box-mode requires --observed-detection-boxes')
    if args.opencv_threads is not None:
        if args.opencv_threads < 1:
            parser.error('--opencv-threads must be positive')
        cv2.setNumThreads(args.opencv_threads)
    if args.torch_cpu_threads is not None:
        if args.torch_cpu_threads < 1:
            parser.error('--torch-cpu-threads must be positive')
        import torch
        torch.set_num_threads(args.torch_cpu_threads)
    if args.detector_batch_size < 1:
        parser.error('--detector-batch-size must be positive')
    if args.tracking_camera_alignment_guard and not args.tracking_camera_motion:
        parser.error('--tracking-camera-alignment-guard requires --tracking-camera-motion')
    if args.reviewed_links_store and (args.active_priority_tracking or args.geometric_confirmation or args.latest_input or args.tracking_camera_motion or args.detector_half or args.detector_tile_size != 768 or args.detector_batch_size != 1 or args.analysis_fps != 5 or
            (args.tracking_fps is not None and args.tracking_fps != args.analysis_fps)):
        parser.error('Reviewed raw-ID links belong to the old tracking configuration; preserve the answers but revalidate links before changing cadence/camera motion')

    record = json.loads(Path(args.calibrations).read_text(encoding='utf-8')).get(args.camera)
    if not record:
        raise SystemExit(f'No saved calibration for {args.camera}.')
    if args.camera_adaptation and (args.reference_bg is not None or any(args.shift)):
        parser.error('--camera-adaptation cannot be combined with --reference-bg or nonzero --shift')
    overrides = {k: v for k, v in (('length', args.pitch_length), ('width', args.pitch_width)) if v is not None}
    record = {**record, 'pitch': {**(record.get('pitch') or {}), **overrides}}
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
    from app.tracking_motion import BackgroundMotion, cadence_steps, xyah_tracker_class
    def new_tracker():
        tracker_type = xyah_tracker_class(args.tracking_camera_alignment_guard) if args.tracking_camera_motion else BYTETracker
        if args.active_priority_tracking:
            from app.active_priority_tracker import with_active_priority
            tracker_type = with_active_priority(tracker_type)
        if args.geometric_confirmation:
            from app.confirmation_tracker import with_geometric_confirmation
            tracker_type = with_geometric_confirmation(tracker_type)
        tracker = tracker_type(args=config)
        if args.tracking_camera_motion:
            tracker.gmc = BackgroundMotion(downscale=args.tracking_camera_downscale)
        return tracker
    device = 'cpu' if args.device == 'cpu' else int(args.device)
    tile_camera = args.tile_camera or args.camera
    votes = TeamVotes(args.classifier, guarded=args.guard_team_votes)
    def new_analyzer():
        return LiveAnalyzer(args.direction, fitted['pitch']['length'], fitted['pitch']['width'], args.analysis_fps)
    analyzer = new_analyzer()
    other = 'A' if args.team == 'B' else 'B'

    source = int(args.source) if args.source.isdigit() else args.source
    if args.latest_input and isinstance(source, str) and Path(source).exists() and not args.realtime:
        parser.error('--latest-input on a recorded file requires --realtime')
    if args.latest_input:
        # Warm up before opening the source; these dummy inputs never enter analysis.
        detector.predict([np.zeros((384,384,3),np.uint8)] * args.detector_batch_size,
                         device=device, imgsz=args.detector_tile_size, conf=args.confidence,
                         quantize=16 if args.detector_half else 32, classes=[0], max_det=100, verbose=False)
    capture = cv2.VideoCapture(source)
    if not capture.isOpened():
        raise SystemExit('Could not open the source.')
    is_file = isinstance(source, str) and Path(source).exists()
    reconnect = None
    if args.reviewed_links_store:
        if not is_file:
            parser.error('--reviewed-links-store requires the exact reviewed recording, not a live stream')
        import hashlib
        from app.reappearance_review import reviewed_links
        from app.reviewed_reconnect import ReviewedReconnector, alias_teams, alias_players, alias_boxes
        with open(source,'rb') as handle:
            source_hash=hashlib.file_digest(handle,'sha256').hexdigest()
        decisions=reviewed_links(args.reviewed_links_store,source_hash)
        reconnect=ReviewedReconnector(decisions)
    fps = args.source_fps or capture.get(cv2.CAP_PROP_FPS) or 25.0
    try:
        tracking_step, step = cadence_steps(fps, args.analysis_fps if args.tracking_fps is None else args.tracking_fps, args.analysis_fps)
    except ValueError as exc:
        capture.release()
        parser.error(str(exc))
    config.track_buffer = max(1, round(config.track_buffer * step / tracking_step))
    byte_tracker = new_tracker()
    if is_file and args.start:
        capture.set(cv2.CAP_PROP_POS_FRAMES, int(args.start * fps))
    alerts_path = Path(args.alerts)
    if args.store:
        import re
        from datetime import datetime
        session = args.session or datetime.now().strftime('run-%Y%m%d-%H%M%S')
        if not re.match(r'^[A-Za-z0-9_-]{1,40}$', session):
            raise SystemExit('The session name may only hold letters, digits, - and _ (40 at most).')
        alerts_path = Path(args.store) / 'alerts' / session / 'alerts.jsonl'
        alerts_path.parent.mkdir(parents=True, exist_ok=True)
    camera = CameraSession.from_record(args.calibrations, record, fitted, review_store=args.store) if args.camera_adaptation else None
    camera_status_path = alerts_path.with_suffix('.camera.json')
    from app.live_publish import LivePublisher, dashboard_players
    from app.position_guard import PositionGuard, DisplayPositionGuard
    position_guard = PositionGuard()
    display_guard = DisplayPositionGuard()
    recovery_display = RecoveryDisplay()
    if args.motion_guard:
        from app.identity_guard import IdentityGuard
        from app.foot_stability import FootStabilizer
        identity_guard, foot_filter = IdentityGuard(), FootStabilizer()
    publisher = LivePublisher(args.publish_dir) if args.publish_dir else None
    if publisher and args.async_preview:
        from app.async_publish import AsyncPublisher
        publisher = AsyncPublisher(publisher)
    observations = open(args.observations, 'x', encoding='utf-8') if args.observations else None
    recent_alerts = []
    previous_camera_state = None
    counter = sum(1 for _ in open(alerts_path, encoding='utf-8')) if alerts_path.exists() else 0        # the number of an alert is its line in the file, also when a run is continued
    writer, alerts_out = None, open(alerts_path, 'a', encoding='utf-8')
    wall0, index, shown = time.time(), 0, None
    monotonic0 = time.monotonic()
    latest_reader = None
    if args.latest_input:
        from app.latest_frame import LatestFrameReader
        latest_reader = LatestFrameReader(capture, source_fps=fps, pace=is_file)
    next_tracking = next_analysis = args.start if is_file else 0.
    publication_clock = time.perf_counter()
    stats = {'frames': 0, 'team': 0, 'other': 0, 'camera_ready_frames': 0, 'tracking_updates': 0}
    print(f'Live feedback for team {args.team}, attacking {"right" if args.direction > 0 else "left"}; analysing every {step} frame(s) of {fps:.1f} fps.')
    print(f'Tracking {fps / tracking_step:.2f} fps; analysis {fps / step:.2f} fps; tracking camera compensation={args.tracking_camera_motion}.')
    try:
        while True:
            captured_at = None
            if latest_reader:
                item = latest_reader.read()
                if item is None:
                    break
                index, frame, captured_at = item
                t = args.start + (index - 1) / fps if is_file else captured_at - monotonic0
                if t + 1e-7 < next_tracking:
                    continue
                base = args.start if is_file else 0.
                next_tracking = base + (int((t-base)*fps/tracking_step + 1e-7)+1)*tracking_step/fps
                analysis_due = t + 1e-7 >= next_analysis
                if analysis_due:
                    next_analysis = base + (int((t-base)*fps/step + 1e-7)+1)*step/fps
            else:
                ok, frame = (capture.grab(), None) if args.grab_skipped_frames else capture.read()
                if not ok:
                    print(f'The source ended or could not be read after {index} frames.')
                    break
                index += 1
                if (index - 1) % tracking_step:
                    continue
                if frame is None:
                    ok, frame = capture.retrieve()
                    if not ok:
                        raise RuntimeError('Could not decode a selected tracking frame')
                analysis_due = (index - 1) % step == 0
                t = args.start + (index - 1) / fps if is_file else time.time() - wall0
            if args.seconds and t - (args.start if is_file else 0) > args.seconds:
                break
            if args.realtime and is_file:
                lag = (t - args.start) - (time.time() - wall0)
                if lag > 0:
                    time.sleep(lag)
            camera_ready = True
            processing_start = time.perf_counter()
            if camera and analysis_due:
                status = camera.update(frame, t)
                status['stream_state'] = 'running'
                status['coaching_enabled'] = status['state'] == 'ready'
                camera.write_status(camera_status_path)
                camera_ready = status['state'] == 'ready'
                if not camera_ready or status.get('reset_temporal'):
                    analyzer = new_analyzer()
                    shown = None
                # Ground calibration failure alone does not change pixel track identity.
                # Keep appearance votes through temporary registration failure.
                if status.get('reset_temporal'):
                    byte_tracker = new_tracker()
                    votes.reset()
                    if args.motion_guard:
                        identity_guard, foot_filter = IdentityGuard(), FootStabilizer()
                state = (status['state'], status['reason'])
                if state != previous_camera_state:
                    print('Camera:', status['state'], status['reason'])
                    previous_camera_state = state
                stats['camera_ready_frames'] += camera_ready
            detection_floor = min(args.confidence, config.track_low_thresh) if args.recover_low_confidence else args.confidence
            detection_start = time.perf_counter()
            found = tile_detector.detect(detector, frame, tile_camera, device, detection_floor, batch_size=args.detector_batch_size, half=args.detector_half, tile_size=args.detector_tile_size)
            detector_ms = (time.perf_counter() - detection_start) * 1000
            recovery_found = found
            if args.recover_low_confidence:
                found = [d for d in found if d[4] >= args.confidence]
            array = np.array([[*d[:4], d[4], 0] for d in found], np.float32).reshape(-1, 6)
            tracking_start = time.perf_counter()
            tracked = byte_tracker.update(Boxes(array, frame.shape[:2]), frame if args.tracking_camera_motion else None)
            tracker_ms = (time.perf_counter() - tracking_start) * 1000
            stats['tracking_updates'] += 1
            if not analysis_due:
                continue
            source_tracks = [[float(v) for v in r[:5]] for r in tracked]
            tracker_observation_rows = tracked.tolist() if args.observed_detection_boxes else None
            tracked,identity_events,aliases,reconnect_events,observation_box_checks=prepare_observation_tracks(
                t,frame,tracked,array,identity_guard=identity_guard if args.motion_guard else None,
                reconnect=reconnect,observed=args.observed_detection_boxes,mode=args.observation_box_mode)
            observed_tracks=[[float(v) for v in r[:5]] for r in tracked]
            mine, theirs, drawn = [], [], []
            display_points = {}
            filtered_feet = []
            track_outcomes = []
            votes.observe_many(frame, tracked, t=t)
            for row in tracked:
                box, tid = row[:4], int(row[4])
                letter = votes.label(tid)
                outcome = {'id': str(tid), 'team': letter,
                           'projection_status': 'team_excluded',
                           'position_status': 'not_evaluated', 'point_m': None}
                track_outcomes.append(outcome)
                if letter is None:
                    continue
                point = camera.point(box, frame) if camera else feet_to_metres(fitted, box, frame.shape[1], frame.shape[0], tuple(args.shift), tuple(args.reference_bg) if args.reference_bg else None)
                outcome['projection_status'] = 'projection_rejected' if point is None else 'projected'
                if point is None:
                    continue
                outcome['point_m'] = list(map(float, point))
                if args.motion_guard:
                    overlaps = any(int(other[4]) != tid and tile_detector.overlap_share(box, other[:4]) > .25 for other in tracked)
                    foot = foot_filter.update(t, tid, box, ambiguous=overlaps)
                    adjusted = foot['box']
                    filtered = camera.point(adjusted, frame) if camera else feet_to_metres(fitted, adjusted, frame.shape[1], frame.shape[0], tuple(args.shift), tuple(args.reference_bg) if args.reference_bg else None)
                    # Perspective can amplify even a small pixel adjustment: bound in metres too.
                    delta = float(np.linalg.norm(np.asarray(filtered)-point)) if filtered is not None else None
                    if filtered is not None and delta <= .8:
                        display_points[str(tid)] = filtered
                    filtered_feet.append({'id':str(tid),'raw':list(map(float,point)),
                        'display':list(map(float,display_points.get(str(tid),point))),
                        'pixel_shift':foot['pixel_shift'],'kind':foot['kind'],
                        'projection_shift_m':delta, 'accepted':filtered is not None and delta <= .8})
                (mine if letter == args.team else theirs).append((tid, point[0], point[1]))
                drawn.append((box, letter))
            stats['frames'] += 1
            stats['team'] += len(mine)
            stats['other'] += len(theirs)
            raw_mine, raw_theirs = mine, theirs
            guarded, rejected = position_guard.filter(t, {'home': mine, 'away': theirs})
            mine, theirs = guarded['home'], guarded['away']
            retained_ids = {str(row[0]) for row in mine + theirs}
            for outcome in track_outcomes:
                if outcome['projection_status'] == 'projected':
                    outcome['position_status'] = 'retained' if outcome['id'] in retained_ids else 'rejected'
            coaching_ready = camera_ready and len(mine) <= 11 and len(theirs) <= 11
            if not coaching_ready:
                analyzer.interrupt_observations(t)
            linked = alias_teams({'home':mine,'away':theirs},aliases) if reconnect else {'home':mine,'away':theirs}
            new = analyzer.update(t, linked['home'], linked['away']) if coaching_ready else []
            measured = dashboard_players({'home': mine, 'away': theirs}, fitted['pitch'])
            display_rows={name:[(tid,*display_points.get(str(tid),(px,py))) for tid,px,py in rows]
                          for name,rows in (('home',mine),('away',theirs))}
            display_checks={'raw_fallbacks':0,'omitted':0}
            if args.motion_guard:
                display_rows,display_checks=display_guard.filter(t,{'home':mine,'away':theirs},display_rows)
            displayed = dashboard_players(display_rows, fitted['pitch'])
            recovered = []
            if args.recover_low_confidence:
                project = lambda box: camera.point(box, frame) if camera else feet_to_metres(fitted, box, frame.shape[1], frame.shape[0], tuple(args.shift), tuple(args.reference_bg) if args.reference_bg else None)
                recovered = recovery_display.update(t, recovery_found, tracked, displayed, project, fitted['pitch'], camera_ready, args.confidence)
                displayed = displayed + recovered
            unlinked_players = measured
            if reconnect:
                measured = alias_players(measured, aliases)
                displayed = alias_players(displayed, aliases)
            recent_alerts = [a for a in recent_alerts if coaching_ready and 0 <= t-a['time'] <= 8] + new
            elapsed_ms = (time.perf_counter()-processing_start)*1000
            publication_time = time.perf_counter()
            publication_fps = 1 / max(publication_time - publication_clock, .000001)
            publication_clock = publication_time
            if observations:
                observations.write(json.dumps({'time':t, 'camera_ready':camera_ready,
                    'detected':len(found), 'tracked':len(tracked), 'players':measured,
                    'raw_positions': {'home': raw_mine, 'away': raw_theirs},
                    'display_players': displayed, 'recovered_players': recovered, 'foot_filter': filtered_feet,
                    'display_checks': display_checks,
                    'source_tracks': source_tracks, 'identity_events': identity_events,
                    'diagnostic_schema': 1, 'tracking_detections': array.tolist(),
                    'track_outcomes': track_outcomes,
                    'observed_tracks': observed_tracks, 'observation_box_checks': observation_box_checks,
                    'observed_detection_rows': array.tolist() if args.observed_detection_boxes else None,
                    'tracker_observation_rows': tracker_observation_rows,
                    'reconnect_events':reconnect_events,'identity_aliases':aliases,'unlinked_players':unlinked_players,
                    'position_rejected': rejected, 'alerts':new, 'processing_ms':elapsed_ms,
                    'team_vote_decisions': votes.last_decisions,
                    'team_vote_resets': votes.last_resets,
                    'tracking_updates':stats['tracking_updates'], 'tracking_target_fps':fps/tracking_step,
                    'analysis_target_fps':fps/step, 'publication_fps':publication_fps,
                    'source_sequence':index, 'input_age_ms':(time.monotonic()-captured_at)*1000 if captured_at is not None else None,
                    'stage_ms':{'detector':detector_ms, 'tracker':tracker_ms, 'analysis_other':max(0,elapsed_ms-detector_ms-tracker_ms)},
                    'tracking_camera_motion':byte_tracker.gmc.last if hasattr(byte_tracker,'gmc') else None,
                    'geometric_confirmation':args.geometric_confirmation,
                    'active_priority_tracking':args.active_priority_tracking}, ensure_ascii=False)+'\n')
                observations.flush()
            if publisher:
                publisher.publish(frame, displayed, recent_alerts, t, fitted['pitch'], camera_ready,
                                  publication_fps if args.tracking_fps is not None or args.tracking_camera_motion else 1000/max(elapsed_ms, 0.001), elapsed_ms,
                                  raw_players=measured if args.motion_guard or args.recover_low_confidence else None)
            boxes_now = {int(r[4]): r[:4] for r in tracked}
            if reconnect:
                boxes_now = alias_boxes(boxes_now, aliases)
            for alert in new:
                shown = (alert, t)
                if alert.get('detail'):
                    picture = lane_picture(frame, alert['detail'], boxes_now)
                    cv2.imwrite(str(alerts_path.with_name(f'alerts_{counter:04d}.jpg')), picture)
                    frame = picture
                alerts_out.write(json.dumps(alert, ensure_ascii=False) + '\n')
                alerts_out.flush()
                counter += 1
                print(f"[{int(alert['time'] // 60)}:{int(alert['time'] % 60):02d}] {alert['title']}: {alert['text']}")
            if args.video_out:
                for box, letter in drawn:
                    cv2.rectangle(frame, (int(box[0]), int(box[1])), (int(box[2]), int(box[3])), TEAM_BGR[letter], 1, cv2.LINE_AA)
                if shown:
                    banner(frame, shown[0], t - shown[1])
                if writer is None:
                    writer = cv2.VideoWriter(args.video_out, cv2.VideoWriter_fourcc(*'mp4v'), args.analysis_fps, (frame.shape[1], frame.shape[0]))
                writer.write(frame)
    finally:
        if observations:
            observations.close()
        if latest_reader:
            latest_reader.close(timeout=10)
        else:
            capture.release()
        alerts_out.close()
        if camera:
            camera.status['stream_state'] = 'ended'
            camera.status['coaching_enabled'] = False
            camera.write_status(camera_status_path)
        if writer:
            writer.release()
        if publisher and args.async_preview:
            publisher.close(timeout=10)
    n = max(1, stats['frames'])
    if latest_reader:
        print('Latest input:', latest_reader.stats)
    if publisher and args.async_preview:
        print('Async preview:', publisher.stats)
    print(f"Tracking updates: {stats['tracking_updates']}; camera motion: {byte_tracker.gmc.counts if hasattr(byte_tracker, 'gmc') else 'disabled'}")
    if camera:
        print(f"Camera accepted: {stats['camera_ready_frames']}/{stats['frames']} analysed frames; not a metric accuracy measurement.")
    print(f"Finished: {stats['frames']} frames analysed, on average {stats['team'] / n:.1f} players of team {args.team} and {stats['other'] / n:.1f} of team {other} placed on the pitch.")


if __name__ == '__main__':
    main()
