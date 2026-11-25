import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import track_review_clip as tile_detector  # noqa: E402


class Tensor:
    def __init__(self, array):
        self.array = np.array(array, np.float32).reshape(-1, 4) if np.array(array).ndim > 1 else np.array(array, np.float32)

    def cpu(self):
        return self

    def numpy(self):
        return self.array


class Result:
    def __init__(self, boxes, scores):
        self.boxes = type('Boxes', (), {'xyxy': Tensor(boxes), 'conf': Tensor(scores)})()


class FakeModel:
    """Tile passes (imgsz 768) see one person in the middle of the tile; strip passes (imgsz 1024) see one person at a fixed place of the tile, optionally the same one."""

    def __init__(self, strip_box=(20.0, 10.0, 50.0, 90.0), strip_score=0.7):
        self.calls = []
        self.strip_box, self.strip_score = list(strip_box), strip_score

    def predict(self, source, **options):
        self.calls.append((source, options))
        crops = source if isinstance(source, list) else [source]
        if options['imgsz'] == 1024:
            return [Result([self.strip_box], [self.strip_score]) for _ in crops]
        return [Result([[150.0, 100.0, 190.0, 220.0]], [0.8]) for _ in crops]


IMAGE = np.zeros((1080, 1920, 3), np.uint8)


def test_off_by_default_nothing_changes():
    plain, off = FakeModel(), FakeModel()
    a = tile_detector.detect(plain, IMAGE, 'cam1', 0, 0.1)
    b = tile_detector.detect(off, IMAGE, 'cam1', 0, 0.1, far_strip=0.0)
    assert a == b and len(plain.calls) == len(off.calls)
    assert all(options['imgsz'] == 768 for _, options in off.calls)


def test_on_adds_strip_calls_over_the_top_of_the_pitch_part_only():
    model = FakeModel()
    tile_detector.detect(model, IMAGE, 'cam1', 0, 0.1, batch_size=4, far_strip=0.4)
    strip = [(source, options) for source, options in model.calls if options['imgsz'] == 1024]
    assert strip
    top = int(1080 * tile_detector.PITCH_TOP['cam1'])
    band = int((1080 - top) * 0.4)
    crops = [c for source, _ in strip for c in (source if isinstance(source, list) else [source])]
    assert all(c.shape[:2] == (band, 256) for c in crops)
    assert len(crops) == len(tile_detector.starts(1920, 256, 0.25))
    assert all(options['conf'] == 0.1 and options['classes'] == [0] and options.get('quantize') == 32 for _, options in strip)


def test_the_strip_box_is_added_in_frame_coordinates_and_reported():
    info = {}
    found = tile_detector.detect(FakeModel(), IMAGE, 'cam3', 0, 0.1, far_strip=0.4, strip_info=info)
    top = int(1080 * tile_detector.PITCH_TOP['cam3'])
    assert info['strip_only'] and all(d[1] == top + 10 and d[3] == top + 90 for d in info['strip_only'])
    assert all(d in found for d in info['strip_only'])
    base = tile_detector.detect(FakeModel(), IMAGE, 'cam3', 0, 0.1)
    assert len(found) == len(base) + len(info['strip_only'])


def test_a_strip_box_on_top_of_a_better_full_box_is_dropped_and_the_reverse_keeps_the_better_one():
    same_place = (150.0, 100.0, 190.0, 220.0)               # identical to the tile box of a tile that starts at the strip's x (crop origin differs: use a box in image coordinates below)
    top = int(1080 * tile_detector.PITCH_TOP['cam1'])
    base = tile_detector.detect(FakeModel(), IMAGE, 'cam1', 0, 0.1)
    inside = next(d for d in base if d[1] < top + 140)       # a full-frame box in the first row of tiles
    # a strip tile at x = k * 192 shows the same person when the strip box is placed at the same image position
    x0 = max(x for x in tile_detector.starts(1920, 256, 0.25) if x <= inside[0])
    model = FakeModel(strip_box=(inside[0] - x0, inside[1] - top, inside[2] - x0, inside[3] - top), strip_score=0.5)
    info = {}
    found = tile_detector.detect(model, IMAGE, 'cam1', 0, 0.1, far_strip=0.4, strip_info=info)
    assert inside in found                                     # worse strip box dropped, the better full box stays
    assert not any(abs(d[0] - inside[0]) < 1 and abs(d[4] - 0.5) < 1e-6 for d in found)
    better = FakeModel(strip_box=(inside[0] - x0, inside[1] - top, inside[2] - x0, inside[3] - top), strip_score=0.95)
    found = tile_detector.detect(better, IMAGE, 'cam1', 0, 0.1, far_strip=0.4)
    assert inside not in found and any(abs(d[4] - 0.95) < 1e-6 and abs(d[0] - inside[0]) < 1 for d in found)
    assert same_place


def test_batch_size_and_fp16_reach_the_strip_pass():
    one, four = FakeModel(), FakeModel()
    a = tile_detector.detect(one, IMAGE, 'cam1', 0, 0.1, far_strip=0.4)
    b = tile_detector.detect(four, IMAGE, 'cam1', 0, 0.1, batch_size=4, half=True, far_strip=0.4)
    assert a == b
    assert all(options.get('quantize') == 16 for _, options in four.calls)


def test_strip_size_options_reach_the_model():
    model = FakeModel()
    tile_detector.detect(model, IMAGE, 'cam4', 0, 0.1, far_strip=0.25, strip_tile=192, strip_imgsz=1024)
    strip = [source for source, options in model.calls if options['imgsz'] == 1024]
    assert all(s.shape[1] == 192 and s.shape[0] == int((1080 - int(1080 * tile_detector.PITCH_TOP['cam4'])) * 0.25) for s in strip)


def test_wrong_strip_values_are_refused():
    for bad in ({'far_strip': 1.5}, {'far_strip': -0.1}, {'far_strip': True}, {'far_strip': 0.4, 'strip_tile': 10}, {'far_strip': 0.4, 'strip_imgsz': 1000}, {'far_strip': 0.4, 'strip_imgsz': 2048}):
        with pytest.raises(ValueError):
            tile_detector.detect(FakeModel(), IMAGE, 'cam1', 0, 0.1, **bad)


def test_strip_filter_is_off_when_nothing_is_asked():
    assert tile_detector.strip_filter() is None
    with pytest.raises(ValueError):
        tile_detector.strip_filter(min_score=-0.1)


def test_strip_filter_rules():
    keep = tile_detector.strip_filter(min_score=0.25, min_aspect=0.3, drop_seams=True)
    assert keep([100, 10, 120, 40, 0.5], 64, 256, 1920)
    assert not keep([100, 10, 120, 40, 0.2], 64, 256, 1920)           # score
    assert not keep([100, 10, 104, 40, 0.9], 64, 256, 1920)           # thin: 4 wide, 30 high
    assert not keep([65, 10, 90, 40, 0.9], 64, 256, 1920)              # touches the left seam of the tile at x = 64
    assert not keep([280, 10, 319, 40, 0.9], 64, 256, 1920)            # touches the right seam (64 + 256 = 320)
    assert keep([1, 10, 20, 40, 0.9], 0, 256, 1920)                    # the image border is no seam
    assert keep([1700, 10, 1790, 40, 0.9], 1664, 256, 1920)
    assert keep([1700, 10, 1920, 40, 0.9], 1664, 256, 1920)            # the last tile ends at the image border: no seam there


def test_strip_filter_reaches_the_strip_pass_and_changes_only_the_strip_boxes():
    plain, filtered = FakeModel(strip_box=(20.0, 10.0, 24.0, 90.0), strip_score=0.9), FakeModel(strip_box=(20.0, 10.0, 24.0, 90.0), strip_score=0.9)
    base = tile_detector.detect(FakeModel(), IMAGE, 'cam1', 0, 0.1)
    with_thin = tile_detector.detect(plain, IMAGE, 'cam1', 0, 0.1, far_strip=0.4)
    without = tile_detector.detect(filtered, IMAGE, 'cam1', 0, 0.1, far_strip=0.4, strip_keep=tile_detector.strip_filter(min_aspect=0.3))
    assert len(with_thin) > len(base) and without == base                # the thin boxes are gone and the full result is untouched


def test_raw_strip_boxes_are_reported_with_their_tile():
    raw = []
    tile_detector.detect_far_strip(FakeModel(), IMAGE, 'cam1', 0, 0.1, 1, False, 0.4, 256, 1024, raw_out=raw)
    assert raw and all(len(b) == 6 and b[5] in tile_detector.starts(1920, 256, 0.25) for b in raw)
