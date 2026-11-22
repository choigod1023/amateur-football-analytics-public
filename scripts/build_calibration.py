"""Build an unvalidated calibration from unordered, manually measured point pairs.

The widest fitting quadrilateral is selected by image area, not accuracy.  Only
separate checkpoints are evaluated; no validation flag is ever switched on.
"""
import argparse
import itertools
import json
from pathlib import Path

import cv2
import numpy as np

if __package__:
    from .evaluate_calibration import evaluate
else:
    from evaluate_calibration import evaluate


def build(data):
    size = data.get('image_size_px')
    dims = np.asarray(data.get('field_size_m'), dtype=float)
    points = data.get('fitting_points')
    checks = data.get('checkpoints', [])
    if (not isinstance(size, list) or len(size) != 2 or any(isinstance(n, bool) or not isinstance(n, int) or n < 1 for n in size)
            or dims.shape != (2,) or not np.isfinite(dims).all() or (dims <= 0).any()):
        raise ValueError('image size and measured field dimensions are required')
    if not isinstance(points, list) or not 4 <= len(points) <= 20 or not isinstance(checks, list):
        raise ValueError('provide between 4 and 20 fitting points and a checkpoint list')
    images, fields = [], []
    for point in points:
        image = np.asarray(point['image_point'], dtype=float)
        field = np.asarray(point['field_point_m'], dtype=float)
        if (image.shape != (2,) or field.shape != (2,) or not np.isfinite(image).all() or not np.isfinite(field).all()
                or (image < 0).any() or image[0] >= size[0] or image[1] >= size[1]
                or (field < 0).any() or (field > dims).any()):
            raise ValueError('point outside image or measured field')
        if any(np.linalg.norm(image - prev) < 1 for prev in images) or any(np.linalg.norm(field - prev) < .01 for prev in fields):
            raise ValueError('duplicate fitting point')
        images.append(image); fields.append(field)
    # Input order is arbitrary. Image hull defines correspondence order; ensure
    # the corresponding pitch polygon is convex in precisely that same order.
    best = None
    for combo in itertools.combinations(range(len(points)), 4):
        image = np.asarray([images[i] for i in combo], np.float32)
        hull = cv2.convexHull(image, returnPoints=False).reshape(-1)
        if len(hull) != 4:
            continue
        ordered = [combo[int(i)] for i in hull]
        image = np.asarray([images[i] for i in ordered], np.float32)
        field = np.asarray([fields[i] for i in ordered], np.float32)
        area = abs(cv2.contourArea(image))
        if area < 100 or abs(cv2.contourArea(field)) < 1 or not cv2.isContourConvex(field):
            continue
        if best is None or area > best[0]:
            best = (area, ordered)
    if best is None:
        raise ValueError('no usable corresponding quadrilateral; check point labels and geometry')
    order = best[1]
    cal = {'validated': False, 'image_size_px': size, 'field_size_m': dims.tolist(),
           'image_points': [images[i].tolist() for i in order], 'field_points_m': [fields[i].tolist() for i in order]}
    # A checkpoint cannot repeat any fitting input, including discarded points.
    for check in checks:
        point = np.asarray(check['image_point'], dtype=float)
        target = np.asarray(check['field_point_m'], dtype=float)
        if (point.shape != (2,) or target.shape != (2,) or not np.isfinite(point).all() or not np.isfinite(target).all()
                or any(np.linalg.norm(point - image) < 1 for image in images)
                or any(np.linalg.norm(target - field) < .01 for field in fields)):
            raise ValueError('checkpoint duplicates or is not independent of a fitting point')
    result = evaluate(cal, checks) if checks else None
    unused = [i for i in range(len(points)) if i not in order]
    # These points took part in selecting the widest polygon: this is only an
    # in-sample consistency warning, never an independent accuracy estimate.
    consistency = evaluate(cal, [points[i] for i in unused]) if unused else None
    return {'calibration': cal, 'fitting_indices': order,
            'unused_fitting_indices': unused,
            'unused_fitting_consistency': consistency,
            'independent_checkpoint_report': result,
            'warning': 'Widest area does not prove accuracy. Manually check independently measured points, pitch dimensions and camera stability.'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('input', type=Path, help='JSON with image_size_px, field_size_m, fitting_points, checkpoints')
    args = p.parse_args()
    try:
        data = json.loads(args.input.read_text(encoding='utf-8'))
        print(json.dumps(build(data), ensure_ascii=False, indent=2, allow_nan=False))
    except (KeyError, TypeError, ValueError, OSError) as exc:
        p.exit(2, f'Invalid input: {exc}\n')


if __name__ == '__main__':
    main()
