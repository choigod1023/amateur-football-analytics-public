"""Research measurement of the colour-profile team split (app/team_color_profile.py) against the human team labels of the review store (read only, CPU only).

python scripts/eval_team_profile.py <review store folder> <output json> [--model work/team-role-model-20261112b/model.pt]

Truth: the team_group the user set on player boxes (team_b = the own team of this match). Goalkeepers and referees are not counted as team boxes.
Tests:
 1. one_scene: a profile is built from the people of ONE labelled scene (about what the first seconds give), then every box of the OTHER scenes is classified.
 2. pooled: one profile from all scenes (upper bound of what the colour alone can do in this match).
 3. synthetic: the clothes of one team are repainted in another colour (blue, red, white, dark grey, or the own dark team put on bright orange vests) and tests 1 and 2 are repeated;
    the old rule (neon share) and the trained team model are scored on the same repainted boxes. This is the only way to test other clothes with the one match we have.
The human labels are never changed and no model is trained. Results are research measurements, not a service decision.
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.team_color_profile import MIN_HEIGHT_PX, ProfileClassifier, make_profile, shirt_colour, split_teams  # noqa: E402
from app.team_role_features import FEATURE_NAMES, box_features  # noqa: E402

PAINTS = {'파란 조끼': (200, 90, 20), '빨간 조끼': (30, 30, 210), '흰 조끼': (235, 235, 235), '짙은 회색': (60, 60, 60), '주황 조끼': (20, 120, 250)}   # BGR
NEON, DARK = FEATURE_NAMES.index('neon'), FEATURE_NAMES.index('dark')


def load(store):
    scenes = defaultdict(list)
    for path in sorted(Path(store).glob('*.json')):
        try:
            label = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        if not isinstance(label, dict) or 'bbox_image_norm' not in label or label.get('role') in ('duplicate', 'shadow', 'unknown', None):
            continue
        scenes[label['image']].append(label)
    return scenes


def box_px(label, shape):
    h, w = shape[:2]
    x1, y1, x2, y2 = label['bbox_image_norm']
    return [x1 * w, y1 * h, x2 * w, y2 * h]


def paint(image, box, bgr):
    """Repaint the torso of a box with a flat colour that keeps the light and shade of the original."""
    x1, y1, x2, y2 = [int(v) for v in box]
    h, w = y2 - y1, x2 - x1
    top, bottom, left, right = y1 + int(.1 * h), y1 + int(.68 * h), x1 + int(.1 * w), x2 - int(.1 * w)
    region = image[top:bottom, left:right].astype(np.float32)
    if region.size == 0:
        return
    grey = region.mean(2, keepdims=True)
    factor = grey / max(float(grey.mean()), 1.0)
    image[top:bottom, left:right] = np.clip(np.array(bgr, np.float32)[None, None] * factor, 0, 255).astype(np.uint8)


def truth_of(label):
    if label.get('role') == 'player' and label.get('team_group') == 'team_b':
        return 'own'
    if label.get('role') == 'player' and label.get('team_group') == 'team_a':
        return 'opponent'
    return None


def collect(scenes, store, repaint=None):
    """Per scene: list of dict(colour, truth, height_px, role, features). repaint: (team 'own'|'opponent', bgr) repaints the player boxes of that team in the scene copy."""
    out = {}
    for name, labels in scenes.items():
        image = cv2.imread(str(Path(store) / name))
        if image is None:
            continue
        rows = [(label, box_px(label, image.shape)) for label in labels]
        if repaint:
            for label, box in rows:
                if truth_of(label) == repaint[0]:
                    paint(image, box, repaint[1])
        items = []
        for label, box in rows:
            if label['role'] not in ('player', 'goalkeeper', 'referee', 'spectator'):
                continue
            h = box[3] - box[1]
            features = box_features(image, [box[0] / image.shape[1], box[1] / image.shape[0], box[2] / image.shape[1], box[3] / image.shape[0]])
            items.append({'colour': shirt_colour(image, box, MIN_HEIGHT_PX), 'colour_any': shirt_colour(image, box, 8), 'truth': truth_of(label), 'height': h, 'role': label['role'], 'features': features})
        out[name] = items
    return out


def profile_from(items, include_spectators=False):
    pool = [i for i in items if i['colour'] is not None and i['role'] in (('player', 'goalkeeper', 'referee') + (('spectator',) if include_spectators else ()))]
    split = split_teams([i['colour'] for i in pool])
    if len(split['groups']) < 2:
        return None, split
    votes = []
    for g in split['groups']:
        mine = sum(1 for m in g['members'] if pool[m]['truth'] == 'own')
        other = sum(1 for m in g['members'] if pool[m]['truth'] == 'opponent')
        votes.append(mine - other)
    own_group = 0 if votes[0] >= votes[1] else 1                      # the coach's click: the group that shows more of the own team
    return make_profile(split, own_group), split


def score(profile, items):
    """Counts over the team boxes (player boxes with a truth) by size class: correct, wrong (the other team), unclear."""
    classifier = ProfileClassifier(profile)
    result = {'big': [0, 0, 0], 'small': [0, 0, 0]}
    for i in items:
        if i['truth'] is None or i['colour_any'] is None:
            if i['truth'] is not None:
                result['big' if i['height'] >= MIN_HEIGHT_PX else 'small'][2] += 1
            continue
        got = classifier.classify(i['colour_any'])
        slot = result['big' if i['height'] >= MIN_HEIGHT_PX else 'small']
        slot[2 if got is None else (0 if got == i['truth'] else 1)] += 1
    return result


def add(total, part):
    for k in part:
        for j in range(3):
            total[k][j] += part[k][j]


def old_rule(items):
    """The live rule that was fixed to this match: neon share >= 0.10 is team A (opponent), dark share >= 0.30 is team B (own)."""
    result = {'big': [0, 0, 0], 'small': [0, 0, 0]}
    for i in items:
        if i['truth'] is None:
            continue
        f = i['features']
        got = 'opponent' if f[NEON] >= 0.10 else ('own' if f[DARK] >= 0.30 else None)
        slot = result['big' if i['height'] >= MIN_HEIGHT_PX else 'small']
        slot[2 if got is None else (0 if got == i['truth'] else 1)] += 1
    return result


def model_rule(model, items):
    from app.team_role_infer import LETTER, predict
    result = {'big': [0, 0, 0], 'small': [0, 0, 0]}
    teams = [i for i in items if i['truth'] is not None]
    if not teams:
        return result
    probabilities = predict(model, np.array([i['features'] for i in teams]))
    for i, p in zip(teams, probabilities):
        letter = LETTER.get(model['classes'][int(np.argmax(p))])
        got = {'B': 'own', 'A': 'opponent'}.get(letter)
        slot = result['big' if i['height'] >= MIN_HEIGHT_PX else 'small']
        slot[2 if got is None else (0 if got == i['truth'] else 1)] += 1
    return result


def evaluate(scenes, store, repaint=None, model=None):
    data = collect(scenes, store, repaint)
    names = sorted(data)
    one, failed, separations = {'big': [0, 0, 0], 'small': [0, 0, 0]}, 0, []
    for name in names:
        profile, split = profile_from(data[name])
        if profile is None or not split['ok']:
            failed += 1
        if profile is None:
            continue
        separations.append(split['separation'])
        add(one, score(profile, [i for other in names if other != name for i in data[other]]))
    everything = [i for n in names for i in data[n]]
    profile, split = profile_from(everything)
    pooled = score(profile, everything) if profile else None
    out = {'scenes': len(names), 'scene_profiles_not_ok': failed, 'separation_median': float(np.median(separations)) if separations else None,
           'one_scene_profile_vs_other_scenes': one, 'pooled_profile': pooled, 'pooled_separation': split.get('separation'),
           'old_colour_rule': old_rule(everything)}
    if model is not None:
        out['trained_model_on_this_match_model'] = model_rule(model, everything)
    return out


def main():
    args = sys.argv[1:]
    model_path = None
    if '--model' in args:
        model_path = args[args.index('--model') + 1]
        del args[args.index('--model'):args.index('--model') + 2]
    if len(args) != 2:
        raise SystemExit(__doc__)
    store, out = args
    scenes = load(store)
    from app.team_role_infer import load_model
    model = load_model(model_path) if model_path else None
    result = {'store_scenes': len(scenes), 'boxes_with_team_truth': sum(1 for s in scenes.values() for l in s if truth_of(l)), 'real_colours': evaluate(scenes, store, None, None), 'synthetic': {}}
    for name, bgr in PAINTS.items():
        result['synthetic'][f'상대 팀(밝은 옷)을 {name}로 바꿈'] = evaluate(scenes, store, ('opponent', bgr), model)
    for name in ('주황 조끼', '흰 조끼'):
        result['synthetic'][f'우리 팀(어두운 옷)이 {name}를 입음'] = evaluate(scenes, store, ('own', PAINTS[name]), model)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
