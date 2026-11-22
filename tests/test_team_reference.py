import cv2
import numpy as np
import pytest
from app.team_reference import sample_shirt, build_references


def bgr(h,s,v):
    return cv2.cvtColor(np.uint8([[[h,s,v]]]),cv2.COLOR_HSV2BGR)[0,0]


def test_neutral_coloured_and_same_team():
    frame = np.zeros((30,60,3),np.uint8)
    frame[:,:30]=bgr(0,0,175);frame[:,30:]=bgr(110,220,90)
    result=build_references(frame,[1,1,25,25],[35,1,59,25])
    assert result['team_hsv']['home'][1] < 5
    assert abs(result['team_hsv']['away'][0]-110) <= 1
    assert result['team_classification_validated'] is False
    with pytest.raises(ValueError,match='similar'):
        build_references(frame,[1,1,20,20],[2,2,22,22])


def test_hue_wrap_and_mixed():
    frame=np.zeros((20,20,3),np.uint8);frame[:,:10]=bgr(179,255,200);frame[:,10:]=bgr(1,255,200)
    hue=sample_shirt(frame,[0,0,20,20])[0]
    assert min(hue,180-hue)<=1
    frame[:,10:]=bgr(90,255,200)
    with pytest.raises(ValueError,match='hues'):
        sample_shirt(frame,[0,0,20,20])


@pytest.mark.parametrize('rect', [[-1,0,4,4],[0,0,30,4],[0,0,2,5],[0,0,4.2,5]])
def test_invalid_rectangles(rect):
    with pytest.raises(ValueError): sample_shirt(np.zeros((20,20,3),np.uint8),rect)


def test_reject_dark_or_ambiguous():
    frame=np.full((20,20,3),10,np.uint8)
    with pytest.raises(ValueError,match='dark'): sample_shirt(frame,[0,0,20,20])
    frame[:,:10]=bgr(0,0,150);frame[:,10:]=bgr(110,220,150)
    with pytest.raises(ValueError): sample_shirt(frame,[0,0,20,20])
