"""Measure a four-point pitch calibration on separately labelled checkpoints."""
import argparse
import json
from pathlib import Path

import cv2
import numpy as np


def evaluate(calibration, checkpoints):
    src = np.asarray(calibration['image_points'], dtype=np.float32)
    dst = np.asarray(calibration['field_points_m'], dtype=np.float32)
    dimensions = np.asarray(calibration['field_size_m'], dtype=float)
    if (src.shape != (4, 2) or dst.shape != (4, 2) or dimensions.shape != (2,)
            or not np.isfinite(src).all() or not np.isfinite(dst).all()
            or not np.isfinite(dimensions).all() or (dimensions <= 0).any()
            or not cv2.isContourConvex(src) or not cv2.isContourConvex(dst)
            or abs(cv2.contourArea(src)) < 100 or abs(cv2.contourArea(dst)) < 1
            or (dst < 0).any() or (dst > dimensions).any()):
        raise ValueError('Invalid calibration geometry')
    if not isinstance(checkpoints, list) or not checkpoints:
        raise ValueError('At least one independent checkpoint is required')
    matrix = cv2.getPerspectiveTransform(src, dst)
    rows = []
    for checkpoint in checkpoints:
        image = np.asarray(checkpoint['image_point'], dtype=float)
        expected = np.asarray(checkpoint['field_point_m'], dtype=float)
        if (image.shape != (2,) or expected.shape != (2,) or not np.isfinite(image).all()
                or not np.isfinite(expected).all() or (expected < 0).any()
                or (expected > dimensions).any()):
            raise ValueError('Invalid checkpoint')
        if any(np.linalg.norm(image - p) < 1.0 for p in src):
            raise ValueError('Checkpoint duplicates a fitting point')
        if cv2.pointPolygonTest(src, tuple(image), False) < 0:
            rows.append({'error_m': None, 'reason': 'outside_calibrated_area'})
            continue
        actual = cv2.perspectiveTransform(np.array([[image]], dtype=np.float32), matrix)[0, 0]
        if not np.isfinite(actual).all() or (actual < 0).any() or (actual > dimensions).any():
            rows.append({'error_m': None, 'reason': 'projection_outside_pitch'})
            continue
        rows.append({'error_m': round(float(np.linalg.norm(actual - expected)), 3), 'reason': None})
    errors = [r['error_m'] for r in rows if r['error_m'] is not None]
    return {'checkpoints': rows, 'measured': len(errors), 'total': len(rows),
            'median_error_m': round(float(np.median(errors)), 3) if errors else None,
            'max_error_m': round(max(errors), 3) if errors else None,
            'validated': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path, help='JSON with calibration and checkpoints')
    args = parser.parse_args()
    try:
        data = json.loads(args.input.read_text(encoding='utf-8'))
        print(json.dumps(evaluate(data['calibration'], data['checkpoints']), ensure_ascii=False, indent=2, allow_nan=False))
    except (KeyError, TypeError, ValueError, OSError) as exc:
        parser.exit(2, f'Invalid input: {exc}\n')


if __name__ == '__main__':
    main()
