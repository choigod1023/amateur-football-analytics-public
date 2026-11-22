import numpy as np
import torch
from app.tiled_tracking import TiledPlayerTracker


class FakeModel:
    def __init__(self): self.confs=[]
    def predict(self, image, **kwargs):
        self.confs.append(kwargs['conf'])
        return [type('Result', (), {'boxes':None})()]


def test_optional_low_score_recovery_preserves_track_birth_threshold():
    model=FakeModel()
    tracker=TiledPlayerTracker(model,'cpu',640,.35,low_score_recovery=True)
    assert tracker.tracker.args.track_high_thresh==.35
    assert tracker.tracker.args.new_track_thresh==.35
    assert tracker.detector_confidence==.1
    assert tracker.update(np.zeros((640,640,3),dtype=np.uint8))==[]
    assert model.confs==[.1]


def test_default_keeps_existing_detector_threshold():
    model=FakeModel()
    tracker=TiledPlayerTracker(model,'cpu',640,.35)
    tracker.update(np.zeros((640,640,3),dtype=np.uint8))
    assert model.confs==[.35]


def test_weak_detection_recovers_existing_track_but_does_not_create_one():
    class Frames:
        def __init__(self, scores): self.scores=iter(scores)
        def predict(self, image, **kwargs):
            score=next(self.scores)
            boxes=type('Boxes', (), {'xyxy':torch.tensor([[100.,100.,140.,200.]]), 'conf':torch.tensor([score])})()
            return [type('Result', (), {'boxes':boxes})()]
    frame=np.zeros((640,640,3),dtype=np.uint8)
    weak_only=TiledPlayerTracker(Frames([.2]),'cpu',640,.35,low_score_recovery=True)
    assert weak_only.update(frame)==[]
    sequence=TiledPlayerTracker(Frames([.9,.2]),'cpu',640,.35,low_score_recovery=True)
    first=sequence.update(frame); second=sequence.update(frame)
    assert len(first)==len(second)==1 and first[0][1]==second[0][1]
