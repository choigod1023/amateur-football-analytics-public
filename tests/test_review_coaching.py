from app.live_feedback import LiveAnalyzer


def test_membership_change_alone_is_not_retreat():
    a = LiveAnalyzer(1)
    a.frames = {0: {'team': [(i, float(i), 0) for i in range(5)]},
                50: {'team': [(i, float(i), 0) for i in range(3)] + [(6, -30., 0)]}}
    evidence = a.retreat_evidence(10)
    assert not evidence['retreat_supported'] and evidence['median_retreat_m'] == 0


def test_correlated_retreat_is_supported_but_too_few_ids_is_not():
    a = LiveAnalyzer(-1)
    a.frames = {0: {'team': [(i, 0., 0) for i in range(3)]},
                50: {'team': [(i, 10., 0) for i in range(3)]}}
    assert a.retreat_evidence(10)['retreat_supported']
    a.frames[50]['team'].pop()
    assert not a.retreat_evidence(10)['retreat_supported']


def test_unsupported_drop_does_not_instruct_team_to_move_forward():
    a = LiveAnalyzer(1)
    a.series['other'] = {s: {'opponent_back_line': 0. if s < 9 else 30.} for s in range(11)}
    alerts = a._check(11., 10)
    drop = next(x for x in alerts if x['kind'] == 'line_drop')
    assert not drop['evidence']['retreat_supported']
    assert '확인되지 않았습니다' in drop['text']
    assert '함께 올리세요' not in drop['text']
    assert drop['polarity'] == 'info' and drop['rules'] == [] and drop['drill'] is None
