import cv2
import numpy as np
from scripts.evaluate_labeled_srt import mark, decode


def test_marker_survives_jpeg_and_preserves_sky_outside_marker():
    source=np.full((200,1200,3),[100,120,140],dtype=np.uint8)
    marked=mark(source,731)
    assert decode(marked)==731 and np.array_equal(marked[100:,:,:],source[100:,:,:])
    ok, jpeg=cv2.imencode('.jpg',marked,[cv2.IMWRITE_JPEG_QUALITY,65]);assert ok
    decoded=cv2.imdecode(jpeg,cv2.IMREAD_COLOR)
    assert decode(decoded)==731


def test_unknown_marker_is_not_interpreted():
    assert decode(np.full((200,1200,3),127,np.uint8)) is None


def test_one_corrupted_bit_is_rejected():
    marked=mark(np.full((200,1200,3),128,np.uint8),431)
    marked[4:59,0:60] = 255-marked[4:59,0:60]
    assert decode(marked) is None
