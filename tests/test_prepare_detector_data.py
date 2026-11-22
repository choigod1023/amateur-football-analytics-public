import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'prepare_detector_data.py'
spec = importlib.util.spec_from_file_location('prepare_detector_data', SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_a_box_appears_in_every_tile_that_shows_most_of_it_with_tile_coordinates():
    tiles = module.tile_boxes([(300, 600, 340, 680)], 1920, 1080, tile=384, stride=192, top=0.45)
    holding = [(x, y, rows) for x, y, rows in tiles if rows]
    assert holding and all(x <= 300 and x + 384 >= 340 for x, _, _ in holding)
    x, y, rows = holding[0]
    cls, cx, cy, w, h = rows[0]
    assert cls == 0 and abs(cx - (320 - x) / 384) < 1e-9 and abs(h - 80 / 384) < 1e-9


def test_a_box_cut_by_the_tile_edge_is_kept_only_when_half_of_it_is_inside():
    tiles = {(x, y): rows for x, y, rows in module.tile_boxes([(370, 600, 450, 680)], 1920, 1080, tile=384, stride=384, top=0.45)}
    inside = [rows for (x, y), rows in tiles.items() if x == 0 and rows]
    assert inside == []                                    # only 14 of 80 px lie in the first tile
    assert any(rows for (x, y), rows in tiles.items() if x == 384)


def test_a_tile_with_an_unclear_person_is_dropped_instead_of_taught_as_background():
    kept = module.tile_boxes([], 1920, 1080, tile=384, stride=384, top=0.45, skip_boxes=[(100, 600, 140, 680)])
    assert all(not (x <= 100 < x + 384 and y <= 600 < y + 384) for x, y, _ in kept)
    assert len(kept) < len(module.tile_boxes([], 1920, 1080, tile=384, stride=384, top=0.45))
