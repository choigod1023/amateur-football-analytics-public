"""Build a *candidate* pitch calibration from four manually identified lines.

Line labels must be verified for the current camera frame and the field must
use standard penalty-area markings. No camera motion or accuracy is inferred.
"""
import argparse
import json
from pathlib import Path
import numpy as np

if __package__:
    from .build_calibration import build
else:
    from build_calibration import build


def _intersection(first, second, size):
    a, b = np.asarray(first, dtype=float), np.asarray(second, dtype=float)
    if a.shape != (2, 2) or b.shape != (2, 2) or not np.isfinite(a).all() or not np.isfinite(b).all():
        raise ValueError('each line must contain two finite image points')
    for line in (a, b):
        if (line < 0).any() or (line[:, 0] >= size[0]).any() or (line[:, 1] >= size[1]).any():
            raise ValueError('line endpoints must lie inside image')
    u, v = a[1] - a[0], b[1] - b[0]
    lu, lv = np.linalg.norm(u), np.linalg.norm(v)
    matrix = np.column_stack((u, -v))
    if min(lu, lv) < 10 or abs(np.linalg.det(matrix)) / (lu * lv) < .08:
        raise ValueError('line pair too short or near parallel')
    t, s = np.linalg.solve(matrix, b[0] - a[0])
    if not (-20 / lu <= t <= 1 + 20 / lu and -20 / lv <= s <= 1 + 20 / lv):
        raise ValueError('intersection too far outside labelled segments')
    p = a[0] + t * u
    if not (0 <= p[0] < size[0] and 0 <= p[1] < size[1]):
        raise ValueError('intersection outside image')
    return p.tolist()


def candidate(data):
    """Accept image size, measured pitch size, side, and four labelled segments.

    side=left means x=0 goal line; top/bottom are y=width/2 +/- 20.16m.
    The user must confirm that labels are consistent with the chosen axes.
    """
    size = data['image_size_px']
    if not isinstance(size, list) or len(size) != 2 or any(type(x) is not int or x < 1 for x in size):
        raise ValueError('positive integer image_size_px required')
    dims = np.asarray(data['field_size_m'], dtype=float)
    if dims.shape != (2,) or not np.isfinite(dims).all() or dims[0] <= 33 or dims[1] <= 40.32:
        raise ValueError('measured field dimensions are incompatible with standard penalty area')
    side = data['side']
    if side not in ('left', 'right'):
        raise ValueError('side must be left or right')
    lines = data['lines']
    end, front, top, bottom = (lines[k] for k in ('end', 'front', 'top', 'bottom'))
    end_x, front_x = (0., 16.5) if side == 'left' else (float(dims[0]), float(dims[0]) - 16.5)
    top_y, bottom_y = float(dims[1]) / 2 - 20.16, float(dims[1]) / 2 + 20.16
    records = [(_intersection(end, top, size), [end_x, top_y]),
               (_intersection(front, top, size), [front_x, top_y]),
               (_intersection(front, bottom, size), [front_x, bottom_y]),
               (_intersection(end, bottom, size), [end_x, bottom_y])]
    result = build({'image_size_px': size, 'field_size_m': dims.tolist(),
                    'fitting_points': [{'image_point': a, 'field_point_m': b} for a, b in records],
                    'checkpoints': data.get('checkpoints', [])})
    result['warning'] = ('Candidate only: validate independent measured field points, '
                         'line labels, real pitch dimensions, and camera stability before use.')
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('input', type=Path)
    args = p.parse_args()
    try:
        print(json.dumps(candidate(json.loads(args.input.read_text(encoding='utf-8'))), ensure_ascii=False, indent=2, allow_nan=False))
    except (KeyError, TypeError, ValueError, OSError) as exc:
        p.exit(2, f'Invalid input: {exc}\n')


if __name__ == '__main__':
    main()
