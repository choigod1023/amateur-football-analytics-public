"""Separate position observations from conditional advice; ball state is unknown."""


def fields(kind, facts, fallback):
    limitations = ('영상에서 추정한 선수 위치·팀과 경기장 보정에 근거합니다. 선수 신원·실제 위치 오차, '
                   '공 소유·공격 방향의 정답, 화면 밖 선수와 실제 전술 의도는 검증하지 못했습니다.')
    if kind == 'box_attack':
        observation = f"관측 좌표상 박스 안에 우리 팀으로 분류된 선수가 최소 {facts.get('n', 0)}명 있습니다."
        interpretation = '2초 관측창에서 반복된 배치입니다. 실제 공격이나 크로스 기회인지는 공 위치 확인이 필요합니다.'
        suggestion = '실제 공격 장면이라면 가까운 포스트·먼 포스트·뒤쪽에 지원 위치가 나뉘어 있는지 확인하세요.'
    elif kind == 'gap_wide':
        observation = '최근 5초 구간에서 관측 공격 라인과 수비 라인의 간격이 반복해서 32m를 넘었습니다.'
        interpretation = '팀이 길게 벌어진 후보 장면입니다. 선수 누락이나 팀 오분류로 간격이 커 보일 수 있습니다.'
        suggestion = '영상에서도 간격이 벌어진 것이 맞다면 중원과 수비의 지원 거리를 줄일 수 있는지 확인하세요.'
    elif kind == 'line_drop':
        supported = facts.get('retreat_supported', False)
        observation = ('관측 수비선이 이동했고 공통 추적 ID에서도 후퇴 방향 이동이 나타났습니다.' if supported
                       else '관측 수비선 위치가 바뀌었지만 같은 선수들의 후퇴는 확인되지 않았습니다.')
        interpretation = ('수비 후퇴 후보입니다. 실제 동일인인지, 의도한 후퇴인지는 확인이 필요합니다.' if supported
                          else '선수 누락·팀 분류·라인 구성 변화로 생긴 차이일 수 있습니다.')
        suggestion = ('실제 후퇴라면 중원과 수비 사이 간격을 확인하세요. 라인 이동 방향은 공 위치와 상대 압박을 보고 정하세요.' if supported
                      else '이 장면에서는 라인을 올리거나 내리라는 지시를 보류하고 선수 누락과 팀 구분을 확인하세요.')
    elif kind == 'isolated':
        observation = '관측된 앞선 선수와 가까운 동료 사이 간격이 반복해서 크게 나타났습니다.'
        interpretation = '지원 부족 후보입니다. 같은 선수의 지속 고립이나 화면 밖 동료의 부재를 확인한 것은 아닙니다.'
        suggestion = '실제 지원이 부족한 장면이라면 가까운 동료가 받을 각도와 거리를 조정할 수 있는지 확인하세요.'
    else:
        observation = '관측 궤적에서 수비 라인을 넘어가는 이동 후보가 나타났습니다.'
        interpretation = '침투 후보이며, ID 연결 오류·공 움직임·오프사이드 여부는 확인이 필요합니다.'
        suggestion = '실제 침투가 맞는지 앞뒤 영상을 확인한 뒤 출발 타이밍이나 수비 인계 방법을 검토하세요.'
    directive = coaching_directive(kind, facts, observation)
    suggestion = (f"대상: {directive['target']['label']}. {directive['condition']} "
                  f"행동: {directive['action']} 근거: {directive['rationale']}")
    return dict(observation=observation, interpretation=interpretation,
                suggestion=suggestion, limitations=limitations, directive=directive)


def coaching_directive(kind, facts, observation):
    """Name a conditional group, never turn unverified tracker IDs into people."""
    status = 'conditional'
    condition = '코치가 원본 영상에서 해당 배치와 공 상황을 확인한 경우에만 적용하세요.'
    if kind == 'gap_wide':
        label = '우리 팀 중원과 수비 그룹'
        basis = '팀 종방향 간격 경고에 대응하는 역할 그룹이며 개별 포지션은 자동 확정하지 않았습니다.'
        action = '중원과 수비가 서로 연결되는 지원 거리를 줄이세요. 어느 라인을 움직일지는 공 위치와 상대 압박을 확인해 정하세요.'
    elif kind == 'box_attack':
        label = '우리 팀 박스 안 선수들과 뒤쪽 지원 그룹'
        basis = '관측 좌표상 박스 점유에 대응하는 그룹이며 실제 공격 여부는 미확인입니다.'
        action = '실제 공격 중이면 가까운 포스트·먼 포스트·뒤쪽 지원이 겹치는지 확인하고 받는 각도를 나누세요. 추가 침투는 공 위치를 보고 결정하세요.'
    elif kind == 'isolated':
        label = '우리 팀 앞선 선수 주변의 지원 가능한 동료 그룹'
        basis = '앞선 선수와 관측 동료 사이 간격에 대응하며 동일 선수의 지속 고립은 미검증입니다.'
        action = '실제 지원이 부족하면 가까운 동료가 패스를 받을 각도와 거리를 조정하세요. 화면 밖 동료가 이미 지원하는지도 확인하세요.'
    elif kind == 'line_drop' and facts.get('retreat_supported'):
        label = '우리 팀 중원과 수비 그룹'
        basis = '공통 추적 ID의 후퇴 후보에 대응하며 실제 동일인과 포지션은 미검증입니다.'
        action = '중원과 수비 사이 지원 거리를 확인하고 함께 조정하세요. 라인을 올리거나 내릴 방향은 공 위치와 상대 압박을 보고 정하세요.'
    elif kind == 'line_drop':
        label = '코치·분석 담당자'
        basis = '동일 선수 후퇴 근거가 부족해 선수에게 직접 지시하지 않습니다.'
        action = '선수 누락과 팀 구분을 확인하세요. 라인을 올리거나 내리라는 지시는 보류하세요.'
        condition = '후퇴를 확인하지 못했으므로 전술 지시를 보류합니다.'
        status = 'review_required'
    elif kind == 'run':
        label = '우리 팀 침투 후보 선수와 패스 지원 그룹'
        basis = '수비선 통과 궤적 후보에 대응하며 특정 개인 신원은 미검증입니다.'
        action = '실제 침투라면 패스 가능한 순간과 출발 시점을 앞뒤 영상으로 확인하고 타이밍을 맞추세요. 공 위치 없이 오프사이드나 성공을 단정하지 마세요.'
    elif kind == 'conceded_run':
        label = '우리 팀 수비와 커버 그룹'
        basis = '상대 침투 궤적 후보에 대응하며 가장 가까운 수비수 신원은 미검증입니다.'
        action = '실제 상대 침투라면 누가 추적하고 누가 뒤를 커버할지 서로 확인하세요. 공 위치와 실제 수비 배치를 보고 인계하세요.'
    else:
        label = '코치·분석 담당자'
        basis = '지원하지 않는 알림 유형은 전술 지시로 바꾸지 않습니다.'
        action = '원본 장면과 알림 종류를 확인하세요.'
        condition = '알림 종류를 확인할 때까지 전술 지시를 보류합니다.'
        status = 'review_required'
    return {'target': {'scope': 'staff' if status == 'review_required' else 'group',
                       'label': label, 'track_ids': [], 'selection_basis': basis},
            'action': action, 'rationale': observation, 'condition': condition,
            'status': status, 'individual_assignment_verified': False}
