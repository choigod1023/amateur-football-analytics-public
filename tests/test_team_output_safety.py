import threading
from types import SimpleNamespace

import cv2
import numpy as np
import torch
import ultralytics

from app import main


def test_role_unconfirmed_masks_team_without_mutating_input():
    players = [{'id': '1', 'team': 'home', 'x': .2, 'y': .3},
               {'id': '2', 'team': 'away', 'x': None, 'y': None}]
    output = main.mask_unconfirmed_player_teams(players, {'team_classification_validated': True})
    assert [p['team'] for p in output] == ['unknown', 'unknown']
    assert [p['team'] for p in players] == ['home', 'away']
    assert main.mask_unconfirmed_player_teams(players, {'manual_player_assignments': True}) == players
    assert main.mask_unconfirmed_player_teams(players, {'manual_player_assignments': 'true'})[0]['team'] == 'unknown'


def test_video_pipeline_masks_automatic_color_candidate(tmp_path, monkeypatch):
    path = tmp_path / 'video.mp4'
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*'mp4v'), 10, (160, 100))
    assert writer.isOpened()
    for _ in range(3):
        writer.write(np.full((100, 160, 3), 60, np.uint8))
    writer.release()

    class FakeModel:
        def track(self, *args, **kwargs):
            boxes = SimpleNamespace(id=torch.tensor([7]), xyxy=torch.tensor([[40., 10., 80., 90.]]))
            return [SimpleNamespace(boxes=boxes)]

    class FakeSuggestions:
        def update(self, frame, tracks):
            return {str(track_id): 0 for _, track_id in tracks}

    monkeypatch.setattr(ultralytics, 'YOLO', lambda *args, **kwargs: FakeModel())
    monkeypatch.setattr(main, 'classify', lambda *args, **kwargs: 'home')
    monkeypatch.setattr(main, 'TeamSuggestions', FakeSuggestions)
    monkeypatch.setattr(main, 'stop_event', threading.Event())
    monkeypatch.setattr(main, 'status', {})
    monkeypatch.setattr(main, 'analysis', {})
    monkeypatch.setattr(main, 'preview', {})
    main.run(str(path), {'team_classification_validated': True, 'suggest_team_clusters': True})
    assert main.status['status'] == 'idle'
    assert main.analysis['players'][0]['team'] == 'unknown'
    assert main.analysis['players'][0]['suggested_color_group'] == 0
    assert main.analysis['feedback'] == []
