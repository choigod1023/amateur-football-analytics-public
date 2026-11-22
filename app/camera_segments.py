"""Which camera picture a second of the match video shows (one place for the boundaries).

Measured with scripts/research_camera_segments.py (wiki/calibration-automation.md, 10 s steps, this match only): cam1 from the start to about 1490 s, cam2 from about 1500 s to 1730 s,
cam3 from about 1740 s. The detector tile crop (scripts/track_review_clip.py PITCH_TOP) has a value for cam1 and cam3 only, so the cam2 part and the seconds around the changes give None:
callers that need a crop skip those seconds.
"""
CAM1_UNTIL = 1495.0   # first second that is no longer cam1 (the frames at 1490 s and 1510 s could not be judged: kept out on both sides)
CAM3_FROM = 1735.0    # first second that is cam3 again (cam2 lies in between)


def camera_of(t):
    """Video second -> 'cam1', 'cam3', or None for the cam2 part (no detector crop, no calibration)."""
    if t < CAM1_UNTIL:
        return 'cam1'
    return None if t < CAM3_FROM else 'cam3'
