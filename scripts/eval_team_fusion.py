"""Research measurement (CPU only, read only): the offline team letters of the colour profile and their combination with the trained team model, against the human labels of the review store.

python scripts/eval_team_fusion.py <review store folder> <output json> [--model work/team-role-model-20261112b/model.pt]

Truth: the team_group the user set on player boxes (team_b = own team of this match, goalkeepers and referees are not counted). Same boxes and repainting as scripts/eval_team_profile.py.
Rows per situation (real clothes of this match, and clothes of one team repainted in another colour, which stands for another match):
  profile_picture   the profile decides, colour read from the picture (track_review_clip path)
  profile_cache     the profile decides, colour = mean colour of the 12 x 16 patch kept in the detection cache (track_from_cache path)
  model             trained team model alone (its own best team class, clearly ahead)
  fallback          profile first, the model only where the profile is unclear
  model_first       model first, the profile only where the model is unclear
Every cell is [correct, wrong (other team), unclear] over the team boxes at least 30 px high. Profiles: 'pooled' = one profile from all scenes, 'one_scene' = a profile from one scene applied to all other scenes.
The repainting is one flat colour per team on one match: an easier case than real vests. These are research numbers, not a service decision.
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from app.profile_teams import OfflineTeams, choose_mode, colour_from_features, combine, model_coverage, model_letter  # noqa: E402
from app.team_color_profile import MIN_HEIGHT_PX  # noqa: E402
from eval_team_profile import PAINTS, collect, load, profile_from  # noqa: E402

ROWS = ('profile_picture', 'profile_cache', 'model', 'fallback', 'model_first', 'auto')
TRUTH_LETTER = {'own': 'B', 'opponent': 'A'}


def prepare(items, model):
    """Add the model letter to every team box (>= 30 px) of a scene's items."""
    from app.team_role_infer import predict
    boxes = [i for i in items if i['truth'] is not None and i['height'] >= MIN_HEIGHT_PX]
    if boxes and model is not None:
        probabilities = predict(model, np.array([i['features'] for i in boxes]))
        for i, p in zip(boxes, probabilities):
            i['model_letter'] = model_letter(p, model['classes'])
    for i in boxes:
        i.setdefault('model_letter', None)
    return boxes


def tally(profile, boxes, cells):
    teams = OfflineTeams(profile)
    picture = [teams.letter_of_colour(i['colour_any']) for i in boxes]
    cells['_coverage'] = model_coverage(picture, [i['model_letter'] for i in boxes])
    cells['_mode'] = choose_mode(picture, [i['model_letter'] for i in boxes])      # judged on the boxes of the whole situation, as the first seconds of a match would be
    for i in boxes:
        truth = TRUTH_LETTER[i['truth']]
        picture = teams.letter_of_colour(i['colour_any'])
        cache = teams.letter_of_colour(colour_from_features(i['features']))
        answers = {'profile_picture': picture, 'profile_cache': cache, 'model': i['model_letter'],
                   'fallback': combine(picture, i['model_letter'], 'fallback'), 'model_first': combine(picture, i['model_letter'], 'model')}
        answers['auto'] = answers['model_first'] if cells['_mode'] == 'model' else answers['fallback']
        for row, got in answers.items():
            cells[row][2 if got is None else (0 if got == truth else 1)] += 1


def evaluate(scenes, store, repaint, model):
    data = collect(scenes, store, repaint)
    names = sorted(data)
    prepared = {n: prepare(data[n], model) for n in names}
    everything = [i for n in names for i in data[n]]
    out = {}
    pooled_profile, split = profile_from(everything)
    pooled = {r: [0, 0, 0] for r in ROWS}
    if pooled_profile:
        tally(pooled_profile, [i for n in names for i in prepared[n]], pooled)
    one = {r: [0, 0, 0] for r in ROWS}
    for name in names:
        profile, _split = profile_from(data[name])
        if profile is None:
            continue
        tally(profile, [i for other in names if other != name for i in prepared[other]], one)
    out['pooled'] = pooled
    out['one_scene'] = one
    out['team_boxes'] = sum(len(prepared[n]) for n in names)
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
    result = {'scenes': len(scenes), 'situations': {}}
    result['situations']['이 경기 실제 옷'] = evaluate(scenes, store, None, model)
    for name, bgr in PAINTS.items():
        result['situations'][f'상대 팀이 {name}'] = evaluate(scenes, store, ('opponent', bgr), model)
    for name in ('주황 조끼', '흰 조끼'):
        result['situations'][f'우리 팀이 {name}'] = evaluate(scenes, store, ('own', PAINTS[name]), model)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding='utf-8')
    for situation, data in result['situations'].items():
        print(f"== {situation} (team boxes {data['team_boxes']})")
        for kind in ('pooled', 'one_scene'):
            print('  ', kind, {r: data[kind][r] for r in ROWS})


if __name__ == '__main__':
    main()
