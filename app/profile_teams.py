"""Team letters for the offline analysis (tracking, reports) from the team colour profile of the match.

The own team keeps the letter 'B' (team_b) and the opponent the letter 'A' (team_a): all tracking files, labels and reports use these letters (app/team_style.py).
A profile therefore only decides which boxes get which letter; without a profile nothing in this module is used and the old colour rule or trained model stays.

Two sources of the box colour:
 * image path (scripts/track_review_clip.py): the box is read from the picture exactly as the coach's page does (shirt_colour, median Lab colour without grass).
 * cache path (scripts/track_from_cache.py): the cache has only the 12 x 16 mean colour of the shirt patch in the feature row ('blue', 'green', 'red'), so the colour is the mean of that patch.
   It is less exact (grass and lines are not left out); the difference is measured in wiki/team-select.md.

Combination with the trained team model (the model is more exact in the match it was trained on, 2.3 % wrong against 8.7 % of the colour profile, but fails in other clothes):
 mode 'profile'  profile only; unclear boxes stay unclear.
 mode 'fallback' the profile decides; only when it is unclear the model decides.
 mode 'model'    the model decides; only when it is unclear the profile decides.
"""
import numpy as np

from app.team_color_profile import LIGHT_WEIGHT, ProfileClassifier, shirt_colour
from app.team_role_features import FEATURE_NAMES

MODES = ('profile', 'fallback', 'model')
_BLUE, _GREEN, _RED = (FEATURE_NAMES.index(n) for n in ('blue', 'green', 'red'))


def letters_of(own_letter='B'):
    return {'own': own_letter, 'opponent': 'A' if own_letter == 'B' else 'B'}


def colour_from_features(features):
    """The colour point [0.6 * L, a, b] of a feature row from the mean colour of the shirt patch (cache path), or None for an all-zero row."""
    import cv2
    bgr = np.asarray([features[_BLUE], features[_GREEN], features[_RED]], np.float32)
    if not bgr.any():
        return None
    lab = cv2.cvtColor(np.clip(bgr * 255.0, 0, 255).astype(np.uint8)[None, None], cv2.COLOR_BGR2LAB)[0, 0].astype(np.float32)
    return np.array([LIGHT_WEIGHT * lab[0] * 100.0 / 255.0, lab[1] - 128.0, lab[2] - 128.0], np.float32)


class OfflineTeams:
    """Letter of a box from the profile ('B' own, 'A' opponent by default, None unclear)."""

    def __init__(self, profile, own_letter='B'):
        self.classifier = ProfileClassifier(profile)
        self.letters = letters_of(own_letter)

    def letter_of_colour(self, colour):
        side = self.classifier.classify(colour)
        return self.letters[side] if side else None

    def letter_of_box(self, image, box):
        return self.letter_of_colour(shirt_colour(image, box))

    def letter_of_features(self, features):
        return self.letter_of_colour(colour_from_features(features))


def model_letter(probabilities, classes, minimum_confidence=0.5, minimum_margin=0.1):
    """The team letter ('A' / 'B') of one row of class probabilities when the best class is a team and clearly ahead, else None (referee and spectator are not team letters here)."""
    p = np.asarray(probabilities, np.float32)
    order = np.argsort(p)[::-1]
    if p[order[0]] < minimum_confidence or p[order[0]] - p[order[1]] < minimum_margin:
        return None
    return {'team_a': 'A', 'team_b': 'B'}.get(classes[int(order[0])])


def combine(profile_letter, model_letter_, mode='profile'):
    """One team letter from the profile and the model. See the module text for the modes."""
    if mode == 'profile':
        return profile_letter
    if mode == 'fallback':
        return profile_letter or model_letter_
    if mode == 'model':
        return model_letter_ or profile_letter
    raise ValueError(f'unknown mode {mode}')


def profile_probabilities(teams, features, classes, probabilities, mode='profile'):
    """Class probabilities of one feature row after the profile has spoken, so that everything downstream that works on class probabilities (track_label, enforce_team_size) follows the profile.
    The model keeps the say about the role (referee, spectator): only the probability the row has for the two team classes is moved. A team letter chosen by the profile (or by the combination)
    gets all of it; with no letter it is split evenly between the two teams, so the track label stays unclear. The first version also lifted the team probability to 0.6, which turned
    spectators and referees into players (1268 against 2960 spectator rows on one minute of this match); it was removed."""
    p = np.array(probabilities, np.float32)
    a, b = classes.index('team_a'), classes.index('team_b')
    letter = combine(teams.letter_of_features(features), model_letter(probabilities, classes), mode)
    mass = float(p[a] + p[b])
    if letter is None:
        p[a] = p[b] = mass / 2
    else:
        p[a], p[b] = (mass, 0.0) if letter == 'A' else (0.0, mass)
    return p


def shirt_accepts(letters, label):
    """The followed player must look like his team: `letters` are the profile letters of the player's box on a few frames (None = unclear).
    True when no frame is decided or the frames that say `label` are not fewer than those that say the other team."""
    decided = [letter for letter in letters if letter in ('A', 'B')]
    if not decided:
        return True
    return sum(1 for letter in decided if letter == label) >= sum(1 for letter in decided if letter != label)


MIN_FIT_BOXES = 30          # boxes needed to judge whether the trained model fits this match
MIN_MODEL_COVERAGE = 0.9    # NOT used by the scripts: it separates well on hand-labelled player boxes but fails on raw detections (the model calls most large raw boxes spectators: 56 percent coverage on this match's own cache), see wiki/team-select.md. Share of the profile-decided boxes on which the model gives a clear team; in the first match 0.99 (291 boxes), in 7 repainted situations 0.46 to 0.77 (wiki/team-select.md)


def model_coverage(profile_letters, model_letters):
    """(boxes where the profile decided, share of those on which the model also gave a team letter). A model trained on other clothes mostly cannot tell the teams apart, so the share is low."""
    decided = [m for p, m in zip(profile_letters, model_letters) if p is not None]
    if not decided:
        return 0, 0.0
    return len(decided), sum(1 for m in decided if m is not None) / len(decided)


def choose_mode(profile_letters, model_letters):
    """'model' (the model first, the profile where it is unclear) when the model clearly knows these clothes, else 'fallback' (the profile first, the model only where it is unclear).
    With fewer than MIN_FIT_BOXES decided boxes there is no evidence for the model and 'fallback' is returned."""
    count, share = model_coverage(profile_letters, model_letters)
    return 'model' if count >= MIN_FIT_BOXES and share >= MIN_MODEL_COVERAGE else 'fallback'
