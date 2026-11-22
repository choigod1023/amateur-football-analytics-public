"""Build a tiled person-detection dataset (YOLO format) from AI Hub 71482 videos and track1.json labels (CPU only, local only).

python scripts/build_aihub_tiles.py <output folder> [--frames 40] [--scale 0.5] [--matches 305,337] [--workers 4]
        [--ours <our dataset with images/train> --repeat 3]

Matches are split by match number, never by frame: TEST (305, 337, 783) and DEV (318, 781, 303) go to images/test and images/val, every other match with a video goes to images/train.
A match is used only when its video and its label file are both on this computer. Videos come from three places: videos already unpacked under work/ (training split and a few validation matches),
and the validation split inside the TAR, where VS.zip is stored as 1 GiB parts that are read as one virtual file; a match taken from there is unpacked to a temporary folder and deleted again.
The label is 1.동영상분석/<match number, 6 digits>/03/track1.json: {'tag': [{'frame': '0', 'data': [{'id', 'tag': [x, y, w, h]}]}]} with x, y, w, h in pixels of the 1920 x 1080 frame.
Every box (field player, goalkeeper, referee) is one class, person. `--scale 0.5` shrinks the frame and the boxes so that a player is about as tall as in our own video (about 30 px instead of about 60 px).
The frames are read in order (grab) and only the wanted ones are decoded to avoid slow random access. The AI Hub data and everything made from it stay on this computer.
"""
import argparse
import bisect
import io
import json
import shutil
import sys
import tarfile
import tempfile
import time
import zipfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from prepare_detector_data import tile_boxes  # noqa: E402

WORK = Path(__file__).resolve().parents[3] / 'work'
TEST_MATCHES = (305, 337, 783)
DEV_MATCHES = (318, 781, 303)
LABEL_ENTRY = '1.동영상분석/{:06d}/03/track1.json'
LOCAL_VIDEOS = {                           # match number -> video already on this computer
    113: 'aihub-training-prefix/training-first.mp4', 131: 'aihub-training-prefix/training-extra-1.mp4', 103: 'aihub-training-prefix/training-extra-2.mp4',
    151: 'aihub-training-prefix/training-extra-3.mp4', 10: 'aihub-training-prefix/training-extra-4.mp4', 106: 'aihub-training-prefix/training-extra-5.mp4',
    1: 'aihub-training-prefix/training-extra-6.mp4', 102: 'role-extra/training-extra-7.mp4', 129: 'role-extra/training-extra-8.mp4', 112: 'role-extra/training-extra-9.mp4',
    104: 'role-extra/training-extra-10.mp4', 105: 'aihub-additional-20261111/training-extra-11.mp4', 159: 'aihub-additional-20261111/training-extra-12.mp4',
    109: 'aihub-additional-20261111/training-extra-13.mp4', 107: 'aihub-additional-20261111/training-extra-14.mp4',
    310: 'role-extra/validation-310.mp4', 318: 'role-extra/validation-318.mp4', 337: 'aihub-new-role-holdout-337-20261111/video.mp4',
}
VALIDATION_TAR = WORK / 'aihub-official' / 'aihub-71482-485857.tar'
VALIDATION_LABELS = WORK / 'aihub-official' / 'validation-labels.zip'
TRAINING_LABELS = WORK / 'aihub-training-prefix' / 'training-labels.zip'


def part_of(match):
    return 'test' if match in TEST_MATCHES else 'val' if match in DEV_MATCHES else 'train'


def sample_frames(total, count, margin=0.03):
    """`count` frame numbers spread evenly between `margin` and `1 - margin` of the video."""
    low, high = int(total * margin), int(total * (1 - margin))
    if count <= 1 or high <= low:
        return [low]
    return sorted({low + (high - low) * i // (count - 1) for i in range(count)})


def frame_tiles(boxes_xywh, width, height, scale=1.0, tile=384, stride=192):
    """Boxes [x, y, w, h] in pixels of the full frame -> (scaled width, scaled height, [(x, y, rows)]) of the tiles of the scaled frame.

    Boxes are scaled with the frame, clipped to it, and boxes under 4 x 8 px after scaling are dropped. The whole height of the frame is cut (top = 0): an AI Hub frame is almost all pitch."""
    new_w, new_h = int(round(width * scale)), int(round(height * scale))
    boxes = []
    for x, y, w, h in boxes_xywh:
        x1, y1, x2, y2 = max(0.0, x * scale), max(0.0, y * scale), min(new_w, (x + w) * scale), min(new_h, (y + h) * scale)
        if x2 - x1 >= 4 and y2 - y1 >= 8:
            boxes.append((x1, y1, x2, y2))
    return new_w, new_h, tile_boxes(boxes, new_w, new_h, tile, stride, 0.0)


class _Parts(io.RawIOBase):
    """The 1 GiB parts of VS.zip inside the TAR as one seekable file (the same approach as work/aihub-official/list_validation_video.py)."""

    def __init__(self, path):
        with tarfile.open(path) as tf:
            members = [m for m in tf.getmembers() if m.isfile() and '.zip.part' in m.name]
        members.sort(key=lambda m: int(m.name.rsplit('part', 1)[1]))
        self.members, self.file, self.pos, self.starts = members, Path(path).open('rb'), 0, [0]
        for m in members:
            self.starts.append(self.starts[-1] + m.size)

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, offset, whence=0):
        self.pos = (0 if whence == 0 else self.pos if whence == 1 else self.starts[-1]) + offset
        if self.pos < 0:
            raise ValueError('negative seek')
        return self.pos

    def read(self, n=-1):
        if n < 0:
            n = self.starts[-1] - self.pos
        result = bytearray()
        while n and self.pos < self.starts[-1]:
            i = bisect.bisect_right(self.starts, self.pos) - 1
            amount = min(n, self.starts[i + 1] - self.pos)
            self.file.seek(self.members[i].offset_data + self.pos - self.starts[i])
            block = self.file.read(amount)
            if not block:
                break
            result.extend(block)
            self.pos += len(block)
            n -= len(block)
        return bytes(result)

    def close(self):
        self.file.close()
        super().close()


def validation_videos():
    """{match number: zip entry name} of the validation videos inside the TAR."""
    found = {}
    with _Parts(VALIDATION_TAR) as source, zipfile.ZipFile(source) as z:
        for info in z.infolist():
            name = info.filename
            if name.lower().endswith('.mp4') and '경기' in name:
                digits = ''.join(c for c in Path(name).stem.rsplit('경기', 1)[1] if c.isdigit())
                found[int(digits)] = name
    return found


def read_labels(match):
    zip_path = VALIDATION_LABELS if match in _validation_label_matches() else TRAINING_LABELS
    with zipfile.ZipFile(zip_path) as z:
        return json.loads(z.read(LABEL_ENTRY.format(match)).decode('utf-8-sig'))


_cache = {}


def _validation_label_matches():
    if 'v' not in _cache:
        with zipfile.ZipFile(VALIDATION_LABELS) as z:
            _cache['v'] = {int(n.split('/')[1]) for n in z.namelist() if n.endswith('track1.json')}
    return _cache['v']


def process_match(job):
    """One match: (match number, video source, output folder, frames, scale) -> dict of counts and seconds."""
    import cv2
    match, source, out, frames, scale = job
    started = time.time()
    temporary = None
    try:
        label = read_labels(match)
        by_frame = {int(row['frame']): [r['tag'] for r in row['data'] if isinstance(r.get('tag'), list) and len(r['tag']) == 4] for row in label['tag']}
        if isinstance(source, str) and not Path(source).is_file():          # a zip entry name in the validation TAR
            temporary = Path(tempfile.mkdtemp(prefix=f'aihub{match}_'))
            with _Parts(VALIDATION_TAR) as parts, zipfile.ZipFile(parts) as z:
                with z.open(source) as read, (temporary / 'video.mp4').open('wb') as write:
                    shutil.copyfileobj(read, write, 8 << 20)
            source = str(temporary / 'video.mp4')
        capture = cv2.VideoCapture(str(source))
        if not capture.isOpened():
            return {'match': match, 'error': 'video did not open'}
        total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        width, height = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)), int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        wanted = [f for f in sample_frames(total, frames) if by_frame.get(f)]
        part = part_of(match)
        for sub in ('images', 'labels'):
            (Path(out) / sub / part).mkdir(parents=True, exist_ok=True)
        tiles = people = used = 0
        index = 0
        for target in wanted:
            while index < target:
                if not capture.grab():
                    break
                index += 1
            ok, frame = capture.read()
            index += 1
            if not ok:
                continue
            new_w, new_h, cut = frame_tiles(by_frame[target], width, height, scale)
            if scale != 1.0:
                frame = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)
            for x, y, rows in cut:
                stem = f'm{match}_f{target}_{x}_{y}'
                cv2.imwrite(str(Path(out) / 'images' / part / (stem + '.jpg')), frame[y:y + 384, x:x + 384], [cv2.IMWRITE_JPEG_QUALITY, 95])
                (Path(out) / 'labels' / part / (stem + '.txt')).write_text(''.join(f'{c} {a:.6f} {b:.6f} {w:.6f} {h:.6f}\n' for c, a, b, w, h in rows), encoding='utf-8')
                tiles += 1
                people += len(rows)
            used += 1
        capture.release()
        return {'match': match, 'part': part, 'frames': used, 'tiles': tiles, 'people': people, 'video_frames': total, 'label_frames': len(by_frame), 'seconds': round(time.time() - started, 1)}
    finally:
        if temporary is not None:
            shutil.rmtree(temporary, ignore_errors=True)


def write_yaml(path, train, val):
    lines = [f'path: {Path(path).parent.resolve().as_posix()}']
    lines.append('train: ' + (train[0] if len(train) == 1 else '[' + ', '.join(train) + ']'))
    lines += [f'val: {val}', 'names:', '  0: person']
    Path(path).write_text('\n'.join(lines) + '\n', encoding='utf-8')


def add_ours(out, ours, repeat):
    """Copies our own train tiles into images/train (`repeat` times, name suffix _rN) so that the mixed data holds them several times."""
    count = 0
    for image in sorted((Path(ours) / 'images' / 'train').glob('*.jpg')):
        label = Path(ours) / 'labels' / 'train' / (image.stem + '.txt')
        if not label.is_file():
            continue
        for r in range(repeat):
            shutil.copy2(image, Path(out) / 'images' / 'train' / f'own_{image.stem}_r{r}.jpg')
            shutil.copy2(label, Path(out) / 'labels' / 'train' / f'own_{image.stem}_r{r}.txt')
            count += 1
    return count


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('output')
    parser.add_argument('--frames', type=int, default=40)
    parser.add_argument('--scale', type=float, default=0.5)
    parser.add_argument('--matches', help='comma separated match numbers (default: every match with video and labels)')
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--ours', help='our own detector data folder (with images/train and labels/train) to copy in (the mixed data)')
    parser.add_argument('--repeat', type=int, default=3)
    args = parser.parse_args()
    out = Path(args.output)
    if out.exists():
        raise SystemExit(f'{out} exists; use a new folder')
    in_tar = validation_videos()
    label_matches = _validation_label_matches()
    with zipfile.ZipFile(TRAINING_LABELS) as z:
        label_matches |= {int(n.split('/')[1]) for n in z.namelist() if n.endswith('track1.json')}
    sources = {m: str(WORK / v) for m, v in LOCAL_VIDEOS.items() if (WORK / v).is_file()}
    for m, name in in_tar.items():
        sources.setdefault(m, name)
    chosen = sorted(m for m in sources if m in label_matches)
    if args.matches:
        chosen = [m for m in chosen if m in {int(v) for v in args.matches.split(',')}]
    print('matches with video and labels:', len(chosen), '| train', sum(part_of(m) == 'train' for m in chosen), 'dev', [m for m in chosen if part_of(m) == 'val'], 'test', [m for m in chosen if part_of(m) == 'test'], flush=True)
    out.mkdir(parents=True)
    jobs = [(m, sources[m], str(out), args.frames, args.scale) for m in chosen]
    results = []
    started = time.time()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for result in pool.map(process_match, jobs):
            results.append(result)
            print(result, flush=True)
    summary = {'seconds': round(time.time() - started, 1), 'frames': args.frames, 'scale': args.scale, 'matches': results}
    for part in ('train', 'val', 'test'):
        rows = [r for r in results if r.get('part') == part]
        summary[part] = {'matches': len(rows), 'tiles': sum(r['tiles'] for r in rows), 'people': sum(r['people'] for r in rows)}
    if args.ours:
        summary['own_tiles_copied'] = add_ours(out, args.ours, args.repeat)
    (out / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding='utf-8')
    write_yaml(out / 'data.yaml', ['images/train'], 'images/val')
    print({k: v for k, v in summary.items() if k != 'matches'})


if __name__ == '__main__':
    main()
