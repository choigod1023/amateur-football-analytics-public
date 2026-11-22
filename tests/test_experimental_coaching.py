from app.experimental_coaching import observations


def sample():
    return {'status': 'reference_unverified', 'field_size_m': [105, 68], 'players': [
        {'id':str(i), 'team_hint':i//3, 'kind':'observed', 'x':.3, 'y':.2+(i%3)*.2}
        for i in range(6)]}


def test_experimental_observation_labels_short_predictions_and_ignores_old_ones():
    data=sample(); data['players'].append({'id':'ghost','team_hint':1,'kind':'estimated','x':0,'y':1,'age_s':.6})
    data['players'].append({'id':'old','team_hint':1,'kind':'estimated','x':0,'y':0,'age_s':2.})
    result=observations(data)
    assert len(result)==2
    assert '약 27.2m' in result[0]['observation'] and '4명(그중 단기 예측 1명)' in result[1]['observation']
    assert '실험' in result[0]['limitations'] and '확정할 수 없습니다' in result[0]['interpretation']


def test_no_result_for_unknown_basis_duplicate_ids_or_insufficient_points():
    data=sample(); data['status']='active'; assert observations(data)==[]
    data=sample(); data['players'][4]['id']=data['players'][3]['id']; assert observations(data)==[]
    data=sample(); data['players'][0]['x']=float('nan'); assert observations(data)==[]
    data=sample(); data['field_size_m']=[105,0]; assert observations(data)==[]


def test_no_experimental_feedback_when_roster_capacity_hides_candidates():
    data = sample()
    data['capacity'] = {'estimated_suppressed': 1, 'observed_over_limit': 0}
    assert observations(data) == []
    data['capacity'] = {'estimated_suppressed': 0, 'observed_over_limit': 1}
    assert observations(data) == []
    data['capacity'] = {'estimated_suppressed': 0, 'observed_over_limit': 0}
    assert len(observations(data)) == 2
