from scripts.evaluate_wide_tracking import match


def test_one_to_one_iou_matching_does_not_count_duplicates():
    gt = [('a', [0,0,10,10]), ('b', [20,0,30,10])]
    preds = [([0,0,10,10], 1), ([0,0,10,10], 2), ([20,0,30,10], 3), ([50,50,60,60], 4)]
    result = match(gt, preds)
    assert len(result) == 2
    assert dict(result)['b'] == '3'


def test_unmatched_people_are_not_invented():
    assert match([('a', [0,0,10,10])], [([50,50,60,60], 1)]) == []


def test_subsampled_video_and_recovery_setting_are_combined(monkeypatch):
    import numpy as np
    from scripts import evaluate_wide_tracking as audit
    seen = []
    class Capture:
        def __init__(self, path): self.index = 0
        def set(self, prop, value): self.index = int(value)
        def read(self):
            value = self.index; self.index += 1
            return True, np.full((1, 1, 3), value, dtype=np.uint8)
        def grab(self): self.index += 1; return True
        def release(self): pass
    class Tracker:
        def __init__(self, model, device, size, confidence, low_score_recovery=False):
            assert low_score_recovery is True
        def update(self, image):
            seen.append(int(image[0, 0, 0]))
            return [([0, 0, 10, 10], 1)]
    monkeypatch.setattr(audit.cv2, 'VideoCapture', Capture)
    monkeypatch.setattr(audit, 'load_labels', lambda path: {i: [('p', [0,0,10,10])] for i in range(6)})
    monkeypatch.setattr(audit, 'YOLO', lambda path: object())
    monkeypatch.setattr(audit, 'TiledPlayerTracker', Tracker)
    result = audit.evaluate('v', 'l', 'w', 0, 3, 'cpu', 'tiled', .35, True, 2, 1)
    assert seen == [0, 2, 4]
    assert result['processed_frames'] == result['frames'] == result['matched'] == 3
