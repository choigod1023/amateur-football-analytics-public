"""Summarise a hard-frame replay and build the sheets the user judges (research; wiki/hard-frames.md).

python scripts/hard_frames_review_list.py <replay folder holding cam*_<start> pieces> <out folder> [--max-sheets 40] [--seed 5]

Reads every piece written by scripts/hard_frames_replay.py. Prints, per detector: analysed frames, frames flagged per rule (before the budget), saved frames, and how the frames that
the user confirmed boxes on (the 116 boxes) fall in the replayed stretches. Then it writes one sheet per sampled saved frame into <out folder>:
the frame with the boxes of the detector (thin green) and the boxes the other detector finds but this one lacks (red, numbered), and a zoom strip of the red ones.
The judgement is a number per sheet, written by the user ("which red numbers hold a person"); the user's answers never go into the review store from here.
The red boxes are model proposals, not human labels. Nothing is written into the review store.
"""
import html
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
import cv2  # noqa: E402
from app.hard_frames import _iou  # noqa: E402


def load(replay):
    pieces = sorted(p for p in Path(replay).iterdir() if (p / 'done.flag').exists())
    data = {}
    for p in pieces:
        for log in p.glob('frames_*.jsonl'):
            name = log.stem[len('frames_'):]
            rows = [json.loads(x) for x in log.read_text(encoding='utf-8').splitlines() if x.strip()]
            index = p / name / 'hard_frames.jsonl'
            saved = {round(json.loads(x)['video_time'], 2): json.loads(x) for x in index.read_text(encoding='utf-8').splitlines() if x.strip()} if index.exists() else {}
            data.setdefault(name, []).append({'piece': p, 'rows': rows, 'saved': saved})
    return pieces, data


def sheet(image, boxes, candidates):
    h, w = image.shape[:2]
    canvas = image.copy()
    for b in boxes:
        cv2.rectangle(canvas, (int(b[0]), int(b[1])), (int(b[2]), int(b[3])), (60, 200, 60), 1)
    for number, c in enumerate(candidates, start=1):
        cv2.rectangle(canvas, (int(c[0]), int(c[1])), (int(c[2]), int(c[3])), (40, 40, 255), 2)
        cv2.putText(canvas, str(number), (int(c[0]), max(14, int(c[1]) - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (40, 40, 255), 2)
    scale = 1600 / w
    canvas = cv2.resize(canvas, (1600, int(h * scale)))
    strip = []
    for number, c in enumerate(candidates[:6], start=1):
        pad_x, pad_y = 30, 30
        x0, y0, x1, y1 = max(0, int(c[0]) - pad_x), max(0, int(c[1]) - pad_y), min(w, int(c[2]) + pad_x), min(h, int(c[3]) + pad_y)
        crop = image[y0:y1, x0:x1]
        if crop.size == 0:
            continue
        crop = cv2.resize(crop, (200, 280))
        cv2.putText(crop, str(number), (6, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (40, 40, 255), 2)
        strip.append(crop)
    if strip:
        row = cv2.hconcat(strip)
        pad = max(0, 1600 - row.shape[1])
        row = cv2.copyMakeBorder(row, 0, 0, 0, pad, cv2.BORDER_CONSTANT, value=(30, 30, 30))
        canvas = cv2.vconcat([canvas, row[:, :1600]])
    return canvas


def main():
    args = sys.argv[1:]
    opts = {'--max-sheets': 40, '--seed': 5}
    for key in list(opts):
        if key in args:
            i = args.index(key)
            opts[key] = int(args[i + 1])
            del args[i:i + 2]
    if len(args) != 2:
        raise SystemExit(__doc__)
    replay, out = Path(args[0]), Path(args[1])
    pieces, data = load(replay)
    print(f'{len(pieces)} finished pieces')
    summary, pool = {}, []
    for name, parts in data.items():
        rows = [r for part in parts for r in part['rows']]
        flagged = {}
        for r in rows:
            for reason in r['reasons']:
                flagged[reason] = flagged.get(reason, 0) + 1
        any_flag = sum(1 for r in rows if r['reasons'])
        saved = sum(len(part['saved']) for part in parts)
        summary[name] = {'frames': len(rows), 'flagged_by_rule': flagged, 'flagged_any': any_flag, 'saved': saved,
                         'frames_lacking_ge1': sum(1 for r in rows if r['lacking_vs_other'] >= 1), 'frames_lacking_ge2': sum(1 for r in rows if r['lacking_vs_other'] >= 2)}
        print(name, json.dumps(summary[name], ensure_ascii=False))
        for part in parts:
            by_time = {round(r['t'], 2): r for r in part['rows']}
            for t, row in part['saved'].items():
                log = by_time.get(t)
                other = (log or {}).get('other_boxes') or []
                candidates = [o for o in other if o[4] >= 0.35 and all(_iou(o, b) < 0.3 for b in row['boxes'])]
                pool.append({'detector': name, 'piece': part['piece'], 'row': row, 'candidates': candidates})
    random.Random(opts['--seed']).shuffle(pool)
    out.mkdir(parents=True, exist_ok=True)
    items = []
    for number, p in enumerate(sorted(pool[:opts['--max-sheets']], key=lambda p: (p['row']['video_time'], p['detector'])), start=1):
        row = p['row']
        image = cv2.imread(str(p['piece'] / p['detector'] / row['image']))
        if image is None:
            continue
        name = f'sheet_{number:03d}.jpg'
        cv2.imwrite(str(out / name), sheet(image, row['boxes'], p['candidates']), [cv2.IMWRITE_JPEG_QUALITY, 85])
        items.append({'sheet': name, 'origin': 'hard_frame_collector', 'detector': p['detector'], 'video_time': row['video_time'], 'camera': row['camera'], 'reasons': row['reasons'],
                      'detector_boxes': row['n_boxes'], 'red_candidates': len(p['candidates']), 'candidate_boxes': p['candidates'], 'source_image': str(p['piece'] / p['detector'] / row['image']),
                      'human_answer': None})
    (out / 'review_list.json').write_text(json.dumps({'note': 'red boxes are proposals of the other detector, not human labels; human_answer is empty until the user answers', 'summary': summary, 'items': items}, ensure_ascii=False, indent=1), encoding='utf-8')
    cards = ''.join(f'<div class="c"><img src="{i["sheet"]}"><p><b>{i["sheet"]}</b> {int(i["video_time"] // 60)}분 {int(i["video_time"] % 60)}초 · {i["camera"]} · 이유 {html.escape(", ".join(i["reasons"]))} · 빨간 상자 {i["red_candidates"]}개<br>'
                    f'빨간 번호 중 사람이 있는 번호를 적어 주세요 (없으면 0, 사람이 더 있으면 "+").</p></div>' for i in items)
    (out / 'index.html').write_text('<!doctype html><meta charset="utf-8"><title>놓친 장면 판정</title><style>body{font-family:sans-serif;max-width:1640px;margin:auto}.c{margin:24px 0}img{max-width:100%}</style>'
                                    + '<h1>놓친 장면 판정 (모델 제안, 사람 판정 전)</h1>' + cards, encoding='utf-8')
    print(f'{len(items)} sheets in {out}')


if __name__ == '__main__':
    main()
