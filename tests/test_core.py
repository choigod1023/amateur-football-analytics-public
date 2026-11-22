import time
import cv2
import numpy as np
from fastapi.testclient import TestClient
from app.main import app, classify, project, summarize, validate_config, team_colors
import pytest


def test_empty_api_and_missing_file():
    client = TestClient(app)
    assert client.get('/api/v1/status').json()['status'] == 'idle'
    data = client.get('/api/v1/analysis').json()
    assert data['players'] == [] and data['metrics']['team_width_m'] is None
    assert data['team_colors'] == {'home': None, 'away': None}
    assert client.post('/api/v1/start', json={'source':'missing.mp4'}).status_code == 400


def test_calibration_and_guard():
    cal = {'validated': True, 'image_points': [[0,0],[100,0],[100,100],[0,100]], 'field_points_m': [[0,0],[100,0],[100,50],[0,50]], 'field_size_m':[100,50]}
    validate_config({'calibration': cal})
    assert project((50,50), cal) == (0.5,0.5)
    assert project((101,50), cal) == (None,None)
    assert project((50,50), None) == (None,None)


def test_teams_and_metrics():
    frame = np.zeros((100,100,3), np.uint8); frame[:] = (0,0,255)
    assert classify(frame, (0,0,100,100), {}) == 'unknown'
    assert classify(frame, (0,0,100,100), {'home':[0,255,255], 'away':[120,255,255]}) == 'home'
    players = [dict(id='1',team='home',x=.1,y=.2),dict(id='2',team='home',x=.3,y=.5),dict(id='3',team='unknown',x=0,y=0)]
    metrics, feedback = summarize(players, 'home', [100,50])
    assert metrics == {'team_width_m':15, 'team_length_m':20} and len(feedback) == 1
    assert summarize(players, 'away')[0]['team_width_m'] is None
    assert '홈팀' in feedback[0]['observation']


def test_team_classification_abstains_when_crop_matches_background():
    refs = {'home': [0, 255, 255], 'away': [120, 255, 255]}
    frame = np.zeros((100, 120, 3), dtype=np.uint8)
    frame[:] = (255, 0, 0)  # Blue background, visually ambiguous with away.
    assert classify(frame, (40, 10, 80, 90), refs) == 'unknown'
    frame[10:50, 40:80] = (0, 0, 255)  # Red foreground, blue surroundings.
    assert classify(frame, (40, 10, 80, 90), refs) == 'home'


def test_achromatic_team_and_low_light_abstention():
    refs = {'home': [0, 0, 200], 'away': [120, 255, 200]}
    frame = np.zeros((100, 120, 3), dtype=np.uint8)
    frame[:] = (0, 100, 0)
    frame[10:50, 40:80] = (180, 180, 180)
    assert classify(frame, (40, 10, 80, 90), refs) == 'home'
    frame[10:50, 40:80] = (180, 0, 0)
    assert classify(frame, (40, 10, 80, 90), refs) == 'away'
    frame[10:50, 40:80] = (30, 30, 30)
    assert classify(frame, (40, 10, 80, 90), refs) == 'unknown'
    frame[:] = (180, 180, 180)
    assert classify(frame, (40, 10, 80, 90), refs) == 'unknown'
    frame[:] = (0, 100, 0)
    frame[10:50, 40:80] = (180, 180, 180)
    similar = {'home': [0, 0, 200], 'away': [70, 0, 200]}
    assert classify(frame, (40, 10, 80, 90), similar) == 'unknown'


def test_configured_team_colors():
    refs = {'home':[0,255,255], 'away':[120,255,255]}
    validate_config({'team_hsv':refs})
    assert team_colors(refs) == {'home':'#ff0000', 'away':'#0000ff'}
    assert team_colors({'home':[0,255,255]}) == {'home':'#ff0000', 'away':None}
    with pytest.raises(ValueError):
        validate_config({'team_hsv':{'home':[180,255,255]}})
    with pytest.raises(ValueError):
        validate_config({'team_hsv':{'home':[0.5,255,255]}})
    validate_config({'image_size': 1920})
    validate_config({'own_team': 'away'})
    with pytest.raises(ValueError):
        validate_config({'own_team': 'unknown'})
    assert summarize([dict(id='2', team='away', x=.1, y=.2), dict(id='3', team='away', x=.2, y=.4)], 'away', [100, 50])[0]['team_width_m'] == 10
    with pytest.raises(ValueError):
        validate_config({'image_size': 10000})
