import math
import statistics

import pytest

from app.foot_stability import FootStabilizer


def box(x=100., y=200., height=30.):
    return [x-8, y-height, x+8, y]


def test_stationary_jitter_reduces_without_changing_box_size_or_emitting_missing():
    f = FootStabilizer()
    raw, filtered = [], []
    for i in range(30):
        y = 200.+(2. if i%2 else -2.)
        out=f.update(i*.2,1,box(y=y))
        raw.append(y);filtered.append(out['foot'][1])
        assert out['box'][2]-out['box'][0] == pytest.approx(16.)
        assert out['box'][3]-out['box'][1] == pytest.approx(30.)
        assert out['pixel_shift'] <= 3.+1e-9
        assert not out['extrapolated']
    assert statistics.pstdev(filtered[3:]) < .65*statistics.pstdev(raw[3:])
    assert set(f.previous)=={'1'}


def test_constant_motion_has_small_bounded_lag_not_a_stationary_stick():
    f=FootStabilizer()
    outputs=[f.update(i*.2,1,box(x=100+i*2)) for i in range(20)]
    assert all(a['foot'][0]<b['foot'][0] for a,b in zip(outputs,outputs[1:]))
    lag=138-outputs[-1]['foot'][0]
    assert 0 < lag < 1.1  # 10px/s: under 110ms equivalent lag.


@pytest.mark.parametrize('changed,reason',[(box(x=140),'large_observed_displacement'),
                                          (box(height=50),'box_shape_changed')])
def test_discontinuity_is_not_smoothed(changed,reason):
    f=FootStabilizer();f.update(0,1,box())
    out=f.update(.2,1,changed)
    assert out['box']==changed and out['reason']==reason
    assert out['pixel_shift']==0


def test_missing_time_identity_rewind_and_overlap_reset():
    f=FootStabilizer();f.update(0,1,box());f.update(.2,1,box(y=202))
    assert f.update(1,1,box(y=203))['pixel_shift']==0
    assert f.update(1.2,2,box(y=204))['pixel_shift']==0
    assert f.update(1.3,2,box(y=205),ambiguous=True)['pixel_shift']==0
    assert f.update(1.4,2,box(y=206))['pixel_shift']==0
    assert f.update(.1,2,box(y=207))['pixel_shift']==0


def test_invalid_input_and_nearby_boxes_are_not_smoothed():
    f=FootStabilizer();f.update(0,1,box())
    with pytest.raises(ValueError):f.update(.2,1,[0,0,math.nan,20])
    assert '1' not in f.previous
    near=box(height=100)
    assert f.update(.4,1,near)['box']==near
    assert f.update(.6,1,box(height=100,y=202))['pixel_shift']==0
