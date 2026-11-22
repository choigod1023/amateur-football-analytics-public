import threading
from types import SimpleNamespace

import cv2
import numpy as np
import torch
import ultralytics

from app import main
from app.manual_tracks import ManualTracks


def test_explicit_generation_reset_resets_tracker_and_colour_state_in_video_pipeline(tmp_path, monkeypatch):
    path = tmp_path / 'video.mp4'
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*'mp4v'), 10, (160, 100))
    assert writer.isOpened()
    for _ in range(5): writer.write(np.full((100, 160, 3), 60, np.uint8))
    writer.release()
    registry = ManualTracks()
    resets = []
    instances = []

    class FakeModel:
        def __init__(self):
            self.calls = 0
            self.predictor = SimpleNamespace(trackers=[SimpleNamespace(reset=lambda: resets.append('tracker'))])
        def track(self, *args, **kwargs):
            self.calls += 1
            if self.calls == 1: registry.reset()  # asynchronous video boundary
            boxes = SimpleNamespace(id=torch.tensor([7]), xyxy=torch.tensor([[40., 10., 80., 90.]]))
            return [SimpleNamespace(boxes=boxes)]

    class FakeSuggestions:
        def __init__(self): instances.append(self)
        def update(self, frame, tracks): return {str(track_id): 0 for _, track_id in tracks}

    def monitored(factory, name):
        def create():
            item = factory()
            original = item.reset
            def reset():
                resets.append(name)
                original()
            item.reset = reset
            return item
        return create

    monkeypatch.setattr(ultralytics, 'YOLO', lambda *args, **kwargs: FakeModel())
    monkeypatch.setattr(main, 'TeamSuggestions', FakeSuggestions)
    monkeypatch.setattr(main, 'TeamConsensus', monitored(main.TeamConsensus, 'consensus'))
    monkeypatch.setattr(main, 'MovementTracker', monitored(main.MovementTracker, 'movement'))
    monkeypatch.setattr(main, 'FormationObserver', monitored(main.FormationObserver, 'formation'))
    monkeypatch.setattr(main, 'manual_tracks', registry)
    monkeypatch.setattr(main, 'stop_event', threading.Event())
    monkeypatch.setattr(main, 'status', {})
    monkeypatch.setattr(main, 'analysis', {})
    monkeypatch.setattr(main, 'preview', {})
    main.run(str(path), {'suggest_team_clusters': True, 'temporal_team_consensus': True, 'formation_observation': True})
    assert main.status['status'] == 'idle'
    assert resets.count('tracker') == 1
    assert 'consensus' in resets and 'movement' in resets and 'formation' in resets
    assert len(instances) == 2
    # run() invalidates the registry once more when the video ends.
    assert main.analysis['tracking_generation'] == registry.generation()-1


def test_tiled_tracker_reset_is_called_and_suggestions_rebuilt(monkeypatch):
    calls = []
    tiled = SimpleNamespace(reset=lambda: calls.append('tiled'))
    prior = object()
    monkeypatch.setattr(main, 'TeamSuggestions', lambda: 'new-groups')
    result = main.reset_segment_state(tiled, object(), prior, SimpleNamespace(clear=lambda: calls.append('map')))
    assert result == 'new-groups' and calls == ['tiled', 'map']
