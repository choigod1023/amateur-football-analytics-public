"""Opt-in position diagnostics. Pixel tolerance is a scenario, not a confidence interval.

Coordinates remain centred pitch metres; no role/team inference or boundary clipping.
"""
import numpy as np

from app.pitch_map import fit, apply, landmarks


def calibration_diagnostics(record):
    fitted = fit(record)
    if 'error' in fitted:
        return {'valid': False, 'reason': fitted['error'], 'loo': []}
    known = landmarks(record.get('pitch'))
    points = [p for p in record.get('points', []) if p.get('landmark') in known]
    errors = []
    for i, point in enumerate(points):
        trial = fit({**record, 'points': points[:i] + points[i + 1:]})
        xy = None if 'error' in trial else apply(trial['H'], point['x'], point['y'])
        error = None if xy is None else float(np.linalg.norm(np.array(xy) - known[point['landmark']]))
        errors.append({'landmark': point['landmark'], 'error_m': error})
    valid = [e['error_m'] for e in errors if e['error_m'] is not None]
    return {'valid': True, 'in_sample_rms_m': fitted['rms'], 'loo': errors,
            'loo_max_m': max(valid) if valid else None,
            'loo_complete': len(valid) == len(points),
            'interpretation': 'clicked-landmark consistency, not measured player-position accuracy'}


def position_quality(fitted, box, width, height, shift=(0., 0.), bg=None,
                     foot_tolerance_px=3., tactical_budget_m=1.):
    """Exact projective envelope of a +/- pixel square around bottom-centre.

    Convex square projects to a convex quadrilateral while the denominator stays
    positive. Maximum distance from the centre is attained at a vertex. This
    bounds ONLY the stated foot perturbation, excluding calibration/pose errors.
    """
    invalid = {'valid': False, 'position_m': None, 'tactical_foot_gate': False}
    try:
        box = np.asarray(box, dtype=float)
        shift = np.asarray(shift, dtype=float)
        h = np.asarray(fitted['H'], dtype=float)
        background = np.asarray(bg if bg is not None else (1., 0., 0., 0.), dtype=float)
        half = np.array([fitted['pitch']['length'], fitted['pitch']['width']], dtype=float)/2
        if box.shape != (4,) or shift.shape != (2,) or h.shape != (3, 3) or background.shape != (4,):
            return {**invalid, 'reason': 'invalid_shape'}
        width, height, foot_tolerance_px, tactical_budget_m = map(float, (width, height, foot_tolerance_px, tactical_budget_m))
    except (KeyError, TypeError, ValueError):
        return {**invalid, 'reason': 'invalid_input'}
    values = np.asarray([*box, width, height, *shift, foot_tolerance_px, tactical_budget_m], float)
    if not np.all(np.isfinite(values)) or width <= 0 or height <= 0 or foot_tolerance_px < 0 or tactical_budget_m < 0:
        return {**invalid, 'reason': 'invalid_input'}
    if box[2] <= box[0] or box[3] <= box[1] or 'H' not in fitted:
        return {**invalid, 'reason': 'invalid_box_or_calibration'}
    a, b, tx, ty = background
    transform = np.array([[a, -b, tx-a*shift[0]+b*shift[1]],
                          [b, a, ty-b*shift[0]-a*shift[1]], [0., 0., 1.]])
    matrix = h @ np.diag([1/width, 1/height, 1.]) @ transform
    if not np.all(np.isfinite(matrix)) or np.linalg.matrix_rank(matrix) < 3:
        return {**invalid, 'reason': 'degenerate_projection'}
    p = np.array([(box[0]+box[2])/2, box[3], 1.])
    r = foot_tolerance_px
    samples = np.array([p, p+[-r,-r,0], p+[-r,r,0], p+[r,-r,0], p+[r,r,0]])
    homogeneous = samples @ matrix.T
    if np.any(homogeneous[:, 2] <= 1e-12):
        return {**invalid, 'reason': 'horizon_crossing'}
    projected = homogeneous[:, :2] / homogeneous[:, 2, None]
    centre = projected[0]
    jacobian = (matrix[:2, :2] - centre[:, None]*matrix[2, :2]) / homogeneous[0, 2]
    radius = float(np.max(np.linalg.norm(projected[1:]-centre, axis=1)))
    if not np.all(np.isfinite(half)) or np.any(half <= 0):
        return {**invalid, 'reason': 'invalid_pitch_dimensions'}
    outside = bool(np.any(np.abs(centre) > half))
    # A bounding rectangle entirely inside establishes an inside envelope;
    # otherwise conservatively mark boundary ambiguity, never clamp.
    envelope_inside = bool(np.all(np.abs(projected) <= half))
    boundary = 'outside' if outside else ('inside' if envelope_inside else 'boundary_uncertain')
    return {'valid': True, 'position_m': centre.tolist(), 'boundary': boundary,
            'jacobian_m_per_px': jacobian.tolist(),
            'max_sensitivity_m_per_px': float(np.linalg.svd(jacobian, compute_uv=False)[0]),
            'foot_tolerance_px': r, 'foot_envelope_radius_m': radius,
            'tactical_foot_gate': envelope_inside and radius <= tactical_budget_m,
            'tactical_budget_m': tactical_budget_m,
            'calibration_fit_gate_checked': False,
            'calibration_uncertainty_included': False}
