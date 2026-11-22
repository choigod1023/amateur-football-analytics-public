"""Put the alerts of a replay (scripts/replay_live_feedback.py --alerts) on the page /alerts so that a human can mark them right, wrong or useless.

Every alert gets the video frame of its moment as picture. The session is written to <store>/alerts/<session>/ (alerts.jsonl and alerts_0000.jpg ...).
The store is only added to; nothing existing is changed. The session name is the folder name, so give a new name for every import.

python scripts/import_alerts_for_review.py alerts.jsonl match.mp4 <store> --session replay-h1
"""
import argparse
import json
import re
import sys
from pathlib import Path

import cv2


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('alerts', help='alerts.jsonl of a replay')
    parser.add_argument('video')
    parser.add_argument('store')
    parser.add_argument('--session', required=True)
    parser.add_argument('--width', type=int, default=1280, help='width of the saved picture')
    args = parser.parse_args()
    if not re.match(r'^[A-Za-z0-9_-]{1,40}$', args.session):
        raise SystemExit('The session name may only hold letters, digits, - and _ (40 at most).')
    folder = Path(args.store) / 'alerts' / args.session
    if (folder / 'alerts.jsonl').exists():
        raise SystemExit(f'{folder} exists already; use another session name.')
    rows = [json.loads(line) for line in Path(args.alerts).read_text(encoding='utf-8').splitlines() if line.strip()]
    capture = cv2.VideoCapture(args.video)
    if not capture.isOpened():
        raise SystemExit('Could not open the video.')
    folder.mkdir(parents=True, exist_ok=True)
    saved = 0
    for number, row in enumerate(rows):
        capture.set(cv2.CAP_PROP_POS_MSEC, float(row['time']) * 1000)
        ok, frame = capture.read()
        if not ok:
            continue
        scale = args.width / frame.shape[1]
        frame = cv2.resize(frame, (args.width, int(frame.shape[0] * scale)), interpolation=cv2.INTER_AREA)
        cv2.imwrite(str(folder / f'alerts_{number:04d}.jpg'), frame, [cv2.IMWRITE_JPEG_QUALITY, 88])
        saved += 1
    (folder / 'alerts.jsonl').write_text('\n'.join(json.dumps(r, ensure_ascii=False) for r in rows) + '\n', encoding='utf-8')
    print(f'{len(rows)} alerts, {saved} pictures -> {folder}', file=sys.stderr)


if __name__ == '__main__':
    main()
