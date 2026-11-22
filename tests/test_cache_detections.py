import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'cache_detections.py'
spec = importlib.util.spec_from_file_location('cache_detections', SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_the_stretch_is_cut_into_chunks_and_the_last_one_may_be_shorter():
    assert module.chunk_plan(64, 200, 60) == [(64, 60), (124, 60), (184, 16)]
    assert module.chunk_plan(0, 60, 60) == [(0, 60)]
    assert module.chunk_plan(10, 10, 60) == []


def test_pass_settings_are_parsed_even_with_a_drive_letter_in_the_path():
    assert module.parse_passes(['C:/models/yolo11x.pt:0.05:384', 'yolo11n.pt:0.1:512']) == [('C:/models/yolo11x.pt', 0.05, 384), ('yolo11n.pt', 0.1, 512)]


def test_a_later_pass_only_adds_boxes_that_do_not_overlap_an_earlier_one():
    class Tracker:
        TILE = 384
        detections = {0: [[100, 100, 140, 200, 0.4]], 1: [[102, 102, 142, 202, 0.9], [500, 100, 540, 200, 0.2]]}

        def detect(self, model, image, camera, device, confidence):
            return self.detections[model]
    tracker = Tracker()
    kept = module.detect_passes(tracker, {0: 0, 1: 1}, [(0, 0.05, 384), (1, 0.05, 512)], None, 'cam1')
    assert [(k[1], k[2]) for k in kept] == [(0.4, 0), (0.2, 1)]               # the overlapping box of pass 1 was not added
    assert tracker.TILE == 384
