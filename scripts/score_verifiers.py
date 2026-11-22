"""Score the crops of dump_verifier_crops.py with outside verifier models (research only; run with the separate verifier environment, never the production one).

<verifier venv>/Scripts/python.exe scripts/score_verifiers.py <crops folder> <output json> [--models gdino,owl,siglip] [--device cpu|cuda]

Models (all downloaded from Hugging Face on first use; licences are noted in wiki/verifier-models.md):
  gdino   IDEA-Research/grounding-dino-tiny, text 'person.', the score is the best detection that overlaps the judged box (IoU >= 0.3) in the context crop, 0 when none.
  owl     google/owlv2-base-patch16-ensemble, query 'a person', same overlap rule.
  siglip  google/siglip-base-patch16-224 on the tight crop: logit('a photo of a person') minus the best logit of other things seen on a pitch (grass, pole, sign, ball, spectator bag).
The human label is not read here; the output is {n: {model: score}} and is joined with the labels afterwards.
"""
import argparse
import json
from pathlib import Path

import torch
from PIL import Image

LABELS = ['a photo of a person', 'a photo of grass', 'a photo of a goalpost or a pole', 'a photo of a sign or a fence', 'a photo of a ball', 'a photo of a bag or a bottle on the ground']


def iou(a, b):
    w, h = min(a[2], b[2]) - max(a[0], b[0]), min(a[3], b[3]) - max(a[1], b[1])
    if w <= 0 or h <= 0:
        return 0.0
    i = w * h
    return i / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - i)


def run_detector(name, repo, text, manifest, folder, device, threshold, partial=None):
    from transformers import AutoProcessor, AutoModelForZeroShotObjectDetection
    processor = AutoProcessor.from_pretrained(repo)
    model = AutoModelForZeroShotObjectDetection.from_pretrained(repo).to(device).eval()
    out = {int(k): v for k, v in json.loads(partial.read_text(encoding='utf-8')).items()} if partial is not None and partial.exists() else {}      # resume after a crash
    for count, m in enumerate(manifest):
        if m['n'] in out:
            continue
        image = Image.open(folder / f'{m["n"]:03d}_ctx.png').convert('RGB')
        inputs = processor(images=image, text=text, return_tensors='pt').to(device)
        with torch.no_grad():
            result = model(**inputs)
        size = torch.tensor([image.size[::-1]], device=device)
        if name == 'gdino':
            found = processor.post_process_grounded_object_detection(result, inputs.input_ids, threshold=threshold, text_threshold=threshold, target_sizes=size)[0]
        else:
            found = processor.post_process_grounded_object_detection(result, threshold=threshold, target_sizes=size)[0]
        best = 0.0
        for box, score in zip(found['boxes'].tolist(), found['scores'].tolist()):
            if iou(box, m['box_ctx']) >= 0.3:
                best = max(best, float(score))
        out[m['n']] = best
        if partial is not None and count % 10 == 9:
            partial.write_text(json.dumps(out), encoding='utf-8')
    return out


def run_siglip(manifest, folder, device):
    from transformers import AutoProcessor, AutoModel
    repo = 'google/siglip-base-patch16-224'
    processor = AutoProcessor.from_pretrained(repo)
    model = AutoModel.from_pretrained(repo).to(device).eval()
    out = {}
    for m in manifest:
        image = Image.open(folder / f'{m["n"]:03d}_tight.png').convert('RGB')
        inputs = processor(text=LABELS, images=image, padding='max_length', return_tensors='pt').to(device)
        with torch.no_grad():
            logits = model(**inputs).logits_per_image[0].tolist()
        out[m['n']] = logits[0] - max(logits[1:])
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('folder')
    parser.add_argument('output')
    parser.add_argument('--models', default='gdino,owl,siglip')
    parser.add_argument('--device', default='cpu')
    args = parser.parse_args()
    folder = Path(args.folder)
    manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
    manifest = [{k: m[k] for k in ('n', 'box_ctx')} for m in manifest]          # the labels are not passed to the models
    scores = {m['n']: {} for m in manifest}
    if Path(args.output).exists():                     # keep the scores of models that were run before
        for k, v in json.loads(Path(args.output).read_text(encoding='utf-8')).items():
            scores[int(k)] = v
    for name in args.models.split(','):
        if name == 'gdino':
            result = run_detector('gdino', 'IDEA-Research/grounding-dino-tiny', 'person.', manifest, folder, args.device, 0.05, Path(args.output + '.gdino.partial'))
        elif name == 'owl':
            result = run_detector('owl', 'google/owlv2-base-patch16-ensemble', [['a person']], manifest, folder, args.device, 0.01, Path(args.output + '.owl.partial'))
        elif name == 'siglip':
            result = run_siglip(manifest, folder, args.device)
        else:
            raise SystemExit('unknown model ' + name)
        for n, s in result.items():
            scores[n][name] = s
        print(name, 'done', flush=True)
        Path(args.output).write_text(json.dumps(scores), encoding='utf-8')


if __name__ == '__main__':
    main()
