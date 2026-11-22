import json
import cv2
import numpy as np
import pytest
from scripts.capture_calibration_frame import capture


def test_capture_real_video_without_overwrite(tmp_path):
    source = tmp_path / 'sample.mp4'
    out = tmp_path / 'out'
    out.mkdir()
    writer = cv2.VideoWriter(str(source), cv2.VideoWriter_fourcc(*'mp4v'), 5, (160,90))
    assert writer.isOpened()
    for value in (30,90,150):
        writer.write(np.full((90,160,3), value, np.uint8))
    writer.release()
    image_path, template_path = capture(source, 1, out)
    image = cv2.imread(str(image_path))
    assert image.shape == (90,160,3) and abs(float(image.mean())-90) < 5
    data = json.loads(template_path.read_text(encoding='utf-8'))
    assert data['calibration']['image_size_px'] == [160,90]
    assert data['calibration']['validated'] is False and data['calibration']['image_points'] == []
    before = image_path.read_bytes()
    with pytest.raises(FileExistsError): capture(source, 0, out)
    assert image_path.read_bytes() == before
