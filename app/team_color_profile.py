"""Team colour profile of one match: the coach says once which colour group is the own team, and the rest of the analysis follows that choice.

Why: the live run used to assume "neon shirts are team A, dark shirts are team B" (scripts/run_live_feedback.py, scripts/track_review_clip.py) and the team model was trained on one match.
A new match with other clothes (a vest, another colour) needs the colours of the match itself. This module has no assumption about a colour:

1. shirt_colour(): the colour of the upper body of a box as a point in the Lab colour space (median of the torso patch, grass pixels left out).
2. split_teams(): the colours of the people seen in the first seconds are split into two team groups; people far from both groups (referee, goalkeeper) are 'others'.
3. The coach looks at pictures of both groups and says which one is the own team (web/team_select.html, app/team_select_routes.py).
4. make_profile() / save_profile(): the choice is stored as a small JSON file (<store>/service/team_profile.json).
5. ProfileClassifier.classify(): later boxes are labelled 'own', 'opponent' or None (unclear) by their colour distance to the two stored colours.

Nothing here reads a video or trains a model. The pictures are made by scripts/team_select_prepare.py.
"""
import json
import os
import tempfile
import time
from pathlib import Path

import numpy as np

PROFILE_VERSION = 1
MIN_HEIGHT_PX = 30          # smaller boxes have too few shirt pixels. 40 px left only 3 readable people per scene of this match (35 scenes), 30 px gave 11, 24 px gave 17 (wiki/team-select.md)
LIGHT_WEIGHT = 0.6          # lightness changes with the place on the pitch (sun, shade, lamps); the colour axes a and b count fully
SCALE_FLOOR = 4.0           # the spread of a group never counts as smaller than this (Lab units), so that a few similar boxes do not make a razor-thin group
OUTLIER_FACTOR = 3.5        # a person farther than this many spreads from both groups is not a player of either team
MIN_SEPARATION = 1.5        # distance of the two group colours measured in spreads; below it the page warns that the colours are close (proposed value: in this match the real colours give 1.8 to 2.1, repainted ones 2.4 to 9.9)
MIN_PER_TEAM = 4            # boxes needed in each team group before a choice is offered
CLASSIFY_RATIO = 0.7        # the nearer group colour must be this much nearer than the other one, else the box stays unclear


def shirt_colour(image, box, min_height=MIN_HEIGHT_PX):
    """Colour point [0.6 * L, a, b] (Lab, L 0..100, a and b about -128..127) of the upper body of a box [x1, y1, x2, y2] in pixels, or None when the box is too small or has no usable pixels."""
    import cv2
    x1, y1, x2, y2 = [float(v) for v in box[:4]]
    h, w = y2 - y1, x2 - x1
    if h < min_height or w < 4:
        return None
    top, bottom = int(y1 + .15 * h), int(y1 + .6 * h) + 1
    left, right = int(x1 + .2 * w), int(x2 - .2 * w) + 1
    patch = image[max(0, top):max(0, bottom), max(0, left):max(0, right)]
    if patch.size == 0 or patch.shape[0] < 3 or patch.shape[1] < 2:
        return None
    hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV).reshape(-1, 3)
    grass = (hsv[:, 0] >= 45) & (hsv[:, 0] <= 85) & (hsv[:, 1] > 70) & (hsv[:, 2] > 40)
    lab = cv2.cvtColor(patch, cv2.COLOR_BGR2LAB).reshape(-1, 3).astype(np.float32)
    keep = lab[~grass] if (~grass).sum() >= 6 else lab
    lightness, a, b = np.median(keep, axis=0)
    return np.array([LIGHT_WEIGHT * lightness * 100.0 / 255.0, a - 128.0, b - 128.0], np.float32)


def _kmeans2(points, seeds=24):
    """Two groups by k-means with many starts; the score caps the distance of far points so that one referee does not decide the split."""
    rng = np.random.default_rng(0)
    best = None
    for _ in range(seeds):
        i, j = rng.choice(len(points), 2, replace=False)
        centres = points[[i, j]].astype(np.float64)
        for _ in range(30):
            distance = np.linalg.norm(points[:, None, :] - centres[None], axis=2)
            labels = distance.argmin(1)
            moved = np.array([np.median(points[labels == c], axis=0) if (labels == c).any() else centres[c] for c in (0, 1)])
            if np.allclose(moved, centres):
                break
            centres = moved
        distance = np.linalg.norm(points[:, None, :] - centres[None], axis=2).min(1)
        score = float(np.minimum(distance, 25.0).sum())
        if best is None or score < best[0]:
            best = (score, centres)
    return best[1]


def _group_others(points, indexes, radius=15.0):
    """The far people grouped by a simple radius rule: [{'members': [index...], 'centre': [...]}]; only for the picture of 'other people' (referee, goalkeeper)."""
    groups = []
    for index in indexes:
        for g in groups:
            if np.linalg.norm(points[index] - np.array(g['centre'])) <= radius:
                g['members'].append(index)
                g['centre'] = np.mean([points[m] for m in g['members']], axis=0).tolist()
                break
        else:
            groups.append({'members': [index], 'centre': points[index].astype(float).tolist()})
    return sorted(groups, key=lambda g: -len(g['members']))


def split_teams(colours, min_per_team=MIN_PER_TEAM):
    """colours: list of colour points from shirt_colour(). Returns a dict:
    ok (bool), reason (text when not ok), groups: two dicts {centre, scale, members} ordered by size (larger first), others: [{members, centre}], separation (group distance in spreads).
    Members are indexes into `colours`. Not ok when too few people or a group below min_per_team. weak=True (still ok) when the two colours are close (separation below MIN_SEPARATION): the person then looks at the pictures with more care."""
    points = np.asarray(colours, np.float64).reshape(-1, 3)
    n = len(points)
    if n < 2 * min_per_team:
        return {'ok': False, 'reason': f'색을 읽을 수 있는 선수가 {n}명뿐입니다({2 * min_per_team}명 이상 필요).', 'groups': [], 'others': [], 'separation': None, 'weak': False}
    centres = _kmeans2(points)
    scales = np.array([SCALE_FLOOR, SCALE_FLOOR])
    outlier = np.zeros(n, bool)
    labels = np.zeros(n, int)
    for _ in range(4):
        distance = np.linalg.norm(points[:, None, :] - centres[None], axis=2)
        labels = distance.argmin(1)
        nearest = distance.min(1)
        scales = np.array([max(float(np.median(nearest[(labels == c) & ~outlier])) if ((labels == c) & ~outlier).any() else SCALE_FLOOR, SCALE_FLOOR) for c in (0, 1)])
        outlier = nearest / scales[labels] > OUTLIER_FACTOR
        centres = np.array([np.median(points[(labels == c) & ~outlier], axis=0) if ((labels == c) & ~outlier).any() else centres[c] for c in (0, 1)])
    groups = [{'centre': centres[c].tolist(), 'scale': float(scales[c]), 'members': [int(i) for i in np.flatnonzero((labels == c) & ~outlier)]} for c in (0, 1)]
    groups.sort(key=lambda g: -len(g['members']))
    others = _group_others(points, [int(i) for i in np.flatnonzero(outlier)])
    separation = float(np.linalg.norm(np.array(groups[0]['centre']) - np.array(groups[1]['centre'])) / (groups[0]['scale'] + groups[1]['scale']))
    result = {'ok': True, 'reason': '', 'groups': groups, 'others': others, 'separation': round(separation, 2), 'weak': False}
    if min(len(g['members']) for g in groups) < min_per_team:
        result.update(ok=False, reason=f'한쪽 색 무리가 {min_per_team}명 미만입니다.')
    elif separation < MIN_SEPARATION:
        result.update(weak=True, reason='두 팀의 옷 색이 서로 비슷합니다. 사진을 잘 보고 골라 주세요. 팀이 섞여 보일 수 있습니다.')
    return result


def make_profile(split, own_group, *, note='', source=None, now=None):
    """The profile of a match after the coach chose group `own_group` (0 or 1, an index into split['groups']) as the own team."""
    if not split.get('ok') and len(split.get('groups', [])) < 2:
        raise ValueError('Two colour groups are needed.')
    if own_group not in (0, 1):
        raise ValueError('own_group must be 0 or 1.')
    own, opponent = split['groups'][own_group], split['groups'][1 - own_group]
    return {'version': PROFILE_VERSION, 'created': now or time.strftime('%Y-%m-%dT%H:%M:%S'),
            'own': {'centre': [round(v, 3) for v in own['centre']], 'scale': round(own['scale'], 3), 'people': len(own['members'])},
            'opponent': {'centre': [round(v, 3) for v in opponent['centre']], 'scale': round(opponent['scale'], 3), 'people': len(opponent['members'])},
            'others': [{'centre': [round(v, 3) for v in g['centre']], 'people': len(g['members'])} for g in split.get('others', [])],
            'separation': split.get('separation'), 'note': note, 'source': source or {}}


def save_profile(path, profile):
    """Written to a temporary file first and renamed, so that a live run never reads a half-written profile."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=path.parent, suffix='.tmp')
    try:
        with os.fdopen(handle, 'w', encoding='utf-8') as out:
            json.dump(profile, out, ensure_ascii=False, indent=1)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def load_profile(path):
    """The stored profile, or None when the file is missing. A damaged or foreign file raises ValueError (a live run must not continue with an unknown profile)."""
    path = Path(path)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        for key in ('own', 'opponent'):
            if len(data[key]['centre']) != 3 or float(data[key]['scale']) <= 0:
                raise ValueError(key)
        if data.get('version') != PROFILE_VERSION:
            raise ValueError('version')
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise ValueError(f'팀 색 프로필 파일을 읽을 수 없습니다({path.name}): {error}') from error
    return data


class ProfileClassifier:
    """Labels a colour point 'own', 'opponent' or None from the stored profile."""

    def __init__(self, profile):
        self.centres = {k: np.array(profile[k]['centre'], np.float64) for k in ('own', 'opponent')}
        self.scales = {k: max(float(profile[k]['scale']), SCALE_FLOOR) for k in ('own', 'opponent')}
        self.others = [np.array(g['centre'], np.float64) for g in profile.get('others', [])]

    def distances(self, colour):
        point = np.asarray(colour, np.float64)
        return {k: float(np.linalg.norm(point - self.centres[k])) for k in self.centres}

    def classify(self, colour):
        """'own' / 'opponent' / None. None when the colour is far from both groups (referee, goalkeeper, a person of the stands) or about as near to one as to the other."""
        if colour is None:
            return None
        d = self.distances(colour)
        near, far = sorted(d, key=d.get)
        if d[near] / self.scales[near] > OUTLIER_FACTOR:
            return None
        if d[far] > 0 and d[near] / d[far] > CLASSIFY_RATIO:
            return None
        return near

    def classify_box(self, image, box):
        return self.classify(shirt_colour(image, box))


def profile_fit(profile, colours):
    """How well the stored colours still describe the people seen now (for the check of the second half and for the warning "team colours again"):
    {'own', 'opponent', 'unclear', 'people', 'ok', 'reason'}. Not ok when fewer than 4 people are labelled for a team or more than half of the people are unclear."""
    classifier = ProfileClassifier(profile)
    counts = {'own': 0, 'opponent': 0, 'unclear': 0}
    for colour in colours:
        if colour is None:
            continue
        counts[classifier.classify(colour) or 'unclear'] += 1
    people = sum(counts.values())
    ok, reason = True, ''
    if people == 0:
        ok, reason = False, '색을 읽을 수 있는 선수가 없습니다.'
    elif counts['own'] < MIN_PER_TEAM or counts['opponent'] < MIN_PER_TEAM:
        ok, reason = False, '한쪽 팀으로 나뉜 선수가 4명 미만입니다. 옷이 바뀌었거나 사진이 어두울 수 있습니다.'
    elif counts['unclear'] / people > 0.5:
        ok, reason = False, '색으로 나뉘지 않은 사람이 절반을 넘습니다.'
    return {**counts, 'people': people, 'ok': ok, 'reason': reason}


def colour_name(centre):
    """A plain Korean colour word for a group colour point [0.6 L, a, b], for the pictures and the confirmation line (rough: the coach sees the pictures as well)."""
    lightness, a, b = float(centre[0]) / LIGHT_WEIGHT, float(centre[1]), float(centre[2])
    chroma = (a * a + b * b) ** 0.5
    if lightness < 22:
        return '검은색'
    if chroma < 12:
        return '흰색' if lightness > 75 else ('회색' if lightness > 40 else '어두운 회색')
    import math
    hue = math.degrees(math.atan2(b, a)) % 360          # Lab hue angle: 0 red-magenta, 90 yellow, 180 green, 270 blue
    if lightness < 40:
        return '어두운 색' if chroma < 25 else '어두운 ' + _hue_word(hue)
    if 85 <= hue < 130 and lightness > 70 and chroma > 45:
        return '형광 노란색'
    return ('밝은 ' if lightness >= 60 else '') + _hue_word(hue)


def _hue_word(hue):
    for limit, word in ((30, '빨간색'), (70, '주황색'), (100, '노란색'), (130, '연두색'), (180, '초록색'), (240, '하늘색'), (300, '파란색'), (340, '보라색'), (361, '분홍색')):
        if hue < limit:
            return word
    return '빨간색'
