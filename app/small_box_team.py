"""Team reading of small boxes (20 to 29 px high) by the share of bib-coloured pixels, not by the mean colour (live option --small-box-team, off by default).
With all_sizes (--small-box-team-all) the same rule reads every box of 20 px and more, also those of 30 px and more (instead of the mean colour).

Why: boxes under MIN_HEIGHT_PX (30 px) are not read at all, so about half of the tracked boxes of the 11-20 match get no team and the own team has
6 to 7 people on average. Reading them with the mean colour (ProfileClassifier) lets the referee's black coat and the grey keeper in as the own team:
in the shade the mean of a green bib and of a black coat are almost the same colour point (work/model-improve-1123/colour-open/results.md).
The pixels are different: a bib has many light pixels of the bib hue, a dark coat has few (work/model-improve-1123/small-team/results.md).

Rule for one small box (only the team profile the coach chose on /team-select is used, nothing fixed per match):
- torso patch as shirt_colour() (height 0.15..0.6, sides 0.2); grass pixels removed by the same fixed HSV rule
- a pixel is 'own-like' when its hue (atan2(b, a)) is within HUE_BAND_DEG of the own centre's hue, its chroma at least CHROMA_SHARE of the own
  centre's chroma, and its weighted lightness [0.6 L] at least the own centre's minus one own spread (scale); 'opponent-like' the same with the
  opponent centre. share = own-like pixels / all patch pixels (and the same for the opponent).
- score = own share - opponent share. The mean colour says 'opponent' -> opponent. Else score >= threshold -> own; score <= -threshold -> opponent;
  else unclear (None).
"""
import numpy as np

from app.team_color_profile import LIGHT_WEIGHT, MIN_HEIGHT_PX, SCALE_FLOOR, ProfileClassifier, shirt_colour

SMALL_MIN_HEIGHT_PX = 20     # under 20 px the torso patch has under about 40 pixels; today's experiments read from 20 px (colour-minheight)
HUE_BAND_DEG = 25.0          # a pixel within this many degrees of the team hue counts (both 11-20 bib hues are about 100 degrees apart)
CHROMA_SHARE = 0.5           # and at least half as colourful as the team centre (grey and black pixels are not bib pixels)
MIN_HUE_GAP_DEG = 2 * HUE_BAND_DEG   # two hue bands of +-HUE_BAND_DEG do not overlap from this gap on (not chosen from data)
# A team centre is 'chromatic' from this chroma (hypot(a, b), the scale of CHROMA_SHARE). 17.97 = sqrt(12.04 * 26.81): the geometric mean of the
# 11-18 own centre (black shirts, chroma 12.04: the reader read 1 of 21 of them) and the lower of the two 11-20 centres (green and red bib, 29.58 and 26.81).
# LIMIT: placed from three profiles (six colours) only; a kit with a chroma between about 12 and 27 is decided by this one number.
MIN_CENTRE_CHROMA = 17.97


def hue_chroma(centre):
    """(hue in degrees 0..360, chroma) of a colour point [0.6 L, a, b]."""
    c = [float(v) for v in centre]
    if len(c) != 3:
        raise ValueError('colour centre needs 3 values')
    return float(np.degrees(np.arctan2(c[2], c[1])) % 360.0), float(np.hypot(c[1], c[2]))


def reader_decision(profile):
    """(on, message): whether the bib-pixel reader can tell the two teams of this profile apart, and the log line.
    OFF when the two hue bands overlap (gap < MIN_HUE_GAP_DEG) or a team colour is achromatic (chroma < MIN_CENTRE_CHROMA); then the caller
    must use the mean-colour reader and no vote switch (the output of a run without --small-box-team). Raises ValueError when the profile lacks its centres."""
    try:
        own_hue, own_chroma = hue_chroma(profile['own']['centre'])
        opp_hue, opp_chroma = hue_chroma(profile['opponent']['centre'])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f'team profile has no usable own/opponent centre: {error}') from error
    gap = abs((own_hue - opp_hue + 180.0) % 360.0 - 180.0)
    fallback = ' (falling back to mean-colour reader, vote switch disabled)'
    if gap < MIN_HUE_GAP_DEG:
        return False, f'Small-box team reader OFF: hue gap {gap:.1f} deg < {MIN_HUE_GAP_DEG:.0f}{fallback}'
    low = [(name, chroma) for name, chroma in (('own', own_chroma), ('opponent', opp_chroma)) if chroma < MIN_CENTRE_CHROMA]
    if low:
        return False, 'Small-box team reader OFF: ' + ', '.join(f'{name} colour chroma {chroma:.1f}' for name, chroma in low) + f' < {MIN_CENTRE_CHROMA} (achromatic){fallback}'
    return True, f'Small-box team reader ON: hue gap {gap:.1f} deg, chromas {own_chroma:.1f}/{opp_chroma:.1f}'


def _pixels(image, box):
    """[0.6 L, a, b] of the torso patch pixels and the grass mask (same patch and grass rule as shirt_colour), or (None, None)."""
    import cv2
    x1, y1, x2, y2 = [float(v) for v in box[:4]]
    h, w = y2 - y1, x2 - x1
    if w < 4:
        return None, None
    top, bottom = int(y1 + .15 * h), int(y1 + .6 * h) + 1
    left, right = int(x1 + .2 * w), int(x2 - .2 * w) + 1
    patch = image[max(0, top):max(0, bottom), max(0, left):max(0, right)]
    if patch.size == 0 or patch.shape[0] < 3 or patch.shape[1] < 2:
        return None, None
    hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV).reshape(-1, 3)
    grass = (hsv[:, 0] >= 45) & (hsv[:, 0] <= 85) & (hsv[:, 1] > 70) & (hsv[:, 2] > 40)
    lab = cv2.cvtColor(patch, cv2.COLOR_BGR2LAB).reshape(-1, 3).astype(np.float32)
    points = np.stack([LIGHT_WEIGHT * lab[:, 0] * 100.0 / 255.0, lab[:, 1] - 128.0, lab[:, 2] - 128.0], 1)
    return points, grass


class SmallBoxTeam:
    """Reads 'own' / 'opponent' / None for boxes SMALL_MIN_HEIGHT_PX <= height < MIN_HEIGHT_PX (all_sizes: height >= SMALL_MIN_HEIGHT_PX) from the stored team profile."""

    def __init__(self, profile, threshold, all_sizes=False):
        if threshold <= 0:
            raise ValueError('threshold must be > 0')
        self.threshold = float(threshold)
        self.all_sizes = bool(all_sizes)
        self.mean = ProfileClassifier(profile)
        self.bands = {}
        for key in ('own', 'opponent'):
            c = np.array(profile[key]['centre'], np.float64)
            self.bands[key] = (float(np.degrees(np.arctan2(c[2], c[1]))), float(np.hypot(c[1], c[2])) * CHROMA_SHARE,
                               float(c[0] - max(float(profile[key]['scale']), SCALE_FLOOR)))

    @staticmethod
    def in_small_range(box):
        h = float(box[3]) - float(box[1])
        return SMALL_MIN_HEIGHT_PX <= h < MIN_HEIGHT_PX

    def applies(self, box):
        h = float(box[3]) - float(box[1])
        return h >= SMALL_MIN_HEIGHT_PX if self.all_sizes else h < MIN_HEIGHT_PX and h >= SMALL_MIN_HEIGHT_PX

    def shares(self, points, grass):
        hue = np.degrees(np.arctan2(points[:, 2], points[:, 1]))
        chroma = np.hypot(points[:, 1], points[:, 2])
        out = {}
        for key, (h0, cmin, lmin) in self.bands.items():
            near = np.abs((hue - h0 + 180.0) % 360.0 - 180.0) <= HUE_BAND_DEG
            out[key] = float(np.mean(near & (chroma >= cmin) & (points[:, 0] >= lmin) & ~grass))
        return out

    def read(self, image, box):
        """(side, score): side 'own' / 'opponent' / None; score = own share - opponent share (None when the patch is empty)."""
        points, grass = _pixels(image, box)
        if points is None:
            return None, None
        s = self.shares(points, grass)
        score = s['own'] - s['opponent']
        if self.mean.classify(shirt_colour(image, box, min_height=0)) == 'opponent':
            return 'opponent', score
        if score >= self.threshold:
            return 'own', score
        if score <= -self.threshold:
            return 'opponent', score
        return None, score

    def classify_box(self, image, box):
        return self.read(image, box)[0]
