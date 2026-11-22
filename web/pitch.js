(function (root) {
  // API coordinates are normalized field coordinates, not image pixels.
  const valid = value => typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 1;
  function prepare(input) {
    if (!Array.isArray(input)) return {players: [], located: [], missing: 0};
    const players = input.filter(p => p && typeof p === 'object').map(p => ({
      id: typeof p.id === 'string' && p.id ? p.id.slice(0, 80) : '?',
      team: p.team === 'home' || p.team === 'away' ? p.team : 'unknown',
      suggested_color_group: p.suggested_color_group === 0 || p.suggested_color_group === 1 ? p.suggested_color_group : null,
      x: valid(p.x) && valid(p.y) ? p.x : null,
      y: valid(p.x) && valid(p.y) ? p.y : null,
    }));
    const located = players.filter(p => p.x !== null);
    return {players, located, missing: players.length - located.length};
  }
  function calibrationReason(status) {
    const labels = {
      estimated_reference: '저장된 기준점과 추정 경기장 크기로 보정했습니다. 실제 위치 오차는 검증되지 않았습니다.',
      not_configured: '경기장 보정이 설정되지 않았습니다.',
      not_validated: '경기장 보정이 아직 검증되지 않았습니다.',
      resolution_unverified: '보정 영상의 해상도가 기록되지 않았습니다.',
      resolution_mismatch: '현재 영상의 해상도가 보정한 영상과 다릅니다.',
      camera_reference_unavailable: '카메라 비교 기준 영상을 사용할 수 없습니다.',
      camera_guard_insufficient: '카메라 구도가 유지되는지 확인할 단서가 부족합니다.',
      camera_moved: '카메라 구도 변화가 감지되어 위치를 보류합니다.',
      active: '일부 선수는 보정된 영역 밖이거나 위치를 확인할 수 없습니다.'
    };
    return labels[status] || '보정 상태나 선수 위치를 확인할 수 없습니다.';
  }
  function prepareExperimental(input) {
    if (!input || input.status !== 'reference_unverified' || !Array.isArray(input.players)) return [];
    return input.players.filter(p => p && typeof p.id === 'string' && valid(p.x) && valid(p.y) &&
      (p.kind === 'observed' || p.kind === 'estimated') && typeof p.age_s === 'number' &&
      Number.isFinite(p.age_s) && p.age_s >= 0 && (p.kind === 'observed' ? p.age_s === 0 : p.age_s <= 0.8))
      .map(p => ({id:p.id.slice(0,80),x:p.x,y:p.y,kind:p.kind,age_s:p.age_s,team_hint:p.team_hint === 0 || p.team_hint === 1 ? p.team_hint : null})).slice(0,100);
  }
  function coachingReasons(data) {
    const diag = data && typeof data.coaching_diagnostics === 'object' ? data.coaching_diagnostics : null;
    if (!diag || !Array.isArray(diag.reasons)) return [];
    const labels = {
      team_capacity_exceeded: '한 팀의 위치 후보가 11명을 초과해 중복·팀 분류 확인이 필요합니다.',
      calibration_unavailable: calibrationReason(data.calibration_status),
      player_roles_unverified: '탐지된 사람이 필드 선수인지 확인되지 않았습니다.',
      team_references_missing: '두 팀의 유니폼 기준색이 준비되지 않았습니다.',
      team_classification_unverified: '팀 분류가 아직 검증되지 않았습니다.',
      manual_frame_stale: '최근 분석 화면이 오래되어 팀과 코칭을 잠시 보류합니다.',
      manual_confirmation_changed: '선수 확인 상태가 바뀌어 이전 팀과 코칭을 보류합니다.',
      insufficient_located_team_members: '지정 팀에서 소속과 위치가 확인된 선수가 최소 2명 필요합니다.'
    };
    return [...new Set(diag.reasons.map(key => Object.hasOwn(labels, key) ? labels[key] :
      typeof key === 'string' && /[가-힣]/.test(key) ? key.slice(0, 500) : '서버가 제공한 일부 보류 사유를 해석할 수 없습니다.'))];
  }
  function coachingWarnings(data) {
    const warnings = data?.coaching_diagnostics?.warnings;
    return Array.isArray(warnings) ? [...new Set(warnings.filter(value => typeof value === 'string' && value.trim()).map(value => value.trim().slice(0, 500)))] : [];
  }
  const api = {prepare, prepareExperimental, calibrationReason, coachingReasons, coachingWarnings};
  if (typeof module !== 'undefined' && module.exports) module.exports = api; else root.PitchData = api;
})(typeof window !== 'undefined' ? window : globalThis);
