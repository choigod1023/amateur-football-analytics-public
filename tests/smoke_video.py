"""Synthetic video tests the plumbing, not football accuracy or live latency."""
import time
from pathlib import Path
import cv2
import numpy as np
import torch
from fastapi.testclient import TestClient
from app.main import app

path = Path('synthetic_test.mp4')
out = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*'mp4v'), 10, (640, 360))
assert out.isOpened()
for i in range(24):
    out.write(np.zeros((360, 640, 3), dtype=np.uint8))
out.release()
try:
    client = TestClient(app)
    if torch.cuda.is_available(): torch.cuda.reset_peak_memory_stats()
    print('START', client.post('/api/v1/start', json={'source':str(path)}).json())
    end = time.monotonic() + 180
    seen = None
    while time.monotonic() < end:
        status = client.get('/api/v1/status').json()
        if status['fps'] is not None: seen = status
        if status['status'] != 'running': break
        time.sleep(.1)
    print('LAST_SAMPLE', seen)
    print('FINAL', status)
    print('ANALYSIS', client.get('/api/v1/analysis').json())
    print('CUDA_PEAK_BYTES', torch.cuda.max_memory_allocated() if torch.cuda.is_available() else None)
    assert status['status'] == 'idle' and status['message'] == 'End of file' and seen
finally:
    path.unlink(missing_ok=True)
