"""Cut context crops around the auto-labeller candidates that lie in the range the verifiers were tested on (research only, read only).

python scripts/dump_candidate_crops.py <video> <output folder> <candidates folder> [<candidates folder> ...] [--all]

Candidates come from candidates_*.jsonl of work/auto-labels-bulk-20261116 and work/auto-labels-round2-20261117. Only in-scope candidates are cut (found by one detector, score 0.35 to 0.45),
because the verifiers were measured only on boxes with scores 0.36 to 0.44 (wiki/verifier-models.md); --all cuts the others too, whose results stay unvalidated.
manifest.json: n, source folder, frame, time, camera, box, score, found_by, in_scope, box_ctx (the same fields scripts/score_verifiers.py reads; no human label exists for these boxes).
"""
import glob
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dump_verifier_crops import cut_crops  # noqa: E402


def main():
    args = [a for a in sys.argv[1:] if a != '--all']
    everything = '--all' in sys.argv[1:]
    if len(args) < 3:
        raise SystemExit(__doc__)
    import cv2
    video, out, folders = args[0], Path(args[1]), args[2:]
    out.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(video)
    rows = []
    for folder in folders:
        for path in sorted(glob.glob(str(Path(folder) / 'candidates_*.jsonl'))):
            for line in Path(path).read_text(encoding='utf-8').splitlines():
                if line.strip():
                    r = json.loads(line)
                    if r['in_scope'] or everything:
                        rows.append(dict(r, source=Path(folder).name))
    rows.sort(key=lambda r: (r['time'], r['source']))
    manifest, last_time, image = [], None, None
    for r in rows:
        if r['time'] != last_time:
            cap.set(cv2.CAP_PROP_POS_MSEC, r['time'] * 1000)
            ok, image = cap.read()
            last_time = r['time']
            image = image if ok else None
        if image is None:
            continue
        ctx, tight, box_ctx, origin = cut_crops(image, r['box'])
        n = len(manifest)
        cv2.imwrite(str(out / f'{n:03d}_ctx.png'), ctx)
        cv2.imwrite(str(out / f'{n:03d}_tight.png'), tight)
        manifest.append({'n': n, 'source': r['source'], 'frame': r['frame'], 'time': r['time'], 'camera': r['camera'], 'box': r['box'], 'score': r['score'], 'found_by': r['found_by'],
                         'in_scope': r['in_scope'], 'old_decision': r['decision'], 'box_ctx': box_ctx})
    (out / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    print(len(manifest), 'crops')


if __name__ == '__main__':
    main()
