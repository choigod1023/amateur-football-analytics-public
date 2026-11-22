import time
import cv2
import numpy as np
from fastapi.testclient import TestClient
from app import main


def test_real_frame_preview_and_staleness():
    client=TestClient(main.app)
    main.stop_event.clear()
    main.set_state(main.status,status='running')
    main.set_state(main.preview,jpeg=None,decoded_monotonic=None,decoded_at=None)
    assert client.get('/api/v1/frame.jpg').status_code==204
    frame=np.full((720,1280,3),(12,87,194),dtype=np.uint8)
    now=time.monotonic()
    main.publish_preview(frame,now,'2026-11-10T00:00:00+00:00')
    response=client.get('/api/v1/frame.jpg')
    assert response.status_code==200 and response.headers['content-type']=='image/jpeg'
    assert response.headers['cache-control']=='no-store' and response.headers['x-frame-timestamp']=='2026-11-10T00:00:00+00:00'
    assert int(response.headers['x-frame-age-ms'])>=0 and len(response.content)<=2*1024*1024
    decoded=cv2.imdecode(np.frombuffer(response.content,dtype=np.uint8),cv2.IMREAD_COLOR)
    assert decoded.shape[:2]==(540,960) and np.max(np.abs(decoded[0,0].astype(int)-frame[0,0].astype(int)))<=3
    main.set_state(main.preview,decoded_monotonic=time.monotonic()-4)
    assert client.get('/api/v1/frame.jpg').status_code==204
    main.set_state(main.status,status='idle')
    main.set_state(main.preview,jpeg=None,decoded_monotonic=None,decoded_at=None)
