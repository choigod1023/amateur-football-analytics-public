import time
import cv2
import numpy as np
from app import main


def test_overlay_is_display_only_and_does_not_change_manual_image():
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    clean = main.publish_preview(frame, time.monotonic(), '2026-01-01T00:00:00Z', [(np.array([20, 20, 50, 70]), 1)])
    marked = main.preview['jpeg']
    clean_image = cv2.imdecode(np.frombuffer(clean, np.uint8), cv2.IMREAD_COLOR)
    marked_image = cv2.imdecode(np.frombuffer(marked, np.uint8), cv2.IMREAD_COLOR)
    assert not frame.any() and not clean_image.any()
    assert marked_image[20:72, 18:52].max() > 100
    assert not marked_image[0:10, 0:10].any()


def test_invalid_boxes_are_not_rendered():
    frame = np.zeros((40, 40, 3), dtype=np.uint8)
    clean = main.publish_preview(frame, time.monotonic(), '2026-01-01T00:00:00Z', [(np.array([np.nan, 0, 20, 20]), 1)])
    assert main.preview['jpeg'] == clean


def test_group_colours_do_not_alter_clean_confirmation_frame():
    frame = np.zeros((100, 160, 3), dtype=np.uint8)
    tracks = [(np.array([20, 20, 60, 70]), 1), (np.array([100, 20, 140, 70]), 2)]
    clean = main.publish_preview(frame, time.monotonic(), '2026-01-01T00:00:00Z', tracks, {'1': 0, '2': 1})
    marked = cv2.imdecode(np.frombuffer(main.preview['jpeg'], np.uint8), cv2.IMREAD_COLOR)
    raw = cv2.imdecode(np.frombuffer(clean, np.uint8), cv2.IMREAD_COLOR)
    assert not raw.any()
    # JPEG compression softens a 1px line, so compare local color sums.
    group_a = marked[18:23, 20:60].sum(axis=(0, 1))
    group_b = marked[18:23, 100:140].sum(axis=(0, 1))
    assert group_a[0] > group_a[2] and group_b[2] > group_b[0]
