"""Local-only, explicitly saved frame labels; never affect live inference."""
import base64
import hashlib
import json
import math
import os
import re
import secrets
import tempfile
import threading
import time
from pathlib import Path
import cv2
import numpy as np
from app.team_suggestions import shirt_histogram


CAMERA_ID = re.compile(r'^cam[0-9]$')
PITCH_LIMITS = {'length': (20, 130), 'width': (15, 100), 'circle_r': (1, 15), 'goal_width': (1.5, 9),
                'pa_depth': (3, 25), 'pa_width': (8, 50), 'ga_depth': (1, 10), 'ga_width': (4, 25)}


def _landmark_ids():
    ids = {'center', 'half_near', 'half_far', 'circle_left', 'circle_right', 'circle_near', 'circle_far'}
    for side in ('l', 'r'):
        for depth in ('near', 'far'):
            ids.update({f'corner_{side}_{depth}', f'post_{side}_{depth}', f'pa_{side}_{depth}',
                        f'pa_goalline_{side}_{depth}', f'ga_{side}_{depth}', f'ga_goalline_{side}_{depth}'})
    return ids


LANDMARK_IDS = _landmark_ids()


class TrainingLabels:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.lock = threading.Lock()
        self.latest = None
        self.sessions = {}

    def publish(self, frame, tracks, timestamp, source, groups=None, provenance=None, role_hints=None):
        h, w = frame.shape[:2]
        people = []
        for box, track_id in tracks:
            values = [float(box[0])/w, float(box[1])/h, float(box[2])/w, float(box[3])/h]
            if not all(math.isfinite(x) for x in values):
                continue
            x1,y1,x2,y2 = [max(0., min(1., x)) for x in values]
            if x2 > x1 and y2 > y1:
                hint = (groups or {}).get(str(track_id))
                role_hint = (role_hints or {}).get(str(track_id))
                people.append({'id': str(track_id), 'bbox': [x1,y1,x2,y2],
                               'suggested_color_group': hint if type(hint) is int and hint in (0, 1) else None,
                               'role_hint_unverified': role_hint if role_hint in ('referee', 'goalkeeper', 'uncertain', 'spectator') else None})
        counts = {p['id']: sum(q['id'] == p['id'] for q in people) for p in people}
        with self.lock:
            self.latest = (frame.copy(), [p for p in people if counts[p['id']] == 1], timestamp, source, time.monotonic(), provenance or {'split': 'unassigned'})

    def freeze(self):
        with self.lock:
            if self.latest is None or time.monotonic() - self.latest[4] > 3:
                return None
            frame, people, timestamp, source, _, provenance = self.latest
            ok, jpeg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
            if not ok or jpeg.nbytes > 12_000_000:
                return None
            token = secrets.token_hex(16)
            self.sessions = {k:v for k,v in self.sessions.items() if time.time()-v['created'] < 1800}
            while len(self.sessions) >= 5:
                self.sessions.pop(next(iter(self.sessions)))
            self.directory.mkdir(parents=True, exist_ok=True)
            pending = self.directory / 'pending'
            pending.mkdir(exist_ok=True)
            metadata = {'people': people, 'timestamp': timestamp, 'source': source, 'created': time.time(), 'source_provenance': provenance}
            (pending / (token + '.jpg')).write_bytes(jpeg.tobytes())
            (pending / (token + '.json')).write_text(json.dumps(metadata, ensure_ascii=False), encoding='utf-8')
            self.sessions[token] = {**metadata, 'image': jpeg.tobytes()}
            return {'token': token, 'image': base64.b64encode(jpeg).decode('ascii'), 'people': people, 'timestamp': timestamp}

    def _load(self, token):
        session = self.sessions.get(token)
        if not session:
            pending = self.directory / 'pending'
            try:
                meta = json.loads((pending / (token + '.json')).read_text(encoding='utf-8'))
                session = {**meta, 'image': (pending / (token + '.jpg')).read_bytes()}
            except (OSError, ValueError, TypeError):
                return None
        return session

    def latest_pending(self):
        with self.lock:
            pending = self.directory / 'pending'
            candidates = sorted(pending.glob('*.json'), key=lambda p:p.stat().st_mtime, reverse=True) if pending.exists() else []
            for path in candidates:
                if len(path.stem) == 32 and all(c in '0123456789abcdef' for c in path.stem):
                    session = self._load(path.stem)
                    if session:
                        return {'token': path.stem, 'image': base64.b64encode(session['image']).decode('ascii'),
                                'people': session['people'], 'timestamp': session['timestamp']}
            return None

    def _label_counts(self):
        """Saved answers per scene token (the lock is already held by the caller)."""
        counts = {}
        if not self.directory.is_dir():
            return counts
        for path in self.directory.glob('*.json'):
            try:
                image = json.loads(path.read_text(encoding='utf-8')).get('image')
            except (OSError, ValueError, AttributeError):
                continue
            if isinstance(image, str) and image.endswith('.jpg') and len(image) == 36:
                counts[image[:-4]] = counts.get(image[:-4], 0) + 1
        return counts

    def thumbnail(self, token, width=192):
        """Small cached JPEG of a scene for the scene picker; None when the scene does not exist."""
        if not isinstance(token, str) or len(token) != 32 or any(c not in '0123456789abcdef' for c in token):
            return None
        source = self.directory / 'pending' / (token + '.jpg')
        target = self.directory / 'thumbs' / (token + '.jpg')
        with self.lock:
            if target.is_file():
                return target
            image = cv2.imread(str(source)) if source.is_file() else None
            if image is None:
                return None
            height, original = image.shape[:2]
            small = cv2.resize(image, (width, max(1, round(width * height / original))), interpolation=cv2.INTER_AREA)
            ok, data = cv2.imencode('.jpg', small, [cv2.IMWRITE_JPEG_QUALITY, 78])
            if not ok:
                return None
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_suffix('.tmp')
            temporary.write_bytes(data.tobytes())
            os.replace(temporary, target)
            return target

    def scene_queue(self):
        """Ordered list of saved scenes so a reviewer can move between them.

        Order follows an optional numeric ``order`` field, then creation time.
        Unreadable or incomplete scenes are skipped, never raised.
        """
        with self.lock:
            pending = self.directory / 'pending'
            scenes = []
            label_counts = self._label_counts()
            for path in (pending.glob('*.json') if pending.exists() else []):
                if len(path.stem) != 32 or any(c not in '0123456789abcdef' for c in path.stem):
                    continue
                try:
                    meta = json.loads(path.read_text(encoding='utf-8'))
                    if not (pending / (path.stem + '.jpg')).is_file():
                        continue
                    order = meta.get('order', meta.get('created', 0))
                    order = float(order) if type(order) in (int, float) and math.isfinite(order) else 0.0
                    prov = meta.get('source_provenance') if isinstance(meta.get('source_provenance'), dict) else {}
                    clip_time = prov.get('clip_time_sec')
                    clip_time = float(clip_time) if type(clip_time) in (int, float) and math.isfinite(clip_time) else None
                    split = prov.get('split') if prov.get('split') in ('unassigned', 'eval', 'buffer_excluded', 'train') else None
                    camera = prov.get('camera_setting') if isinstance(prov.get('camera_setting'), str) and CAMERA_ID.match(prov['camera_setting']) else None
                    bg = prov.get('bg_to_ref')
                    bg = [float(v) for v in bg] if (camera and isinstance(bg, list) and len(bg) == 4 and
                                                    all(type(v) in (int, float) and math.isfinite(v) for v in bg)) else None
                    scenes.append({'token': path.stem, 'order': order, 'timestamp': meta.get('timestamp'),
                                   'source': str(meta.get('source', ''))[:120],
                                   'box_count': len(meta.get('people', [])),
                                   'clip_time': clip_time, 'split': split, 'camera': camera, 'bg': bg,
                                   'label_count': label_counts.get(path.stem, 0)})
                except (OSError, ValueError, TypeError, AttributeError):
                    continue
            scenes.sort(key=lambda s: (s['order'], s['token']))
            return scenes

    def _regions_path(self):
        return self.directory / 'regions' / 'pitch_regions.json'

    def _read_regions(self):
        try:
            data = json.loads(self._regions_path().read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def pitch_regions(self):
        """Pitch polygons (normalised image coordinates) keyed by the scene they were drawn on."""
        with self.lock:
            return self._read_regions()

    def set_pitch_region(self, token, polygon):
        """Save or (with an empty polygon) clear the pitch polygon drawn on one scene.

        The polygon only drives review hints in the page; it never saves a label.
        """
        if not isinstance(token, str) or len(token) != 32 or any(c not in '0123456789abcdef' for c in token):
            raise ValueError('Invalid snapshot token')
        if not isinstance(polygon, (list, tuple)) or len(polygon) > 40 or 0 < len(polygon) < 3:
            raise ValueError('A pitch region needs 3 to 40 points')
        points = []
        for point in polygon:
            if (not isinstance(point, (list, tuple)) or len(point) != 2 or
                    any(type(v) not in (float, int) or not math.isfinite(v) or not 0 <= v <= 1 for v in point)):
                raise ValueError('Invalid normalized point')
            points.append([float(point[0]), float(point[1])])
        if points:
            area = abs(sum(points[i][0] * points[(i + 1) % len(points)][1] -
                           points[(i + 1) % len(points)][0] * points[i][1] for i in range(len(points)))) / 2
            if area < 0.01:
                raise ValueError('Pitch region is too small')
        with self.lock:
            if not (self.directory / 'pending' / (token + '.json')).is_file():
                raise ValueError('화면이 만료됐습니다.')
            regions = self._read_regions()
            if points:
                regions[token] = points
            else:
                regions.pop(token, None)
            target = self._regions_path()
            target.parent.mkdir(parents=True, exist_ok=True)
            temp_name = None
            try:
                with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=target.parent,
                                                 suffix='.tmp', delete=False) as output:
                    temp_name = output.name
                    json.dump(regions, output, ensure_ascii=False)
                os.replace(temp_name, target)
            finally:
                if temp_name and os.path.exists(temp_name):
                    os.unlink(temp_name)
            return regions

    def scene_labels(self, token):
        """Saved answers for one scene (read only), for drawing the minimap from confirmed roles and teams."""
        if not isinstance(token, str) or len(token) != 32 or any(c not in '0123456789abcdef' for c in token):
            raise ValueError('Invalid snapshot token')
        with self.lock:
            labels = []
            if not self.directory.is_dir():
                return labels
            for path in self.directory.glob('*.json'):
                try:
                    label = json.loads(path.read_text(encoding='utf-8'))
                except (OSError, ValueError):
                    continue
                if not isinstance(label, dict) or label.get('image') != token + '.jpg':
                    continue
                bbox = label.get('bbox_image_norm')
                if not (isinstance(bbox, list) and len(bbox) == 4):
                    continue
                labels.append({'track_id': str(label.get('track_id', ''))[:128], 'role': label.get('role'),
                               'team_group': label.get('team_group'), 'bbox': bbox,
                               'origin': label.get('annotation_origin')})
            return labels

    def _calibration_path(self):
        return self.directory / 'calibration' / 'calibrations.json'

    def _read_calibrations(self):
        try:
            data = json.loads(self._calibration_path().read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def calibrations(self):
        """Pitch calibrations per camera setting: landmark clicks in the setting's reference frame."""
        with self.lock:
            return self._read_calibrations()

    def set_calibration(self, setting, points, pitch, ref_token=None):
        """Save (or with no points, clear) the calibration clicks of one camera setting."""
        if not isinstance(setting, str) or not CAMERA_ID.match(setting):
            raise ValueError('Invalid camera setting')
        if not isinstance(points, (list, tuple)) or len(points) > 40 or 0 < len(points) < 4:
            raise ValueError('A calibration needs 4 to 40 landmark points')
        clean = {}
        for point in points:
            landmark, x, y = point.get('landmark'), point.get('x'), point.get('y')
            if landmark not in LANDMARK_IDS:
                raise ValueError('Unknown landmark')
            if any(type(v) not in (float, int) or not math.isfinite(v) or not -0.5 <= v <= 1.5 for v in (x, y)):
                raise ValueError('Invalid normalized point')
            clean[landmark] = {'landmark': landmark, 'x': float(x), 'y': float(y)}
        if points and len(clean) < 4:
            raise ValueError('A calibration needs 4 different landmarks')
        if not isinstance(pitch, dict) or set(pitch) != set(PITCH_LIMITS):
            raise ValueError('Pitch dimensions are required')
        dims = {}
        for key, (low, high) in PITCH_LIMITS.items():
            value = pitch[key]
            if type(value) not in (float, int) or not math.isfinite(value) or not low <= value <= high:
                raise ValueError(f'Pitch dimension {key} must be between {low} and {high}')
            dims[key] = float(value)
        if ref_token is not None and (not isinstance(ref_token, str) or len(ref_token) != 32 or
                                      any(c not in '0123456789abcdef' for c in ref_token)):
            raise ValueError('Invalid snapshot token')
        with self.lock:
            data = self._read_calibrations()
            if setting in data:
                # Whatever is replaced or cleared stays in a history file, so an accidental clear can be undone by hand.
                history = self._calibration_path().with_name('calibration_history.jsonl')
                history.parent.mkdir(parents=True, exist_ok=True)
                with history.open('a', encoding='utf-8') as output:
                    output.write(json.dumps({'setting': setting, 'replaced_at': time.strftime('%Y-%m-%d %H:%M:%S'),
                                             'record': data[setting]}, ensure_ascii=False) + '\n')
            if clean:
                data[setting] = {'points': list(clean.values()), 'pitch': dims, 'ref_token': ref_token,
                                 'pitch_dimensions_are_estimates': True, 'updated': time.strftime('%Y-%m-%d %H:%M:%S')}
            else:
                data.pop(setting, None)
            target = self._calibration_path()
            target.parent.mkdir(parents=True, exist_ok=True)
            temp_name = None
            try:
                with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=target.parent,
                                                 suffix='.tmp', delete=False) as output:
                    temp_name = output.name
                    json.dump(data, output, ensure_ascii=False)
                os.replace(temp_name, target)
            finally:
                if temp_name and os.path.exists(temp_name):
                    os.unlink(temp_name)
            return data

    def restore(self, token):
        with self.lock:
            session = self._load(token)
            if not session:
                raise ValueError('화면이 만료됐습니다.')
            return {'token': token, 'image': base64.b64encode(session['image']).decode('ascii'),
                    'people': session['people'], 'timestamp': session['timestamp']}

    def add_manual_box(self, token, bbox):
        """Persist a user-drawn box in the same frozen frame, with no role inferred."""
        if not isinstance(token, str) or len(token) != 32 or any(c not in '0123456789abcdef' for c in token):
            raise ValueError('Invalid snapshot token')
        if (not isinstance(bbox, (list, tuple)) or len(bbox) != 4 or
                any(type(v) not in (float, int) or not math.isfinite(v) or not 0 <= v <= 1 for v in bbox)):
            raise ValueError('Invalid normalized box')
        x1, y1, x2, y2 = bbox
        if x2 <= x1 or y2 <= y1:
            raise ValueError('Box must have positive area')
        with self.lock:
            session = self._load(token)
            if not session:
                raise ValueError('화면이 만료됐습니다.')
            if len(session['people']) >= 100:
                raise ValueError('한 화면에는 최대 100개의 상자만 추가할 수 있습니다.')
            person = {'id': 'manual-' + secrets.token_hex(8), 'bbox': list(bbox),
                      'suggested_color_group': None, 'annotation_origin': 'human_drawn'}
            metadata = {k: v for k, v in session.items() if k != 'image'}
            metadata['people'] = [*session['people'], person]
            pending = self.directory / 'pending'
            pending.mkdir(parents=True, exist_ok=True)
            temp_name = None
            try:
                with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=pending,
                                                 suffix='.tmp', delete=False) as output:
                    temp_name = output.name
                    json.dump(metadata, output, ensure_ascii=False)
                os.replace(temp_name, pending / (token + '.json'))
            finally:
                if temp_name and os.path.exists(temp_name):
                    os.unlink(temp_name)
            self.sessions[token] = {**metadata, 'image': session['image']}
            return person

    def delete_manual_box(self, token, person_id):
        """Remove a box the reviewer drew by hand, but only while no answer has been saved for it."""
        if not isinstance(token, str) or len(token) != 32 or any(c not in '0123456789abcdef' for c in token):
            raise ValueError('Invalid snapshot token')
        if not isinstance(person_id, str) or not re.fullmatch(r'manual-[0-9a-f]{16}', person_id):
            raise ValueError('Only hand-drawn boxes can be deleted')
        with self.lock:
            session = self._load(token)
            if not session:
                raise ValueError('화면이 만료됐습니다.')
            person = next((p for p in session['people'] if p['id'] == person_id), None)
            if person is None or person.get('annotation_origin') != 'human_drawn':
                raise ValueError('직접 그린 상자만 지울 수 있습니다.')
            label_id = hashlib.sha256((token + ':' + person_id).encode()).hexdigest()[:32]
            if (self.directory / (label_id + '.json')).is_file():
                raise ValueError('이미 답을 저장한 상자는 지울 수 없습니다.')
            metadata = {k: v for k, v in session.items() if k != 'image'}
            metadata['people'] = [p for p in session['people'] if p['id'] != person_id]
            pending = self.directory / 'pending'
            temp_name = None
            try:
                with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=pending, suffix='.tmp', delete=False) as output:
                    temp_name = output.name
                    json.dump(metadata, output, ensure_ascii=False)
                os.replace(temp_name, pending / (token + '.json'))
            finally:
                if temp_name and os.path.exists(temp_name):
                    os.unlink(temp_name)
            if token in self.sessions:
                self.sessions[token] = {**metadata, 'image': session['image']}
            return len(metadata['people'])

    def save(self, token, track_id, role, team_group, shirt_color, shirt_detail='', *, only_if_new=False):
        with self.lock:
            session = self._load(token)
            if not session:
                raise ValueError('화면이 만료됐습니다. 새 화면을 가져오세요.')
            person = next((p for p in session['people'] if p['id'] == track_id), None)
            if person is None:
                raise ValueError('선택한 사람이 해당 화면에 없습니다.')
            self.directory.mkdir(parents=True, exist_ok=True)
            image_path = self.directory / (token + '.jpg')
            if not image_path.exists():
                image_path.write_bytes(session['image'])
            label_id = hashlib.sha256((token + ':' + track_id).encode()).hexdigest()[:32]
            label = {'image': image_path.name, 'captured_at': session['timestamp'], 'source': session['source'],
                     'track_id': track_id, 'bbox_image_norm': person['bbox'], 'role': role, 'team': 'unknown',
                     'team_group': team_group, 'shirt_color': shirt_color,
                     'suggested_color_group_unverified': person.get('suggested_color_group'),
                     'provenance': 'human_confirmed_detection', 'note': 'Not a complete annotation; track ID is temporary.'}
            label['annotation_origin'] = person.get('annotation_origin', 'model_candidate')
            if label['annotation_origin'] == 'human_drawn':
                label['provenance'] = 'human_drawn_and_confirmed'
            label['training_disposition'] = {'shadow':'background_negative', 'spectator':'person_outside_play',
                                             'duplicate':'duplicate_box', 'unknown':'unresolved'}.get(role, 'person_role')
            label['source_provenance'] = session.get('source_provenance', {'split': 'unassigned'})
            label['shirt_detail'] = shirt_detail.strip()
            label['role_hint_unverified'] = person.get('role_hint_unverified')
            path = self.directory / (label_id + '.json')
            if only_if_new:
                try:
                    with path.open('x', encoding='utf-8') as stream:
                        json.dump(label, stream, ensure_ascii=False, indent=2)
                except FileExistsError:
                    raise ValueError('이미 저장된 답변입니다. 수정하려면 직접 분류를 이용하세요.') from None
                return label_id
            temporary = path.with_suffix('.tmp')
            temporary.write_text(json.dumps(label, ensure_ascii=False, indent=2), encoding='utf-8')
            temporary.replace(path)
            return label_id

    def suggest(self, token):
        """Suggest same-frame kit groups from confirmed outfield players only.

        A group is just a suggestion: no roles or files are created. Never use
        goalkeeper/referee/legacy colour labels, cross-frame or cross-match IDs.
        """
        with self.lock:
            session = self._load(token)
            if not session:
                raise ValueError('화면이 만료됐습니다.')
            img = cv2.imdecode(np.frombuffer(session['image'], dtype=np.uint8), cv2.IMREAD_COLOR)
            if img is None:
                raise ValueError('화면을 읽을 수 없습니다.')
            h, w = img.shape[:2]
            features = {}
            labels = {}
            confirmed = set()
            for person in session['people']:
                ident = person['id']
                box = person['bbox']
                features[ident] = shirt_histogram(img, [box[0]*w, box[1]*h, box[2]*w, box[3]*h])
                label_id = hashlib.sha256((token + ':' + ident).encode()).hexdigest()[:32]
                try:
                    label = json.loads((self.directory / (label_id + '.json')).read_text(encoding='utf-8'))
                except (OSError, ValueError):
                    continue
                confirmed.add(ident)
                if label.get('role') == 'player' and label.get('team_group') in ('team_a', 'team_b') and features[ident] is not None:
                    labels[ident] = label['team_group']
            result = {}
            for ident, feature in features.items():
                if feature is None or ident in confirmed:
                    continue
                distances = {group: min((float(np.linalg.norm(feature-features[ref])) for ref, g in labels.items() if g == group), default=float('inf')) for group in ('team_a','team_b')}
                ranked = sorted(distances, key=distances.get)
                best, other = distances[ranked[0]], distances[ranked[1]]
                if best <= .12 and other - best >= .15:
                    refs = [ref for ref, group in labels.items() if group == ranked[0] and float(np.linalg.norm(feature-features[ref])) <= .12]
                    result[ident] = {'team_group': ranked[0], 'distance': round(best, 3), 'reference_ids': refs,
                                     'status': 'unverified', 'role': 'unknown'}
            return result

    def confirmed_ids(self, token):
        """Return saved IDs from this exact snapshot, including non-players."""
        with self.lock:
            session = self._load(token)
            if not session:
                raise ValueError('화면이 만료됐습니다.')
            return [person['id'] for person in session['people']
                    if (self.directory / (hashlib.sha256((token + ':' + person['id']).encode()).hexdigest()[:32] + '.json')).is_file()]
