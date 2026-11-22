from app.ball_path import link_ball_path


def test_a_smooth_confident_track_is_found_among_distractors():
    frames = [[(100 + 10 * t, 300, 0.9), (800, 200 + 200 * (t % 2), 0.6)] for t in range(6)]
    picks = link_ball_path(frames)
    assert [picks[t][:2] for t in range(6)] == [(100 + 10 * t, 300) for t in range(6)]


def test_weak_scores_give_no_answer_instead_of_a_guess():
    frames = [[(100 + 10 * t, 300, 0.3)] for t in range(8)]
    assert link_ball_path(frames) == {}


def test_a_short_chain_and_empty_frames_are_not_trusted():
    assert link_ball_path([[], [], []]) == {}
    assert link_ball_path([[(10, 10, 0.95)], [(20, 10, 0.95)], [], [], [], []]) == {}


def test_a_chain_survives_a_one_frame_gap_but_not_a_teleport():
    frames = [[(100, 300, 0.9)], [(110, 300, 0.9)], [], [(130, 300, 0.9)], [(140, 300, 0.9)]]
    assert sorted(link_ball_path(frames)) == [0, 1, 3, 4]
    far = [[(100, 300, 0.9)], [(110, 300, 0.9)], [(120, 300, 0.9)], [(1500, 900, 0.9)], [(1510, 900, 0.9)], [(1520, 900, 0.9)]]
    picks = link_ball_path(far)
    assert picks[2][0] == 120 and picks[3][0] == 1500        # two separate chains, no jump inside one


def test_v2_keeps_a_smooth_chain_and_drops_an_unconfident_one():
    from app.ball_path import link_ball_path_v2
    smooth = [[(100 + 10 * t, 200, 0.95)] for t in range(6)]
    assert sorted(link_ball_path_v2(smooth)) == list(range(6))
    weak = [[(100 + 10 * t, 200, 0.6)] for t in range(6)]
    assert link_ball_path_v2(weak) == {}


def test_v2_penalises_a_zigzag_more_than_v1():
    from app.ball_path import link_ball_path_v2, STRICT
    zigzag = [[(100 + 10 * t, 200 + (60 if t % 2 else 0), 0.92)] for t in range(8)]
    assert len(link_ball_path_v2(zigzag, **STRICT)) <= len(link_ball_path_v2(zigzag, accel=0.0))
