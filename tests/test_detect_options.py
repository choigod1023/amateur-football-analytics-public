import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import track_review_clip as tile_detector  # noqa: E402


class Tensor:
    def __init__(self, array):
        self.array = np.array(array, np.float32)

    def cpu(self):
        return self

    def numpy(self):
        return self.array


class Result:
    def __init__(self, box, score):
        self.boxes = type('Boxes', (), {'xyxy': Tensor([box]), 'conf': Tensor([score])})()


class FakeModel:
    """One box in the middle of every tile; records how it was called."""

    def __init__(self):
        self.calls = []

    def predict(self, source, **options):
        self.calls.append((source, options))
        crops = source if isinstance(source, list) else [source]
        return [Result([150.0, 100.0, 190.0, 220.0], 0.8) for _ in crops]


IMAGE = np.zeros((1080, 1920, 3), np.uint8)


def test_the_defaults_keep_the_old_call_one_tile_at_a_time_without_fp16():
    model = FakeModel()
    found = tile_detector.detect(model, IMAGE, 'cam1', 0, 0.2)
    assert all(not isinstance(source, list) and 'half' not in options for source, options in model.calls)
    assert all(options['imgsz'] == 768 and options['conf'] == 0.2 and options['classes'] == [0] for _, options in model.calls)
    assert len(model.calls) > 10 and found


def test_a_batch_gives_the_same_boxes_with_fewer_calls():
    one, three = FakeModel(), FakeModel()
    a = tile_detector.detect(one, IMAGE, 'cam3', 0, 0.2)
    b = tile_detector.detect(three, IMAGE, 'cam3', 0, 0.2, batch_size=3)
    assert a == b
    assert len(three.calls) == -(-len(one.calls) // 3) and isinstance(three.calls[0][0], list)


def test_fp16_is_passed_on_only_when_asked():
    model = FakeModel()
    tile_detector.detect(model, IMAGE, 'cam1', 0, 0.2, half=True)
    assert all(options.get('quantize') == 16 for _, options in model.calls)          # ultralytics 8.4: quantize=16 replaces the deprecated half=True


def test_a_wrong_batch_size_is_refused():
    for bad in (0, -1, True, 2.5):
        with pytest.raises(ValueError):
            tile_detector.detect(FakeModel(), IMAGE, 'cam1', 0, 0.2, batch_size=bad)


def test_larger_enlargement_from_the_live_option_reaches_the_model():
    """--detector-imgsz 1024/1280 of scripts/run_live_feedback.py must reach the detector (the 2026-11-20 merge refused every frame)."""
    for size in (768, 1024, 1280):
        model = FakeModel()
        tile_detector.detect(model, IMAGE, 'cam1', 0, 0.2, imgsz=size)
        assert all(options.get('imgsz') == size for _, options in model.calls)


def test_a_wrong_enlargement_is_refused():
    for bad in (100, 1000, 2048, True, 768.0):
        with pytest.raises(ValueError):
            tile_detector.detect(FakeModel(), IMAGE, 'cam1', 0, 0.2, imgsz=bad)
