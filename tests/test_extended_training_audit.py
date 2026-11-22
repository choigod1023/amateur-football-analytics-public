from pathlib import Path
import pytest
from scripts.train_extended_matches import audit


def make_dataset(root):
    (root / 'dataset.yaml').write_text(f"path: '{root.as_posix()}'\ntrain: images/train\nval: images/val\n")
    for split in ('train', 'val'):
        (root / 'images' / split).mkdir(parents=True)
        (root / 'labels' / split).mkdir(parents=True)
    for game, count in [('113',20),('131',20),('103',20),('151',20),('10',20),('106',20),('1',20),('310',10),('781',6),('318',6)]:
        split = 'val' if game == '318' else 'train'
        for n in range(count):
            name = f'game{game}_aihub{game}_{n}' if game in ('310','781') else f'game{game}_{n}'
            (root / 'images' / split / f'{name}.jpg').touch()
            (root / 'labels' / split / f'{name}.txt').touch()


def test_match_split_and_source_name_audit(tmp_path):
    make_dataset(tmp_path)
    assert audit(tmp_path)['train']['frames'] == 156
    image = tmp_path / 'images/train/game310_aihub310_0.jpg'
    image.rename(image.with_name('game310_aihub318_0.jpg'))
    with pytest.raises(ValueError):
        audit(tmp_path)


def test_rejects_missing_label(tmp_path):
    make_dataset(tmp_path)
    (tmp_path / 'labels/val/game318_0.txt').unlink()
    with pytest.raises(ValueError):
        audit(tmp_path)
