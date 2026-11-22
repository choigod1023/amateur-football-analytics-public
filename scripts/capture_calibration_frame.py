"""Extract an unmodified local MP4 frame and a blank, unvalidated point template."""
import argparse
import json
from pathlib import Path
import cv2


def capture(source, frame_index, output_dir):
    source, output_dir = Path(source), Path(output_dir)
    if not source.is_file() or source.suffix.lower() != '.mp4':
        raise ValueError('Input must be an existing local MP4')
    if isinstance(frame_index, bool) or not isinstance(frame_index, int) or frame_index < 0:
        raise ValueError('Frame index must be a nonnegative integer')
    if not output_dir.is_dir():
        raise ValueError('Output directory must already exist')
    image_path, template_path = output_dir / 'calibration-frame.png', output_dir / 'calibration-points.json'
    if image_path.exists() or template_path.exists():
        raise FileExistsError('Choose an empty output directory; existing files are never overwritten')
    cap = cv2.VideoCapture(str(source))
    try:
        if not cap.isOpened() or not cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index):
            raise ValueError('Cannot open video or seek to frame')
        ok, frame = cap.read()
        if not ok or frame is None or not frame.size:
            raise ValueError('Cannot decode requested frame')
    finally:
        cap.release()
    ok, encoded = cv2.imencode('.png', frame)
    if not ok:
        raise ValueError('Cannot encode reference image')
    height, width = frame.shape[:2]
    template = {'calibration': {'validated': False, 'image_size_px': [width, height], 'field_size_m': None,
                                'image_points': [], 'field_points_m': []},
                'checkpoints': [], 'requested_frame_index': frame_index,
                'notes': 'Frame seek is decoder-dependent. Enter real measured field dimensions and point pairs; no points are inferred.'}
    with image_path.open('xb') as output:
        output.write(encoded.tobytes())
    with template_path.open('x', encoding='utf-8') as output:
        json.dump(template, output, ensure_ascii=False, indent=2, allow_nan=False)
    return image_path, template_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('frame_index', type=int)
    parser.add_argument('output_directory', type=Path)
    args = parser.parse_args()
    try:
        image, template = capture(args.source, args.frame_index, args.output_directory)
        print(f'Reference: {image}\nPoint template: {template}')
    except (ValueError, OSError) as exc:
        parser.exit(2, f'Cannot prepare calibration: {exc}\n')


if __name__ == '__main__':
    main()
