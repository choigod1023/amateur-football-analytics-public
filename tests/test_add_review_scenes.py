import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'add_review_scenes.py'
spec = importlib.util.spec_from_file_location('add_review_scenes', SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

SEGMENTS = [{'source': 'a.mp4', 'cut_start_sec': 0, 'source_offset_sec': 376}, {'source': 'b.mp4', 'cut_start_sec': 226, 'source_offset_sec': 0}]


def test_a_time_in_the_cut_maps_to_the_right_recording_and_offset():
    assert module.source_of(SEGMENTS, 100) == ('a.mp4', 476)
    assert module.source_of(SEGMENTS, 226) == ('b.mp4', 0)
    assert module.source_of(SEGMENTS, 300.5) == ('b.mp4', 74.5)


def test_the_registration_of_a_scene_composes_the_reference_and_the_shift():
    assert module.registration([1, 0, -7.41, 5.61], (0, 0)) == [1, 0, -7.41, 5.61]
    assert module.registration([1, 0, -7.0, 5.0], (2, -3)) == [1, 0, -9.0, 8.0]
