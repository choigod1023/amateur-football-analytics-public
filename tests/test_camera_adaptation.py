import cv2
import numpy as np
import pytest
from app.camera_adaptation import CameraAdaptation, transfer_calibration, _project


def scene():
    rng = np.random.default_rng(83)
    image = np.full((500, 800, 3), (40, 100, 45), np.uint8)
    for x, y, r in rng.integers([45, 65, 2], [750, 460, 8], size=(900, 3)):
        colour = tuple(int(v) for v in rng.integers(40, 240, size=3))
        cv2.circle(image, (int(x), int(y)), int(r), colour, -1)
    return image, np.float32([[25, 45], [775, 45], [775, 475], [25, 475]])


def test_perspective_and_zoom_registration_and_transfer():
    reference, polygon = scene()
    h = np.array([[.94, .035, 16], [-.025, .97, 17], [.00003, -.00004, 1.]])
    current = cv2.warpPerspective(reference, h, (800, 500))
    result = CameraAdaptation().fit(reference, current, polygon)
    assert result['status'] == 'ready', result
    points = np.float32([[150, 150], [650, 150], [650, 400], [150, 400]])
    actual = _project(points, h)
    recovered = _project(actual, np.array(result['current_to_reference']))
    assert np.max(np.linalg.norm(recovered - points, axis=1)) < 3
    original = {'H': np.diag([100., 60., 1.]), 'pitch': {'length':100, 'width':60}}
    new = transfer_calibration(original, result)
    expected = _project(points / [800, 500], original['H'])
    measured = _project(actual / [800, 500], new['H'])
    assert np.max(np.linalg.norm(measured - expected, axis=1)) < .6
    assert result['metric_accuracy_verified'] is False
    assert np.array_equal(original['H'], np.diag([100., 60., 1.]))


def test_blank_and_degenerate_evidence_never_reuses_identity():
    reference, polygon = scene()
    adapter = CameraAdaptation()
    assert adapter.fit(reference, reference, polygon)['status'] == 'ready'
    result = adapter.fit(reference, np.zeros_like(reference), polygon)
    assert result['status'] == 'needs_review' and result['current_to_reference'] is None
    result = adapter.fit(reference, reference, [[0, 0], [10, 0], [20, 0], [30, 0]])
    assert result['status'] == 'needs_review'
    with pytest.raises(ValueError): transfer_calibration({'H': np.eye(3)}, result)


def test_transfer_respects_different_image_dimensions():
    reference_to_current = np.array([[2., 0., 30.], [0., 2., 10.], [0., 0., 1.]])
    result = {'status':'ready', 'current_to_reference':np.linalg.inv(reference_to_current).tolist(),
              'reference_size':[800,500], 'current_size':[1600,1000]}
    old = {'H':np.diag([100.,60.,1.])}
    new = transfer_calibration(old,result)
    ref = np.array([[200.,100.], [700.,400.]])
    current = _project(ref, reference_to_current)
    assert np.allclose(_project(current / [1600,1000],new['H']), _project(ref / [800,500],old['H']))


def test_registration_does_not_confuse_resolution_change_with_excessive_zoom():
    reference, polygon = scene()
    enlarged = cv2.resize(reference, (1600,1000))
    result = CameraAdaptation().fit(reference,enlarged,polygon)
    assert result['status'] == 'ready', result
    points = np.float32([[150,150],[650,400]])
    assert np.max(np.linalg.norm(_project(points*2,np.array(result['current_to_reference']))-points,axis=1)) < 3


def test_explicit_feature_method_and_invalid_method():
    reference, polygon = scene()
    assert CameraAdaptation(method='sift').fit(reference,reference,polygon)['feature_method'] == 'sift'
    with pytest.raises(ValueError):CameraAdaptation(method='unknown')


def test_mirrored_or_nonoverlapping_geometry_rejected():
    _, polygon = scene()
    assert CameraAdaptation._geometry(np.array([[-1.,0,800],[0,1.,0],[0,0,1.]]),polygon,(500,800,3)) is None
    assert CameraAdaptation._geometry(np.array([[1.,0,1200],[0,1.,0],[0,0,1.]]),polygon,(500,800,3)) is None


def test_background_texture_cannot_establish_pitch_registration():
    image, _ = scene()
    polygon = np.float32([[200,150],[600,150],[600,400],[200,400]])
    cv2.fillConvexPoly(image, polygon.astype(np.int32), (40,100,45))
    result = CameraAdaptation().fit(image,image,polygon)
    assert result['status'] == 'needs_review'


def test_local_feature_cluster_is_not_enough_to_transfer_whole_field():
    image = np.full((500,800,3), (40,100,45), np.uint8)
    rng = np.random.default_rng(12)
    image[210:290,350:450] = rng.integers(0,255,(80,100,3),dtype=np.uint8)
    polygon = np.float32([[25,45],[775,45],[775,475],[25,475]])
    result = CameraAdaptation().fit(image,image,polygon)
    assert result['status'] == 'needs_review' and result['reason'] == 'localized_support'
