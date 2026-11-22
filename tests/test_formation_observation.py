from app.formation_observation import FormationObserver, observation_feedback


def players(y, ids=('1','2','3')):
    return [dict(id=pid, team='home', x=.1+i*.1, y=value) for i,(pid,value) in enumerate(zip(ids,y))]


def test_observation_uses_same_people_and_real_units():
    o=FormationObserver()
    assert not o.update(players([.2,.3,.4]), 'home', 0, (100,50), validated=True)
    out=o.update(players([.1,.3,.5]), 'home', 2, (100,50), validated=True)
    assert out == [dict(metric='team_width_m', previous_m=10.,current_m=20.,change_m=10.,interval_s=2.,observed_players=3)]
    assert '화면 밖' in observation_feedback(out[0])['limitations']


def test_missing_or_changed_ids_and_invalid_timeline_reset():
    o=FormationObserver()
    assert not o.update(players([.2,.3,.4]), 'home', 0, (100,50), validated=True)
    assert not o.update(players([.1,.3,.5], ('1','2','4')), 'home', 2, (100,50), validated=True)
    assert not o.update(players([.1,.3,.5]), 'home', 4, (100,50), validated=False)
    assert not o.update(players([.1,.3,.5]), 'home', None, (100,50), validated=True)
    assert not o.update(players([.1,.3,.5]), 'home', 5, (100,50), validated=True)
    assert not o.update(players([.1,.3,.5]), 'home', 4, (100,50), validated=True)


def test_unknown_position_and_duplicate_ids_do_not_generate_change():
    o=FormationObserver();o.update(players([.2,.3,.4]), 'home', 0, (100,50), validated=True)
    bad=players([.1,.3,.5]);bad[0]['x']=None
    assert not o.update(bad, 'home', 2, (100,50), validated=True)
    o.update(players([.2,.3,.4]), 'home', 3, (100,50), validated=True)
    assert not o.update(players([.1,.3,.5], ('1','1','3')), 'home', 5, (100,50), validated=True)


def test_new_and_departing_tracks_do_not_distort_shared_extents():
    o = FormationObserver()
    before = players([.2, .3, .4, .9], ('1', '2', '3', '4'))
    after = players([.1, .3, .5, 0.0], ('1', '2', '3', '5'))
    assert not o.update(before, 'home', 0, (100, 50), validated=True)
    out = o.update(after, 'home', 2, (100, 50), validated=True)
    assert out == [dict(metric='team_width_m', previous_m=10., current_m=20.,
                        change_m=10., interval_s=2., observed_players=3)]


def test_disappeared_track_cannot_reenter_same_interval():
    o = FormationObserver()
    o.update(players([.2, .3, .4, .5], ('1', '2', '3', '4')), 'home', 0, (100, 50), validated=True)
    o.update(players([.2, .3, .4], ('1', '2', '3')), 'home', .5, (100, 50), validated=True)
    # ID 4 reappears at an extreme location but is excluded from this interval.
    out = o.update(players([.2, .3, .4, .99], ('1', '2', '3', '4')), 'home', 1, (100, 50), validated=True)
    assert out == []
