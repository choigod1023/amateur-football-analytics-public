from app.reconnect_evaluation import audit_join_boundaries


def frame(t, ids, matches):
    return {'time': t, 'aliases': {'raw': {s: s for s in ids}}, 'matches': matches}


def test_confirmation_internal_switch_is_not_counted_correct():
    event = {'time': 1.2, 'birth_time': .8, 'previous_raw': '1', 'raw': '2'}
    frames = [frame(.4, ['1'], [('a', '1')]), frame(.8, ['2'], [('b', '2')]),
              frame(1., ['2'], [('a', '2')]), frame(1.2, ['2'], [('a', '2')])]
    assert audit_join_boundaries([event], frames, [(0, 30)])[0]['boundary_verdict'] == 'wrong'


def test_old_unmatched_endpoint_does_not_reuse_stale_gt():
    event = {'time': 1.2, 'birth_time': .8, 'previous_raw': '1', 'raw': '2'}
    frames = [frame(.2, ['1'], [('a', '1')]), frame(.4, ['1'], []),
              frame(.8, ['2'], [('a', '2')]), frame(1., ['2'], [('a', '2')]),
              frame(1.2, ['2'], [('a', '2')])]
    assert audit_join_boundaries([event], frames, [(0, 30)])[0]['boundary_verdict'] == 'unresolved'


def test_missing_confirmation_is_unresolved_not_correct():
    event = {'time': 1.2, 'birth_time': .8, 'previous_raw': '1', 'raw': '2'}
    frames = [frame(.4, ['1'], [('a', '1')]), frame(.8, ['2'], []),
              frame(1., ['2'], [('a', '2')]), frame(1.2, ['2'], [('a', '2')])]
    assert audit_join_boundaries([event], frames, [(0, 30)])[0]['boundary_verdict'] == 'unresolved'
