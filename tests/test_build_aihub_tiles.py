import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'build_aihub_tiles.py'
spec = importlib.util.spec_from_file_location('build_aihub_tiles', SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_boxes_are_scaled_with_the_frame_and_given_in_tile_coordinates():
    width, height, tiles = module.frame_tiles([(600, 400, 40, 120)], 1920, 1080, scale=0.5)
    assert (width, height) == (960, 540)
    holding = [(x, y, rows) for x, y, rows in tiles if rows]
    assert holding
    x, y, rows = holding[0]
    cls, cx, cy, w, h = rows[0]
    assert cls == 0 and abs(cx - (310 - x) / 384) < 1e-9 and abs(cy - (230 - y) / 384) < 1e-9
    assert abs(w - 20 / 384) < 1e-9 and abs(h - 60 / 384) < 1e-9


def test_the_whole_frame_height_is_cut_and_a_box_at_the_top_is_kept():
    _, _, tiles = module.frame_tiles([(100, 5, 40, 100)], 1920, 1080, scale=1.0)
    assert min(y for _, y, _ in tiles) == 0
    assert any(rows for x, y, rows in tiles if y == 0)


def test_tiny_or_clipped_away_boxes_are_dropped():
    _, _, tiles = module.frame_tiles([(100, 100, 6, 40), (1915, 500, 30, 60)], 1920, 1080, scale=0.5)   # 3 px wide after scaling; the second keeps 2.5 px inside the frame
    assert all(not rows for _, _, rows in tiles)


def test_sample_frames_spread_evenly_inside_the_video_and_split_by_match():
    frames = module.sample_frames(20000, 40)
    assert len(frames) == 40 and frames[0] >= 600 and frames[-1] <= 19400 and frames == sorted(frames)
    assert module.part_of(305) == 'test' and module.part_of(318) == 'val' and module.part_of(113) == 'train'
