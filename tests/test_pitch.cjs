const assert = require('node:assert/strict');
const {prepare, prepareExperimental, calibrationReason, coachingReasons, coachingWarnings} = require('../web/pitch');
assert.deepEqual(prepareExperimental({status:'stale',players:[{id:'1',x:.2,y:.3,kind:'observed',age_s:0}]}),[]);
const exp=prepareExperimental({status:'reference_unverified',players:[{id:'1',x:.2,y:.3,kind:'observed',age_s:0,team_hint:0},{id:'2',x:.3,y:.4,kind:'estimated',age_s:.7,team_hint:1},{id:'3',x:.3,y:.4,kind:'estimated',age_s:3}]});
assert.deepEqual(exp.map(p=>p.id),['1','2']);
assert.deepEqual(prepare(null), {players:[],located:[],missing:0});
const view = prepare([
  {id:'12',team:'home',x:0,y:1},
  {id:'13',team:'away',x:0.5,y:0.25},
  {id:'14',team:'home',x:null,y:0.5},
  {id:'15',team:'away',x:1.01,y:0.5},
  {id:'16',team:'other',x:NaN,y:0.5},
]);
assert.equal(view.players.length, 5);
assert.equal(view.located.length, 2);
assert.equal(view.missing, 3);
assert.equal(view.players[4].team, 'unknown');
assert.deepEqual(view.players[2], {id:'14',team:'home',suggested_color_group:null,x:null,y:null});
const candidates=prepare([{id:'1',team:'unknown',x:null,y:null,suggested_color_group:0},{id:'2',team:'away',x:1,y:1,suggested_color_group:1},{id:'3',team:'unknown',suggested_color_group:'0'}]);
assert.equal(candidates.players[0].team,'unknown');assert.equal(candidates.players[0].suggested_color_group,0);
assert.equal(candidates.players[1].suggested_color_group,1);assert.equal(candidates.players[2].suggested_color_group,null);
assert.match(calibrationReason('resolution_mismatch'), /해상도/);
assert.match(calibrationReason('resolution_unverified'), /기록되지/);
assert.match(calibrationReason('not_validated'), /검증/);
assert.match(calibrationReason('camera_moved'), /구도 변화/);
assert.match(calibrationReason('camera_guard_insufficient'), /단서가 부족/);
assert.match(calibrationReason('missing'), /확인할 수 없습니다/);
assert.match(coachingReasons({coaching_diagnostics:{reasons:['manual_frame_stale']}})[0], /오래되어/);
assert.match(coachingReasons({coaching_diagnostics:{reasons:['manual_confirmation_changed']}})[0], /확인 상태/);
assert.deepEqual(coachingReasons(null), []);
assert.match(coachingReasons({coaching_diagnostics:{reasons:['future_code']}})[0], /해석할 수 없습니다/);
const messages=coachingReasons({calibration_status:'not_configured',coaching_diagnostics:{reasons:['calibration_unavailable','insufficient_located_team_members','calibration_unavailable']}});
assert.equal(messages.length,2);
assert.match(messages[0],/보정이 설정되지/);
assert.match(messages[1],/최소 2명/);
console.log('pitch coordinate and unknown handling passed');

assert.match(calibrationReason('estimated_reference'), /실제 위치 오차는 검증되지/);
const capacityText = '한 팀의 위치 후보가 11명을 초과해 중복·팀 분류 확인이 필요합니다.';
assert.deepEqual(coachingReasons({coaching_diagnostics:{reasons:[capacityText]}}), [capacityText]);
assert.deepEqual(coachingReasons({coaching_diagnostics:{reasons:['team_capacity_exceeded']}}), [capacityText]);
assert.deepEqual(coachingWarnings({coaching_diagnostics:{warnings:[' 검증 필요 ',null,3,'', '검증 필요']}}), ['검증 필요']);
assert.deepEqual(coachingWarnings(null), []);
