from app.main import project


def test_tiny_numeric_boundary_deviation_is_clamped_but_outside_is_refused():
    cal = {'validated': True, 'field_size_m': [100., 50.],
           'image_points': [[100., 100.], [1100., 100.], [1100., 600.], [100., 600.]],
           'field_points_m': [[0., 0.], [100., 0.], [100., 50.], [0., 50.]]}
    assert project((100., 350.), cal) == (0., .5)
    assert project((99.995, 350.), cal) == (0., .5)
    assert project((99.98, 350.), cal) == (None, None)
    assert project((float('nan'), 350.), cal) == (None, None)
    # A small pixel deviation that maps to more than 1mm is still rejected.
    large = {**cal, 'field_size_m': [1000., 50.],
             'field_points_m': [[0., 0.], [1000., 0.], [1000., 50.], [0., 50.]]}
    assert project((99.995, 350.), large) == (None, None)
