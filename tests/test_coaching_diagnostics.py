from fastapi.testclient import TestClient
from app.main import app, can_compute_team_metrics, coaching_diagnostics, summarize


def test_no_inputs_reports_missing_requirements_without_synthetic_feedback():
    d = coaching_diagnostics({}, [], 'not_configured', {'team_width_m': None, 'team_length_m': None})
    assert d['state'] == 'blocked'
    assert set(d['reasons']) == {'calibration_unavailable', 'team_references_missing', 'player_roles_unverified',
                                 'team_classification_unverified', 'insufficient_located_team_members'}
    assert 'player_roles_unverified' in d['warnings']


def test_possible_observation_still_warns_person_roles_are_not_known():
    players = [{'team': 'home', 'x': .1, 'y': .2}, {'team': 'home', 'x': .3, 'y': .4}]
    config = {'team_hsv': {'home': [1, 2, 3], 'away': [4, 5, 6]}, 'team_classification_validated': True}
    d = coaching_diagnostics(config, players, 'active', {'team_width_m': 10, 'team_length_m': 20})
    assert d['state'] == 'blocked' and 'player_roles_unverified' in d['reasons']
    assert 'player_roles_unverified' in d['warnings']
    assert 'camera_motion_unchecked' in d['warnings']


def test_manual_confirmation_still_allows_observation_but_guard_has_limits():
    players = [{'team': 'home', 'x': .1, 'y': .2}, {'team': 'home', 'x': .3, 'y': .4}]
    config = {'manual_player_assignments': True, 'calibration': {'camera_guard_reference': 'frame.png'}}
    d = coaching_diagnostics(config, players, 'active', {'team_width_m': 10, 'team_length_m': 20})
    assert d['state'] == 'observation_available' and d['reasons'] == []
    assert 'camera_motion_guard_limited' in d['warnings']


def test_team_colour_validation_alone_cannot_enable_observations():
    people = [{'team': 'home', 'x': .1, 'y': .2}, {'team': 'home', 'x': .3, 'y': .4}]
    for config in ({}, {'team_classification_validated': True}, {'manual_player_assignments': 'true'}):
        field = (100, 50) if can_compute_team_metrics(config) else None
        metrics, feedback = summarize(people, 'home', field)
        assert metrics == {'team_width_m': None, 'team_length_m': None} and feedback == []
    assert can_compute_team_metrics({'manual_player_assignments': True})


def test_original_api_fields_remain_and_new_field_does_not_imply_running():
    data = TestClient(app).get('/api/v1/analysis').json()
    assert {'timestamp', 'players', 'metrics', 'feedback', 'demo'} <= data.keys()
    assert data['coaching_diagnostics']['state'] == 'not_started'
