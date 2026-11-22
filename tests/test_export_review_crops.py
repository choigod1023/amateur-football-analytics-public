import json

import cv2
import numpy as np
import pytest

from scripts.export_review_crops import export


def test_export_explicit_roles_without_duplicate_or_full_frame_labels(tmp_path):
    labels = tmp_path / 'labels'
    labels.mkdir()
    cv2.imwrite(str(labels / 'image.jpg'), np.full((40, 60, 3), 120, np.uint8))
    for index, role in enumerate(('player', 'spectator', 'shadow', 'duplicate', 'unknown')):
        (labels / f'{index}.json').write_text(json.dumps({'role':role, 'image':'image.jpg',
            'bbox_image_norm':[.1,.1,.6,.8], 'source_provenance':{'match':'one'}}), encoding='utf-8')
    result = export(labels, tmp_path / 'export')
    manifest = json.loads((tmp_path / 'export' / 'manifest.json').read_text(encoding='utf-8'))
    assert result['exported'] == 3
    assert {r['role'] for r in manifest['items']} == {'player','spectator','shadow'}
    assert all(r['split'] == 'unassigned' and r['source_provenance']['match'] == 'one' for r in manifest['items'])
    assert result['skipped'] == {'duplicate':1,'unknown':1}
    assert not list((tmp_path / 'export').glob('*.txt'))
    assert all(cv2.imread(str(tmp_path / 'export' / r['crop'])) is not None for r in manifest['items'])


def test_reject_existing_output_and_skip_unsafe_image(tmp_path):
    labels = tmp_path / 'labels'
    labels.mkdir()
    (labels / 'unsafe.json').write_text(json.dumps({'role':'player','image':'../secret.jpg',
        'bbox_image_norm':[0,0,1,1]}), encoding='utf-8')
    assert export(labels, tmp_path / 'out')['skipped'] == {'invalid':1}
    with pytest.raises(ValueError):
        export(labels, tmp_path / 'out')
    with pytest.raises(ValueError):
        export(labels, labels / 'nested')
