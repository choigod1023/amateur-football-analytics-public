"""Put the set-piece candidates of find_set_piece_candidates.py on the page /alerts as one review session (the page the coach already uses to mark alerts).

python scripts/build_set_piece_review.py <video> <candidates.json> <store> [--session setpiece1] [--confidence high,medium,low]

For every candidate three frames (4 s before, at the time, 4 s after) are cut from the video, put side by side into <store>/alerts/<session>/alerts_<n>.jpg, and one line goes into alerts.jsonl
(kind 'set_piece_check', the guess, the reasons and the video time). The coach marks: 맞음 = a set piece starts here, 틀림 = not a set piece, 맞지만 쓸모없음 = cannot tell.
Nothing else in the store is changed; marks of the coach are the only ground truth, the candidates themselves are guesses (origin: set_piece_candidates).
"""
import argparse
import json
from pathlib import Path

CONFIDENCE = {'높음': 'high', '중간': 'medium', '낮음': 'low'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('video')
    parser.add_argument('candidates')
    parser.add_argument('store')
    parser.add_argument('--session', default='setpiece1')
    parser.add_argument('--confidence', default='high,medium,low')
    args = parser.parse_args()
    import cv2
    wanted = set(args.confidence.split(','))
    data = json.loads(Path(args.candidates).read_text(encoding='utf-8'))
    candidates = data['candidates'] if isinstance(data, dict) and 'candidates' in data else data
    items = candidates if isinstance(candidates, list) else list(candidates.values())
    items = [c for c in items if CONFIDENCE.get(c['confidence'], c['confidence']) in wanted]
    items.sort(key=lambda c: c['time_s'])
    folder = Path(args.store) / 'alerts' / args.session
    folder.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(args.video)
    rows = []
    for c in items:
        frames = []
        for offset in (-4.0, 0.0, 4.0):
            cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, c['time_s'] + offset) * 1000)
            ok, image = cap.read()
            if not ok:
                continue
            image = cv2.resize(image, (640, int(image.shape[0] * 640 / image.shape[1])))
            cv2.putText(image, f'{offset:+.0f} s', (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 255), 2, cv2.LINE_AA)
            frames.append(image)
        if not frames:
            continue
        number = len(rows)
        cv2.imwrite(str(folder / f'alerts_{number:04d}.jpg'), cv2.hconcat(frames), [cv2.IMWRITE_JPEG_QUALITY, 85])
        reasons = ', '.join(c.get('reasons', []))
        text = (f'영상 {c["time"]} 근처(구간 {c.get("window_text", "")}): 세트피스가 시작되는 장면인가요? 추정 종류: {c["kind_guess"]}, 확신 {c["confidence"]}. '
                f'근거: {reasons}. 맞으면 맞음, 세트피스가 아니면 틀림, 화면으로 알 수 없으면 맞지만 쓸모없음을 눌러 주세요. 사진은 4초 전, 그 시각, 4초 뒤입니다.')
        rows.append({'time': c['time_s'], 'kind': 'set_piece_check', 'polarity': 'neutral', 'title': f'세트피스 후보 {c["time"]} ({c["kind_guess"]})', 'text': text,
                     'candidate_id': c.get('id'), 'origin': 'set_piece_candidates'})
    (folder / 'alerts.jsonl').write_text('\n'.join(json.dumps(r, ensure_ascii=False) for r in rows) + '\n', encoding='utf-8')
    print(len(rows), 'candidates written to', folder)


if __name__ == '__main__':
    main()
