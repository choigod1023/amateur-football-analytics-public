from types import SimpleNamespace
import numpy as np
import pytest
from scripts.track_review_clip import detect


class Array:
    def __init__(self, values):
        self.values = np.asarray(values, dtype=np.float32)

    def cpu(self):
        return self

    def numpy(self):
        return self.values


class Detector:
    def __init__(self):
        self.calls = []

    def predict(self, source, **kwargs):
        crops = source if isinstance(source, list) else [source]
        self.calls.append((isinstance(source, list), [c.shape for c in crops], kwargs))
        results = []
        for crop in crops:
            x, y = crop[0, 0, :2]
            # Local observation plus one duplicate seen in adjacent overlap tiles.
            boxes, scores = [[20, 30, 40, 70]], [.7]
            if x <= 330 and x + crop.shape[1] >= 350 and y <= 720 and y + crop.shape[0] >= 760:
                boxes.append([330-x, 720-y, 350-x, 760-y]); scores.append(.9)
            results.append(SimpleNamespace(boxes=SimpleNamespace(xyxy=Array(boxes), conf=Array(scores))))
        return results


def image(h=1080, w=1920):
    y, x = np.indices((h, w), dtype=np.int16)
    return np.stack([x, y, np.zeros_like(x)], axis=-1)


@pytest.mark.parametrize('batch_size', [2, 8, 32])
def test_batch_preserves_offsets_scores_and_overlap_suppression(batch_size):
    frame = image(); single = Detector(); batched = Detector()
    expected = detect(single, frame, 'cam3', 0, .1)
    actual = detect(batched, frame, 'cam3', 0, .1, batch_size=batch_size)
    assert actual == expected
    assert len(single.calls) == 14
    assert len(batched.calls) == (14 + batch_size - 1) // batch_size
    assert all(not c[0] for c in single.calls)
    assert all(c[0] for c in batched.calls)
    assert all(c[2] == single.calls[0][2] for c in batched.calls)
    assert sum(row[:4] == [330, 720, 350, 760] for row in actual) == 1


def test_small_input_keeps_same_letterbox_shape():
    frame = image(400, 250); one = Detector(); many = Detector()
    assert detect(one, frame, 'cam3', 'cpu') == detect(many, frame, 'cam3', 'cpu', batch_size=8)
    assert one.calls[0][1] == many.calls[0][1] == [(200, 250, 3)]


@pytest.mark.parametrize('batch_size', [0, -1, True, 1.5])
def test_invalid_batch_size_is_rejected(batch_size):
    with pytest.raises(ValueError):
        detect(Detector(), image(100, 100), 'cam3', 0, batch_size=batch_size)


def test_missing_batch_result_does_not_silently_drop_a_tile():
    class Broken:
        def predict(self, *args, **kwargs):
            return []
    with pytest.raises(RuntimeError, match='number of tile results'):
        detect(Broken(), image(), 'cam3', 0, batch_size=8)
