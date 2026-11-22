import time
import pytest
from app.experimental_map import ExperimentalMap
from app import main
from app.manual_tracks import ManualTracks


def point(x, ident='1'):
    return {'id': ident, 'x': x, 'y': .4, 'team_hint': 0}


def test_roster_limit_only_suppresses_estimates_and_retains_observed_overflow():
    model = ExperimentalMap(max_players=2)
    model.update([point(.20, 'a'), point(.25, 'b')], 10., [105, 68])
    model.update([point(.201, 'a'), point(.251, 'b')], 10.1, [105, 68])
    result = model.update([point(.4, 'c')], 10.2, [105, 68])
    assert [p['id'] for p in result] == ['c', 'a']
    assert model.capacity == {'observed': 1, 'estimated_suppressed': 1, 'observed_over_limit': 0}
    result = model.update([point(.4, 'c'), point(.5, 'd'), point(.6, 'e')], 10.3, [105, 68])
    assert [p['id'] for p in result] == ['c', 'd', 'e']
    assert model.capacity['observed_over_limit'] == 1
    assert model.capacity['estimated_suppressed'] >= 1


def test_only_previously_observed_id_has_short_lived_prediction():
    model = ExperimentalMap()
    first = model.update([point(.2)], 10., [105, 68])
    assert len(first) == 1 and first[0]['kind'] == 'observed'
    model.update([point(.201)], 10.1, [105, 68])
    predicted = model.update([], 10.3, [105, 68])
    assert len(predicted) == 1 and predicted[0]['kind'] == 'estimated'
    assert predicted[0]['age_s'] == .2 and predicted[0]['uncertainty_m'] is None
    assert predicted[0]['x'] == pytest.approx(.203)
    assert model.update([], 10.4, [105, 68], allow_estimation=False) == []
    assert model.update([], 11., [105, 68]) == []


def test_rejects_unsafe_velocity_duplicates_and_outside():
    model = ExperimentalMap()
    model.update([point(.2)], 1., [105, 68])
    model.update([point(.4)], 1.1, [105, 68])
    assert model.update([], 1.2, [105, 68]) == []
    model.update([point(.2), point(.3)], 2., [105, 68])
    assert model.update([], 2.1, [105, 68]) == []
    model.update([point(.2)], 3., [105, 68])
    model.clear()
    assert model.update([], 3.1, [105, 68]) == []
    model.update([point(.2)], 4., [105, 68])
    model.update([point(.201)], 4.1, [105, 68])
    model.forget({'1'})  # Still visible but outside the valid projection polygon.
    assert model.update([], 4.2, [105, 68]) == []


def test_prediction_cannot_leave_projected_calibration_polygon():
    model = ExperimentalMap()
    model.update([point(.49)], 1., [105, 68])
    model.update([point(.499)], 1.1, [105, 68])
    polygon = [[0,0],[52.5,0],[52.5,68],[0,68]]
    assert model.update([], 1.2, [105, 68], allowed_polygon=polygon) == []


def test_experimental_mode_requires_explicit_unvalidated_reference():
    with pytest.raises(ValueError):
        main.validate_config({'experimental_map': True})
    with pytest.raises(ValueError):
        main.validate_config({'experimental_map': True, 'calibration': {'validated': True}})
    main.validate_config({'experimental_map': False})


def test_stale_or_stopped_map_never_returns_old_points(monkeypatch):
    monkeypatch.setattr(main, 'analysis', {'players': [], 'experimental_map': {'status':'reference_unverified', 'players':[{'id':'1'}]}})
    monkeypatch.setattr(main, 'status', {'status':'idle'})
    monkeypatch.setattr(main, 'manual_mode', False)
    monkeypatch.setattr(main, 'last_analysis_monotonic', time.monotonic())
    assert main.get_analysis()['experimental_map'] == {'status':'stale','players':[]}


def test_playlist_reset_invalidates_previous_estimates_before_next_frame(monkeypatch):
    registry = ManualTracks()
    monkeypatch.setattr(main, 'manual_tracks', registry)
    monkeypatch.setattr(main, 'analysis', {'players': [], 'experimental_map': {'status':'reference_unverified', 'players':[{'id':'1'}]}})
    monkeypatch.setattr(main, 'status', {'status':'running'})
    monkeypatch.setattr(main, 'manual_mode', False)
    monkeypatch.setattr(main, 'last_analysis_monotonic', time.monotonic())
    monkeypatch.setattr(main, 'last_map_generation', registry.generation())
    assert main.get_analysis()['experimental_map']['players']
    registry.reset()
    assert main.get_analysis()['experimental_map'] == {'status':'stale','players':[]}
