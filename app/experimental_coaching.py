"""Cautious space observations from a clearly experimental map only.

This never asserts ball possession, attack direction, roles, weakness, or an
opponent identity. Its output belongs to a separate experimental API field.
"""
import math


def observations(experimental_map):
    if not isinstance(experimental_map, dict) or experimental_map.get('status') != 'reference_unverified':
        return []
    capacity = experimental_map.get('capacity')
    if isinstance(capacity, dict) and (capacity.get('observed_over_limit', 0) or capacity.get('estimated_suppressed', 0)):
        return []
    size = experimental_map.get('field_size_m')
    if (not isinstance(size, (tuple, list)) or len(size) != 2 or
            any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0 for v in size)):
        return []
    entries = experimental_map.get('players')
    if not isinstance(entries, list):
        return []
    by_group = {0: [], 1: []}
    ids = set()
    for p in entries:
        if not isinstance(p, dict) or p.get('kind') not in ('observed', 'estimated'):
            continue
        if p['kind'] == 'estimated':
            age = p.get('age_s')
            if isinstance(age, bool) or not isinstance(age, (int, float)) or not math.isfinite(age) or not 0 < age <= .8:
                continue
        group, x, y, tid = p.get('team_hint'), p.get('x'), p.get('y'), p.get('id')
        if (type(group) is not int or group not in by_group or not isinstance(tid, str) or not tid or tid in ids or
                any(isinstance(v, bool) or not isinstance(v, (float, int)) or not math.isfinite(v) or not 0 <= v <= 1 for v in (x, y))):
            continue
        ids.add(tid)
        by_group[group].append((float(x), float(y), p['kind']))
    if min(len(v) for v in by_group.values()) < 3:
        return []
    output = []
    for group in (0, 1):
        pts = by_group[group]
        spread = (max(p[1] for p in pts)-min(p[1] for p in pts))*size[1]
        estimated = sum(p[2] == 'estimated' for p in pts)
        output.append({
            'observation': f"색상 후보 {'A' if group == 0 else 'B'} {len(pts)}명(그중 단기 예측 {estimated}명)의 가로 범위는 약 {spread:.1f}m입니다.",
            'interpretation': '현재 화면에서 탐지한 사람의 위치 범위이며 팀 전체 대형이나 상대 약점으로 확정할 수 없습니다.',
            'suggestion': '영상에서 같은 색상 선수 사이 공간과 화면 밖 선수의 위치를 함께 확인하세요.',
            'limitations': '영상 전용 실험 보정과 미확인 색상 후보를 사용합니다. 최대 0.8초 예측의 개인별 오차는 확인되지 않았고, 심판 혼입과 탐지 누락도 있을 수 있습니다. 공 소유와 공격 방향은 확인하지 않았습니다.',
        })
    return output
