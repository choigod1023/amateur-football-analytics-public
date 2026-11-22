import cv2
import numpy as np
import pytest
import subprocess
import sys
from pathlib import Path
from app.tracking_motion import BackgroundMotion, cadence_steps, tracker_config, make_tracker, compensate_xyah, alignment_score
from types import SimpleNamespace


def test_translation_and_blank_fallback_and_reset():
    rng = np.random.default_rng(24)
    frame = rng.integers(0, 256, (320, 480, 3), dtype=np.uint8)
    frame = cv2.GaussianBlur(frame, (5, 5), 0)
    camera = BackgroundMotion()
    assert np.allclose(camera.apply(frame), np.eye(2, 3))
    moved = cv2.warpAffine(frame, np.array([[1., 0., 10.], [0., 1., -6.]]), (480, 320))
    result = camera.apply(moved, [[150, 100, 230, 230]])
    assert camera.last['state'] == 'accepted'
    assert np.allclose(result[:, 2], [10, -6], atol=.8)
    assert np.allclose(camera.apply(np.zeros_like(frame)), np.eye(2, 3))
    assert camera.last['state'] == 'rejected'
    camera.reset_params()
    assert camera.previous is None and camera.points is None


def test_all_foreground_is_not_camera_evidence():
    frame = np.random.default_rng(25).integers(0, 256, (240, 320, 3), dtype=np.uint8)
    camera = BackgroundMotion()
    camera.apply(frame, [[0, 0, 320, 240]])
    assert camera.points is None
    assert np.allclose(camera.apply(frame, [[0, 0, 320, 240]]), np.eye(2, 3))


def test_sampling_and_retention_seconds():
    assert cadence_steps(30, 15, 5) == (2, 6)
    assert cadence_steps(30, 5, 5) == (6, 6)
    assert tracker_config(5).track_buffer == 50
    assert tracker_config(15).track_buffer == 150
    with pytest.raises(ValueError):cadence_steps(30, 4, 5)
    with pytest.raises(ValueError):cadence_steps(30, 7, 5)
    with pytest.raises(ValueError):cadence_steps(30, 0, 5)


def test_tracker_actually_calls_camera_hook():
    from ultralytics.engine.results import Boxes
    tracker = make_tracker(15, True)
    frame = np.zeros((100, 100, 3), np.uint8)
    tracker.update(Boxes(np.array([[10, 10, 30, 60, .9, 0]], np.float32), frame.shape[:2]), frame)
    assert tracker.gmc.counts['initialized'] == 1


def test_live_cli_refuses_stale_reviewed_raw_id_links():
    script = Path(__file__).resolve().parents[1] / 'scripts/run_live_feedback_identity.py'
    result = subprocess.run([sys.executable, str(script), 'missing.mp4', 'missing.json', 'cam3',
                             '--direction', '1', '--tracking-fps', '15',
                             '--reviewed-links-store', 'preserve-this-store'], capture_output=True, text=True)
    assert result.returncode == 2
    assert 'Reviewed raw-ID links belong to the old tracking configuration' in result.stderr


def test_xyah_rotation_does_not_mix_aspect_and_height():
    angle = np.deg2rad(1.)
    rotation = np.array([[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]])
    warp = np.column_stack((rotation, [4., 2.]))
    track = SimpleNamespace(mean=np.array([100., 100., .3, 60., 2., 1., .01, .5]), covariance=np.eye(8))
    compensate_xyah([track], warp)
    assert track.mean[2] == pytest.approx(.3)
    assert track.mean[3] == pytest.approx(60.)
    assert track.mean[2] * track.mean[3] == pytest.approx(18.)
    assert np.allclose(track.mean[:2], rotation @ [100, 100] + [4, 2])
    assert np.linalg.eigvalsh(track.covariance).min() >= 0


def test_xyah_zoom_scales_height_once_and_covariance_consistently():
    track = SimpleNamespace(mean=np.array([100., 100., .3, 60., 2., 1., .01, .5]), covariance=np.eye(8))
    compensate_xyah([track], np.array([[1.02, 0., 0.], [0., 1.02, 0.]]))
    assert track.mean[2] == pytest.approx(.3)
    assert track.mean[2] * track.mean[3] == pytest.approx(18.36)
    assert track.covariance[2, 2] == pytest.approx(1.)
    assert track.covariance[3, 3] == pytest.approx(1.02**2)


def test_alignment_evidence_is_one_to_one_not_duplicate_matches():
    box = [10, 10, 30, 60]
    assert alignment_score([box, box, box], [box])[1] == 1
    assert alignment_score([], [box]) == (0., 0)


def test_alignment_guard_rejects_spurious_camera_shift():
    from ultralytics.engine.results import Boxes
    tracker = make_tracker(15, True, alignment_guard=True)
    tracker.frame_id = 2
    state = SimpleNamespace(mean=np.array([20., 30., .3, 60., 0., 0., 0., 0.]), covariance=np.eye(8),
                            xyxy=np.array([11., 0., 29., 60.]), end_frame=1)
    tracker.gmc = SimpleNamespace(last={}, apply=lambda *args: np.array([[1.,0.,100.],[0.,1.,0.]]))
    results = Boxes(np.array([[11.,0.,29.,60.,.9,0.]], np.float32), (200,200))
    tracker._pre_first_associate([state], [], np.zeros((200,200,3),np.uint8), results)
    assert state.mean[0] == 20.
    assert not tracker.gmc.last['applied_to_tracks']
