"""Inspect existing research model predictions; never approve calibration.

Reads the local, access-controlled AI Hub data and writes aggregate numbers
only. An edge-proximity score is exploratory, not a calibrated confidence.
"""
import ast, json, pathlib, random, re, runpy, sys, zipfile
import cv2
import numpy as np
import torch
from torch import nn
from torchvision.models import resnet18

repo = pathlib.Path(__file__).resolve().parents[1]
root = repo.parents[1]
sys.path.insert(0, str(repo))
from scripts.calibrate_penalty_lines import _intersection

# Reuse the original dataset parser and preprocessor without running training.
tree = ast.parse((repo / 'scripts/experimental_partial_field.py').read_text(encoding='utf8'))
functions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in ('target', 'image', 'labels_from')]
exec(compile(ast.Module(body=functions, type_ignores=[]), '<dataset helpers>', 'exec'))

trainpaths = {int(re.search(r'soccer_(\d+)\.jpg$', p.name)[1]): p for p in (root/'work/aihub-training-prefix/field-images').glob('*.jpg') if re.search(r'soccer_(\d+)\.jpg$', p.name) and int(re.search(r'soccer_(\d+)\.jpg$', p.name)[1]) <= 9000}
train = [r for r in labels_from(root/'work/aihub-training-prefix/training-labels.zip', trainpaths) if r[2].startswith('q6c_Hxjgn4B_')]
random.seed(17); random.shuffle(train)
with zipfile.ZipFile(root/'work/aihub-official/validation-labels.zip') as z:
    ids = {int(re.search(r'soccer_(\d+)\.json$', n)[1]) for n in z.namelist() if re.search(r'soccer_(\d+)\.json$', n)}
valid = [r for r in labels_from(root/'work/aihub-official/validation-labels.zip', ids) if r[2].startswith('Vss97zvkNj_') and r[1][2].sum() == 4]
random.shuffle(valid); valid = valid[:200]
parts = runpy.run_path(str(root/'work/aihub-official/list_validation_video.py'))
model = resnet18(weights=None); model.fc = nn.Linear(model.fc.in_features, 10)
weights = root/'work/partial-field-runs/f97a51bbba1543b28757cb0d7c8e582d/experimental.pt'
model.load_state_dict(torch.load(weights, map_location='cpu', weights_only=True)); model.eval()
device = 'cuda' if torch.cuda.is_available() else 'cpu'; model.to(device)
rows = []
with parts['Parts']() as source, zipfile.ZipFile(source) as z, torch.no_grad():
    names = {pathlib.PurePosixPath(n).stem:n for n in z.namelist() if n.lower().endswith('.jpg')}
    for num, (side, points, mask), _ in valid:
        name = names.get(f'soccer_{num}')
        if not name: continue
        data = z.read(name); x = image(data)
        if x is None: continue
        rgb = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        rgb = cv2.resize(rgb, (320, 192))
        raw = model(torch.tensor(x[None]).to(device)).cpu()
        pred = torch.sigmoid(raw[0,:8]).numpy().reshape(4,2) * [1920,1080]
        errors = np.linalg.norm(pred - points, axis=1)
        # Distance in 320x192 pixels to bright, weakly saturated pixels. Players,
        # highlights and advertisements can also satisfy this condition.
        hsv = cv2.cvtColor(rgb, cv2.COLOR_BGR2HSV)
        white = ((hsv[:,:,1] < 85) & (hsv[:,:,2] > 180)).astype(np.uint8)
        dist = cv2.distanceTransform(1-white, cv2.DIST_L2, 3)
        xy = np.rint(pred / [1920,1080] * [319,191]).astype(int)
        proximity = np.mean([dist[y,x] for x,y in xy])
        corners = cv2.goodFeaturesToTrack(white * 255, maxCorners=800, qualityLevel=.02, minDistance=2)
        candidates = np.empty((0,2)) if corners is None else corners.reshape(-1,2)
        refinements = {}
        for radius in (4, 8, 12, 20):
            adjusted = pred.copy()
            for index, (x, y) in enumerate(pred / [1920,1080] * [320,192]):
                if len(candidates):
                    distances = np.linalg.norm(candidates - [x,y], axis=1)
                    nearest = int(distances.argmin())
                    if distances[nearest] <= radius:
                        adjusted[index] = candidates[nearest] / [320,192] * [1920,1080]
            refinements[radius] = np.linalg.norm(adjusted-points,axis=1).mean()
        rows.append((num, errors, float(proximity), bool(np.any((points < 0) | (points > [1920,1080]))), refinements))
rows.sort(key=lambda row: row[0])
error = np.stack([row[1] for row in rows]); mean = error.mean(axis=1)
score = np.array([row[2] for row in rows]); split = len(rows)//2
threshold = float(np.median(score[:split])); selected = score[split:] <= threshold
def summary(a): return {'count':len(a), 'median_px':float(np.median(a)), 'p90_px':float(np.percentile(a, 90)), 'over_100px':int(np.sum(a > 100))} if len(a) else {'count':0}
result = {'development_frames':len(rows), 'corner_median_px':np.median(error,axis=0).tolist(), 'corner_p90_px':np.percentile(error,90,axis=0).tolist(), 'targets_outside_frame':sum(row[3] for row in rows), 'all':summary(mean), 'threshold_fit_first_half':threshold, 'second_half_all':summary(mean[split:]), 'second_half_selected':summary(mean[split:][selected]), 'second_half_rejected':summary(mean[split:][~selected]), 'limitation':'Same repeatedly-used Vss match; ordered frame halves are correlated; selected is not verified calibration. Score uses bright pixels, not labeled field lines.'}
refined = {radius:np.array([row[4][radius] for row in rows]) for radius in (4,8,12,20)}
best = min(refined, key=lambda radius: np.mean(refined[radius][:split]))
result['snap_fit_first_half'] = {'radius_px_at_320x192':best, 'baseline':summary(mean[:split]), 'adjusted':summary(refined[best][:split])}
result['snap_evaluation_second_half'] = {'baseline':summary(mean[split:]), 'adjusted':summary(refined[best][split:]), 'improved_frames':int(np.sum(refined[best][split:] < mean[split:])), 'worsened_frames':int(np.sum(refined[best][split:] > mean[split:]))}
print(json.dumps(result, ensure_ascii=False, indent=2))
