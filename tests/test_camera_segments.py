from app.camera_segments import CAM1_UNTIL, CAM3_FROM, camera_of


def test_first_half_is_cam1_and_second_half_cam3():
    assert camera_of(70.0) == 'cam1'
    assert camera_of(1490.0) == 'cam1'
    assert camera_of(1740.0) == 'cam3'
    assert camera_of(2900.0) == 'cam3'


def test_cam2_part_has_no_crop_camera():
    for t in (CAM1_UNTIL, 1500.0, 1600.0, 1730.0, CAM3_FROM - 0.1):
        assert camera_of(t) is None


def test_every_returned_camera_has_a_detector_crop():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
    import track_review_clip as tracker
    for t in range(0, 2900, 10):
        camera = camera_of(float(t))
        assert camera is None or camera in tracker.PITCH_TOP
