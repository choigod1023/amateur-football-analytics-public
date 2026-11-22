"""Prepare a server config from measured pitch points and a reference image.

No analysis is started. Calibration is inactive unless the operator explicitly
confirms independent measurements and supplies a tolerance in metres.
"""
import argparse
import copy
import json
import math
from pathlib import Path

import cv2
import numpy as np

if __package__:
    from .build_calibration import build
else:
    from build_calibration import build


def prepare(base, measured, reference, *, accept_measured=False, max_error_m=None):
    if not isinstance(base, dict):
        raise ValueError('base configuration must be an object')
    built = build(measured)
    cal = built['calibration']
    # The guard reference must be a user-supplied, decodable local frame at
    # the same pixel resolution as the calibration; never trust a placeholder.
    path = Path(reference).resolve(strict=True)
    reference_frame = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if reference_frame is None or [reference_frame.shape[1], reference_frame.shape[0]] != cal['image_size_px']:
        raise ValueError('reference image missing, unreadable, or resolution mismatch')
    cal['camera_guard_reference'] = str(path)
    region = measured.get('camera_guard_feature_region')
    if region is not None:
        polygon = np.asarray(region, dtype=np.float32)
        w, h = cal['image_size_px']
        if (polygon.shape != (4, 2) or not np.isfinite(polygon).all()
                or not cv2.isContourConvex(polygon) or abs(cv2.contourArea(polygon)) < 100
                or (polygon < 0).any() or (polygon[:, 0] >= w).any() or (polygon[:, 1] >= h).any()):
            raise ValueError('camera guard feature region must be a convex quadrilateral inside the image')
        cal['camera_guard_feature_region'] = polygon.tolist()
    checks = built['independent_checkpoint_report']
    if accept_measured:
        if isinstance(max_error_m, bool) or not isinstance(max_error_m, (int, float)) or not math.isfinite(max_error_m) or max_error_m <= 0:
            raise ValueError('explicit positive maximum error in metres is required')
        # Zero/partial check results cannot support the operator's confirmation.
        if checks is None or checks['total'] < 3 or checks['measured'] != checks['total']:
            raise ValueError('at least three independent, in-area checkpoints are required')
        # The user-facing report is rounded to millimetres. Compare unrounded
        # values so a reported 0.500m cannot silently pass a 0.500m limit when
        # its actual error is slightly above the limit.
        matrix = cv2.getPerspectiveTransform(np.asarray(cal['image_points'], np.float32),
                                             np.asarray(cal['field_points_m'], np.float32))
        actual = cv2.perspectiveTransform(np.asarray([[c['image_point'] for c in measured['checkpoints']]], np.float32), matrix)[0]
        expected = np.asarray([c['field_point_m'] for c in measured['checkpoints']], dtype=float)
        max_exact = float(np.max(np.linalg.norm(actual.astype(float) - expected, axis=1)))
        if not math.isfinite(max_exact) or max_exact > max_error_m:
            raise ValueError('independent checkpoint error exceeds the selected tolerance')
        cal['validated'] = True
    config = copy.deepcopy(base)
    config['calibration'] = cal
    return {'config': config, 'independent_checkpoint_report': checks,
            'fitting_indices': built['fitting_indices'],
            'unused_fitting_indices': built['unused_fitting_indices'],
            'unused_fitting_consistency': built['unused_fitting_consistency'],
            'warning': ('Operator confirmation and checkpoint error do not prove calibration accuracy or a fixed camera. '
                        'The configured camera guard may abstain on the first video frame.')}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base', type=Path, required=True, help='existing configuration JSON, read only')
    p.add_argument('--measurements', type=Path, required=True, help='build_calibration input JSON')
    p.add_argument('--reference', type=Path, required=True, help='reference frame for camera movement guard')
    p.add_argument('--output', type=Path, required=True, help='new config file; existing files are never overwritten')
    p.add_argument('--accept-measured', action='store_true', help='operator confirms reference frame, measurements and fixed camera')
    p.add_argument('--max-error-m', type=float, help='operator-selected maximum independent checkpoint error')
    args = p.parse_args()
    try:
        base = json.loads(args.base.read_text(encoding='utf-8'))
        measured = json.loads(args.measurements.read_text(encoding='utf-8'))
        result = prepare(base, measured, args.reference, accept_measured=args.accept_measured, max_error_m=args.max_error_m)
        with args.output.open('x', encoding='utf-8') as f:
            json.dump(result['config'], f, ensure_ascii=False, indent=2, allow_nan=False)
            f.write('\n')
        print(json.dumps({k: v for k, v in result.items() if k != 'config'}, ensure_ascii=False, indent=2, allow_nan=False))
    except (KeyError, TypeError, ValueError, OSError) as exc:
        p.exit(2, f'Cannot prepare calibration: {exc}\n')


if __name__ == '__main__':
    main()
