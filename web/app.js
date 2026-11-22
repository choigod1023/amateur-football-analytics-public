const $ = id => document.getElementById(id);
const state = { timer: null, frameTimer: null, generation: 1 };
const freshness = new TimestampWatch();
const frameFreshness = new TimestampWatch(5000);
let frameExpiryTimer = null;
let replayPolling = false, pitchAnimation = null;
const pitchMotion = new MinimapMotion();
const matchRoster = new MatchRoster();
let rosterSample={time:0,generation:0};
let motionExperimental = [];
let teamSettings = {mode:'auto',home:TeamColors.defaults.home,away:TeamColors.defaults.away};
try {
  const v = JSON.parse(localStorage.getItem('touchline-team-colors') || '{}');
  if (v.mode === 'manual' && TeamColors.normalize(v.home) && TeamColors.normalize(v.away)) teamSettings = {mode:'manual',home:TeamColors.normalize(v.home),away:TeamColors.normalize(v.away)};
} catch (_) {}
let serverColors = null, currentColors = TeamColors.resolveColors(teamSettings, serverColors), lastPlayers = [], calibrationStatus = null, lastExperimental = null;
const clean = value => typeof value === 'string' ? value : '';
const metric = value => typeof value === 'number' && Number.isFinite(value) ? value.toFixed(1) : '—';
const set = (id, value) => { $(id).textContent = value; };

function paintPitch(located, experimental) {
  const c = $('pitch'), x = c.getContext('2d'), w = c.width, h = c.height;
  x.fillStyle = '#263e2b'; x.fillRect(0, 0, w, h);
  for (let i = 0; i < 8; i++) { if (i % 2 === 0) { x.fillStyle = '#29442f'; x.fillRect(i*w/8,0,w/8,h); } }
  x.strokeStyle = '#8ca688'; x.lineWidth = 2; x.globalAlpha = 0.7;
  x.strokeRect(27, 25, w-54, h-50); x.beginPath(); x.moveTo(w/2,25); x.lineTo(w/2,h-25); x.stroke();
  x.beginPath(); x.arc(w/2,h/2,56,0,Math.PI*2); x.stroke();
  x.strokeRect(27,h/2-100,95,200); x.strokeRect(w-122,h/2-100,95,200);
  x.strokeRect(27,h/2-48,35,96); x.strokeRect(w-62,h/2-48,35,96); x.globalAlpha = 1;
  let drawn = 0;
  for (const p of located) {
    const px = 27 + p.x*(w-54), py = 25 + p.y*(h-50);
    const color = p.team === 'home' ? currentColors.home : p.team === 'away' ? currentColors.away : '#a4b2a5';
    const held = ['last_seen','predicted'].includes(p.display_kind);
    if (p.display_kind === 'predicted') {
      x.globalAlpha=p.display_opacity;
      x.beginPath(); x.ellipse(px,py,p.uncertainty_m/89*(w-54),p.uncertainty_m/60*(h-50),0,0,Math.PI*2);
      x.strokeStyle=color; x.setLineDash([2,4]); x.stroke(); x.setLineDash([]);
    }
    x.beginPath(); x.arc(px,py,11,0,Math.PI*2); x.fillStyle = color; if (!held) x.fill();
    if (held && x.setLineDash) x.setLineDash([3,3]);
    x.strokeStyle = '#ffffff'; x.lineWidth = 2; x.stroke();
    if (x.setLineDash) x.setLineDash([]);
    x.font = 'bold 12px sans-serif'; x.textAlign='center'; x.textBaseline='middle';
    x.fillStyle = held ? '#fff' : TeamColors.foreground(color); x.fillText(p.id.length <= 4 ? p.id : p.id.slice(-4), px, py + 0.5); x.globalAlpha=1; drawn++;
  }
  for (const p of experimental) {
    const px = 27+p.x*(w-54), py = 25+p.y*(h-50);
    const color = p.team_hint === 0 ? '#3cb4ff' : p.team_hint === 1 ? '#ff6950' : '#a4b2a5';
    x.beginPath(); x.arc(px,py,11,0,Math.PI*2); x.fillStyle=color;
    if (p.kind === 'observed') x.fill();
    x.strokeStyle='#fff'; x.lineWidth=2;
    if (p.kind === 'estimated' && x.setLineDash) x.setLineDash([3,3]);
    x.stroke(); if (x.setLineDash) x.setLineDash([]);
    x.font='bold 12px sans-serif'; x.textAlign='center'; x.textBaseline='middle';
    x.fillStyle=p.kind === 'estimated' ? '#fff' : TeamColors.foreground(color);
    x.fillText(p.id.length <= 4 ? p.id : p.id.slice(-4), px, py+0.5); drawn++;
  }
}

function renderRoster(shown) {
  const model=matchRoster.update(lastPlayers,shown,rosterSample.time,rosterSample.generation);
  const box=$('match-roster');box.replaceChildren();
  const note=document.createElement('p');note.className='pitch-detail';
  note.textContent='11대11 가정 · 골키퍼 포함 · 슬롯은 선수 신원 확정이 아닙니다. 위치 미확인은 경기장에 임의로 찍지 않습니다.';box.append(note);
  const names={observed:'관측',predicted:'예상',last_seen:'마지막 위치',unlocated:'위치 미확인',identity_uncertain:'팀·ID 확인 필요'};
  for(const team of ['home','away']) {
    const title=document.createElement('p');title.className='pitch-detail';title.textContent=(team==='home'?'A/홈':'B/상대')+' · 11개 슬롯';box.append(title);
    const list=document.createElement('div');list.className='roster-grid';
    for(const slot of model.teams[team]) {
      const item=document.createElement('span');item.className='roster-slot roster-'+slot.status;
      item.textContent=slot.slot+' · '+names[slot.status];
      item.title=slot.track_id===null?'아직 대응한 추적 ID 없음':'임시 추적 ID '+slot.track_id+' · 동일인 미검증';list.append(item);
    }
    box.append(list);
  }
  if(model.pending.length){const p=document.createElement('p');p.className='pitch-detail';p.textContent='슬롯 대응 보류 '+model.pending.length+'개 탐지: 새 ID·팀 변경·중복 가능성을 확인해야 합니다. 원본 탐지는 별도 목록에 유지합니다.';box.append(p);}
}

function animatePitch(now) {
  const shown=pitchMotion.at(now);
  paintPitch(shown, motionExperimental);
  renderRoster(shown);
  pitchAnimation = pitchMotion.active(now) ? requestAnimationFrame(animatePitch) : null;
}

function drawPitch(players = [], sample = null) {
  lastPlayers = players;
  if(sample)rosterSample=sample;
  const view = PitchData.prepare(players);
  const experimental = view.located.length ? [] : PitchData.prepareExperimental(lastExperimental);
  motionExperimental = experimental;
  if (sample) pitchMotion.push(view.located, sample.time, performance.now(), sample.generation,
    ['active','estimated_reference'].includes(calibrationStatus), view.players.filter(p=>p.x === null).map(p=>p.id));
  else if (!view.located.length) pitchMotion.reset();
  const display = sample || pitchMotion.hasData() ? pitchMotion.at(performance.now()) : view.located;
  paintPitch(display, experimental);
  renderRoster(display);
  if (pitchMotion.active(performance.now()) && pitchAnimation === null) pitchAnimation = requestAnimationFrame(animatePitch);
  const held = display.filter(p=>['last_seen','predicted'].includes(p.display_kind)).length;
  const drawn = display.length + experimental.length;
  $('pitch-empty').hidden = drawn > 0;
  set('pitch-state', experimental.length ? '실험 위치 후보' : drawn ? `${drawn-held}명 관측 · ${held}명 예상·마지막 위치` : view.players.length ? '위치 없음' : '데이터 없음');
  set('pitch-empty', view.players.length ? '위치를 표시할 수 없습니다' : '아직 표시할 선수 위치가 없습니다');
  set('pitch-detail', view.players.length || held
    ? `탐지 ${view.players.length}명 · 관측 위치 ${drawn-held}명 · 예상·마지막 위치 ${held}명 · 위치 미확인 ${view.missing}명${view.missing ? ' — ' + PitchData.calibrationReason(calibrationStatus) : ''}`
    : '선수 탐지 결과를 기다립니다. 위치는 검증된 고정 카메라 보정이 필요합니다.');
  if (drawn && !experimental.length) $('pitch-detail').textContent += ' · 화면 이동은 최대 0.2초 보간. 빈 원은 최대 0.8초 단기 예상 또는 마지막 위치입니다. 범위 원은 시간에 따라 커지는 참고 범위이며 보장된 오차가 아닙니다. 실제 관측·코칭 계산에 포함하지 않습니다.';
  if (experimental.length) {
    const observed=experimental.filter(p=>p.kind === 'observed').length, estimated=experimental.length-observed;
    const cap=lastExperimental?.capacity;
    const suppressed=Number.isInteger(cap?.estimated_suppressed) && cap.estimated_suppressed>0 ? ` · 22명 가정으로 예상 ${cap.estimated_suppressed}개 숨김` : '';
    const excess=Number.isInteger(cap?.observed_over_limit) && cap.observed_over_limit>0 ? ` · 관측 후보 ${cap.observed_over_limit}개 초과(심판·중복 가능)` : '';
    set('pitch-detail', `실험 후보 · 화면 관측 ${observed}명 · 단기 예상 ${estimated}명(점선)${suppressed}${excess}. 제공된 고정 카메라 기준점과 경기장 크기 가정; 실제 선수 위치 오차 미검증이며 확정 지표·코칭이 아닌 별도 실험 관찰에만 사용됩니다.`);
  }
  const unknown = view.players.filter(p => p.team === 'unknown').length;
  const hintCount=view.players.filter(p=>p.suggested_color_group!==null).length;
  set('team-review-reason', unknown ? `미분류 ${unknown}명 · ${hintCount ? `그중 ${hintCount}명의 A/B 색상 후보가 표시됩니다. 후보는 팀·역할 확정이 아니며 심판도 포함될 수 있습니다.` : '소속이 확인되지 않은 사람입니다.'}` : view.players.length ? '팀 표시는 서버에서 받은 값입니다. 역할과 소속의 확인 상태를 따로 확인하세요.' : '탐지 결과가 오면 팀 확인 상태가 표시됩니다.');
  const list=$('pitch-players'); list.replaceChildren();
  const experimentalById=new Map(experimental.map(p=>[p.id,p]));
  for (const p of view.players.slice(0, 100)) {
    const li=document.createElement('li');
    const team=p.team === 'home' ? '홈팀' : p.team === 'away' ? '어웨이팀' : '미분류';
    const hint=p.team === 'unknown' && p.suggested_color_group !== null ? ` · 색상 후보 ${p.suggested_color_group === 0 ? 'A' : 'B'} (미확인)` : '';
    const candidate=experimentalById.get(p.id);
    const position=p.x !== null ? `위치 ${(p.x*100).toFixed(1)}%, ${(p.y*100).toFixed(1)}%` : candidate ? '실험 위치 후보 · 오차 미검증' : '위치 미확인';
    li.textContent=`추적 ID ${p.id} · ${team}${hint} · ${position}`;
    list.append(li);
  }
  for (const p of experimental.filter(p=>p.kind === 'estimated')) {
    const li=document.createElement('li'); li.textContent=`추적 ID ${p.id} · 단기 예상 · 마지막 관측 ${p.age_s}초 전 · 위치 오차 미검증`; list.append(li);
  }
  $('pitch-player-list').hidden = view.players.length === 0;
  if (view.players.length > 100) {
    const li=document.createElement('li'); li.textContent='목록은 처음 100명까지만 표시합니다.'; list.append(li);
  }
}

function updateTeamColors() {
  currentColors = TeamColors.resolveColors(teamSettings, serverColors);
  $('home-dot').style.backgroundColor = currentColors.home;
  $('away-dot').style.backgroundColor = currentColors.away;
  const labels = {manual:'수동 표시색 · 팀 소속 판별과 별개',server:'서버 제공 표시색',default:'기본 표시색 · 유니폼 색 미확인'};
  set('team-color-status', labels[currentColors.source] + (currentColors.similar ? ' · 색상이 비슷해 구별이 어려울 수 있어요' : ''));
  drawPitch(lastPlayers);
}

function clearData() {
  lastExperimental = null;
  renderExperimentalFeedback([]);
  for (const id of ['width','length','fps','latency']) set(id, '—');
  drawPitch();
  const box = $('feedback'); box.className = 'empty-block'; box.replaceChildren();
  const icon = document.createElement('span'); icon.className='spark'; icon.textContent='✳';
  const wrap = document.createElement('div'), title = document.createElement('strong'), desc = document.createElement('p');
  title.textContent='아직 도착한 피드백이 없어요'; desc.textContent='분석 서버에 연결되면 관찰과 제안을 이곳에 표시합니다.';
  wrap.append(title, desc); box.append(icon, wrap);
}

function renderExperimentalFeedback(items) {
  const box = $('experimental-feedback');
  if (!box) return;
  box.replaceChildren();
  const entries = Array.isArray(items) ? items.slice(0, 2) : [];
  box.hidden = !entries.length;
  if (!entries.length) return;
  const title=document.createElement('strong');
  title.textContent='실험 공간 관찰 · 팀과 위치 미검증'; box.append(title);
  for (const item of entries) {
    if (!item || typeof item !== 'object') continue;
    const article=document.createElement('article');
    for (const [name,key] of [['관찰','observation'],['해석','interpretation'],['제안','suggestion'],['한계','limitations']]) {
      if (!clean(item[key])) continue;
      const p=document.createElement('p'), label=document.createElement('b'); label.textContent=name+'  ';
      p.append(label,document.createTextNode(item[key])); article.append(p);
    }
    box.append(article);
  }
}

function renderFeedback(items, demo) {
  if (!items.length) return;
  const box = $('feedback'); box.className = 'feedback-list'; box.replaceChildren();
  if (demo) { const warning=document.createElement('p'); warning.textContent='데모 데이터 · 실제 경기 분석이 아닙니다'; box.append(warning); }
  for (const item of items.slice(0, 5)) {
    if (!item || typeof item !== 'object') continue;
    const article=document.createElement('article');
    for (const [name,key] of [['관찰','observation'],['해석','interpretation'],['제안','suggestion'],['한계','limitations']]) {
      if (!clean(item[key])) continue;
      const p=document.createElement('p'), b=document.createElement('b'); b.textContent=name+'  '; p.append(b,document.createTextNode(item[key])); article.append(p);
    }
    box.append(article);
  }
}

function renderNoFeedback(data) {
  const box = $('feedback'); box.className = 'empty-block'; box.replaceChildren();
  const wrap = document.createElement('div'), title = document.createElement('strong');
  const observing = data?.coaching_diagnostics?.state === 'observing' && Array.isArray(data.coaching_diagnostics.reasons) && !data.coaching_diagnostics.reasons.length;
  title.textContent = observing ? '최근 표시할 전술 알림이 없습니다' : '현재 표시할 코칭이 없습니다'; wrap.append(title);
  const reasons = PitchData.coachingReasons(data);
  const people = PitchData.prepare(data?.players).players;
  const unknown = people.filter(p => p.team === 'unknown').length;
  if (unknown) reasons.push(`추적된 ${unknown}명의 소속이 미확인입니다. 수동 확인을 지원하는 연결에서 필드 선수와 팀을 확인해 주세요.`);
  if (reasons.length) {
    const list = document.createElement('ul');
    for (const reason of reasons) { const li=document.createElement('li'); li.textContent=reason; list.append(li); }
    wrap.append(list);
  } else {
    const p=document.createElement('p'); p.textContent=observing ? '현재 응답에 전술 알림이 없습니다. 분석 정확도나 경기 상황에 문제가 없다는 뜻은 아닙니다.' : '서버에서 아직 피드백이나 상세 보류 사유를 제공하지 않았습니다.'; wrap.append(p);
  }
  const warnings = PitchData.coachingWarnings(data);
  if (data?.calibration_status === 'estimated_reference') warnings.push(PitchData.calibrationReason(data.calibration_status));
  for (const warning of new Set(warnings)) {
    const p=document.createElement('p'); p.textContent=warning; wrap.append(p);
  }
  const note = document.createElement('p'); note.textContent='화면 밖 선수와 추적 ID 변경은 자동으로 모두 확인할 수 없습니다.'; wrap.append(note);
  box.append(wrap);
}

async function read(kind) {
  const controller=new AbortController(), timeout=setTimeout(()=>controller.abort(),5000);
  try {
    const response=await fetch('/api/v1/' + kind,{cache:'no-store',signal:controller.signal});
    if (!response.ok) throw new Error('connection failed');
    return await response.json();
  } finally { clearTimeout(timeout); }
}
async function refresh(gen) {
  if (gen !== state.generation) return;
  try {
    const [status, data] = await Promise.all([read('status'),read('analysis')]);
    if (gen !== state.generation) return;
    replayPolling = status?.replay === true;
    if (!status || typeof status !== 'object' || !data || typeof data !== 'object' || !['running','idle','error'].includes(status.status)) throw new Error('invalid response');
    set('source-label', status.replay ? '녹화 영상 재생 시험 · SRT 라이브 아님' : status.input_mode === 'file' ? '현재 입력: 업로드 영상' : status.input_mode === 'live' ? '현재 입력: SRT' : '입력 상태 확인 중');
    if (status.status !== 'running') {
      $('state').classList.remove('live'); $('state').innerHTML='<i></i>' + (status.status === 'error' ? '서버 분석 오류' : '서버 대기 중');
      freshness.reset(); serverColors=null; calibrationStatus=null; clearData(); updateTeamColors(); set('updated',status.status === 'error' ? '분석 오류 · 서버 상태를 확인하세요' : (status.input_mode === 'file' && status.message === 'End of file' ? '업로드 영상 분석 완료' : '서버 연결됨 · 분석 대기 중'));
      if (status.message) set('updated', clean(status.message));
      if (gen === state.generation) state.timer=setTimeout(()=>refresh(gen),2500);
      return;
    }
    $('state').classList.add('live'); $('state').innerHTML='<i></i>서버 연결됨';
    const freshnessState=freshness.check(data.timestamp, Date.now());
    if (freshnessState !== 'updating') {
      $('state').classList.remove('live'); $('state').innerHTML=freshnessState === 'stale' ? '<i></i>분석 갱신 중단' : '<i></i>분석 시각 대기 중';
      serverColors=null; calibrationStatus=null; clearData(); updateTeamColors(); set('updated',freshnessState === 'stale' ? '분석 시각이 10초 이상 바뀌지 않아 이전 결과를 숨겼습니다.' : '유효한 분석 시각을 기다리고 있습니다.');
      if (gen === state.generation) state.timer=setTimeout(()=>refresh(gen),2500);
      return;
    }
    set('fps',metric(status.fps)); set('latency',metric(status.latency_ms));
    const ownLabel=data.own_team === 'home' ? '홈팀' : data.own_team === 'away' ? '어웨이팀' : '지정 팀';
    set('width-label',`${ownLabel} 관측 폭`); set('length-label',`${ownLabel} 관측 길이`);
    set('width',metric(data.metrics?.team_width_m)); set('length',metric(data.metrics?.team_length_m));
    const players=Array.isArray(data.players)?data.players:[]; serverColors=data.team_colors; calibrationStatus=data.calibration_status; lastExperimental=data.experimental_map || null; updateTeamColors(); drawPitch(players, {time: Number.isFinite(data.source_time_s) ? data.source_time_s*1000 : Date.parse(data.timestamp), generation: data.stream_generation ?? state.generation});
    const recoveredIds = new Set(Array.isArray(data.recovered_player_ids) ? data.recovered_player_ids.map(String) : []);
    if (recoveredIds.size) {
      $('pitch-detail').textContent += ` · 약한 실제 탐지로 ${recoveredIds.size}명 보충(코칭 계산 제외)`;
      for (const item of $('pitch-players').children) {
        const id = item.textContent.match(/^추적 ID (\S+) /)?.[1];
        if (recoveredIds.has(id)) item.textContent += ' · 약한 탐지 보충 · 신원 미검증';
      }
    }
    const feedback=Array.isArray(data.feedback)?data.feedback:[];
    if (feedback.length) renderFeedback(feedback,data.demo===true); else renderNoFeedback(data);
    renderExperimentalFeedback(data.experimental_feedback);
    set('updated',data.demo === true ? '데모 데이터 · 실제 분석 아님' : (clean(data.timestamp) ? `서버 데이터 시간: ${data.timestamp}` : '분석 시각 없음 · 최신 여부 확인 불가'));
  } catch (_) {
    if (gen !== state.generation) return;
    $('state').classList.remove('live'); $('state').innerHTML='<i></i>서버 연결 안 됨';
    freshness.reset(); serverColors=null; calibrationStatus=null; clearData(); updateTeamColors(); set('updated','서버 응답 없음 · 연결 상태를 확인하세요');
  }
  if (gen === state.generation) state.timer=setTimeout(()=>refresh(gen),(replayPolling || ['active','estimated_reference'].includes(calibrationStatus)) ? 200 : lastExperimental?.status === 'reference_unverified' ? 500 : 2500);
}
function clearFrame(message='서버 영상을 기다리고 있어요') {
  clearTimeout(frameExpiryTimer); frameExpiryTimer=null;
  const img=$('frame-preview'); img.hidden=true; img.removeAttribute('src');
  document.querySelector('.placeholder').hidden=false;
  document.querySelector('.placeholder strong').textContent=message;
  document.querySelector('.placeholder p').textContent='서버 영상의 준비 상태를 확인하세요.';
}
async function refreshFrame(gen) {
  if (gen !== state.generation) return;
  if (globalThis.localVideoActive) { state.frameTimer=setTimeout(()=>refreshFrame(gen),1000); return; }
  const controller=new AbortController(), timeout=setTimeout(()=>controller.abort(),5000);
  const started=performance.now();
  try {
    const response=await fetch('/api/v1/frame.jpg',{cache:'no-store',signal:controller.signal});
    if (gen !== state.generation) return;
    if (!response.ok || response.status === 204 || !(response.headers.get('content-type') || '').toLowerCase().startsWith('image/jpeg')) throw new Error('frame unavailable');
    const blob=await response.blob();
    if (gen !== state.generation) return;
    if (globalThis.localVideoActive) return;
    if (!blob.size || blob.size>2000000) throw new Error('invalid frame');
    const frameTime=response.headers.get('X-Frame-Timestamp') || '';
    const ageHeader=response.headers.get('X-Frame-Age-Ms');
    const frameAge=Number(ageHeader)+(performance.now()-started);
    if (!frameTime || !Number.isFinite(Date.parse(frameTime)) || ageHeader === null || !ageHeader.trim() || !Number.isFinite(frameAge) || frameAge < 0 || frameAge >= 3000) throw new Error('stale frame');
    if (frameFreshness.check(frameTime,Date.now()) === 'stale') { clearFrame('영상 프레임 갱신이 중단됐어요'); set('video-state','갱신 중단'); }
    else {
      const next=await new Promise((resolve,reject)=>{
        const reader=new FileReader();
        reader.onload=()=>resolve(reader.result);
        reader.onerror=()=>reject(new Error('frame decode failed'));
        reader.readAsDataURL(blob);
      });
      if (gen !== state.generation || globalThis.localVideoActive) return;
      if (Number(ageHeader) + (performance.now() - started) >= 3000) throw new Error('stale frame');
      const img=$('frame-preview'); img.src=next; img.hidden=false; document.querySelector('.placeholder').hidden=true;
      clearTimeout(frameExpiryTimer);
      frameExpiryTimer=setTimeout(()=>{ if (!globalThis.localVideoActive) { clearFrame('영상 프레임 갱신이 중단됐어요'); set('video-state','갱신 중단'); } },Math.max(0,3000-frameAge));
      set('video-state', frameTime ? '수신 중' : '시각 미제공');
      set('video-info',frameTime ? `서버 프레임: ${frameTime}` : '프레임 시각 없음 · 최신 여부 확인 불가');
    }
  } catch (_) {
    if (gen !== state.generation) return;
    frameFreshness.reset(); clearFrame(); set('video-state','영상 없음'); set('video-info','영상 또는 연결을 확인하세요');
  } finally {
    clearTimeout(timeout);
    if (gen === state.generation) state.frameTimer=setTimeout(()=>refreshFrame(gen),125);
  }
}
$('upload-form').addEventListener('submit',event=>{
  event.preventDefault();
  const file=$('upload-file').files[0];
  if (!file || !/\.mp4$/i.test(file.name)) { set('upload-message','MP4 파일을 선택해 주세요.'); return; }
  if (!file.size || file.size>256*1024*1024) { set('upload-message','파일 크기는 256MiB 이하여야 합니다.'); return; }
  const xhr=new XMLHttpRequest();
  const upload=$('upload-button'), live=$('live-button'), progress=$('upload-progress');
  upload.disabled=true; live.disabled=true; progress.hidden=false; progress.value=0;
  set('upload-message','업로드 중입니다.');
  xhr.open('POST','/api/v1/upload');
  xhr.timeout=300000;
  xhr.setRequestHeader('Content-Type','video/mp4');
  xhr.upload.onprogress=e=>{ if(e.lengthComputable) { progress.value=Math.min(100,Math.round(e.loaded/e.total*100)); set('upload-message',`업로드 중 ${progress.value}%`); } };
  xhr.onload=()=>{
    if(xhr.status===200) { progress.value=100; set('upload-message','업로드를 마쳤습니다. 영상 분석을 시작합니다.'); }
    else if(xhr.status===413) set('upload-message','파일이 크기 또는 저장 공간 제한을 초과했습니다.');
    else if(xhr.status===415) set('upload-message','재생할 수 있는 MP4 파일인지 확인해 주세요.');
    else if(xhr.status===409) set('upload-message','다른 업로드가 진행 중이거나 현재 영상을 종료하고 있습니다.');
    else set('upload-message','업로드 또는 분석 시작에 실패했습니다. 서버 상태를 확인해 주세요.');
  };
  xhr.onerror=()=>set('upload-message','네트워크 오류로 업로드하지 못했습니다.');
  xhr.ontimeout=()=>set('upload-message','업로드 시간이 초과됐습니다.');
  xhr.onloadend=()=>{ upload.disabled=false; live.disabled=false; };
  xhr.send(file);
});
$('live-button').addEventListener('click',async()=>{
  const upload=$('upload-button'),live=$('live-button'); upload.disabled=true;live.disabled=true;
  set('upload-message','SRT 입력으로 전환 중입니다.');
  try {
    const r=await fetch('/api/v1/live',{method:'POST',cache:'no-store'});
    if (!r.ok) throw new Error('switch failed');
    set('upload-message','SRT 입력으로 전환했습니다. 송출을 기다립니다.');
  } catch (_) { set('upload-message','SRT 전환에 실패했습니다. 서버 상태를 확인해 주세요.'); }
  finally {upload.disabled=false;live.disabled=false;}
});
$('team-settings-open').addEventListener('click',()=>{
  $('team-color-mode').value=teamSettings.mode;
  $('home-color').value=teamSettings.mode === 'manual' ? teamSettings.home : currentColors.home;
  $('away-color').value=teamSettings.mode === 'manual' ? teamSettings.away : currentColors.away;
  updateTeamColorControls(); $('team-settings').showModal();
});
function updateTeamColorControls() {
  const manual=$('team-color-mode').value === 'manual';
  $('home-color').disabled=!manual; $('away-color').disabled=!manual;
  set('team-color-warning', manual && TeamColors.similar($('home-color').value,$('away-color').value) ? '선택한 두 색상이 비슷해 구별하기 어려울 수 있습니다.' : '');
}
for (const id of ['team-color-mode','home-color','away-color']) $(id).addEventListener('input',updateTeamColorControls);
$('team-settings-form').addEventListener('submit',e=>{
  if (e.submitter?.value === 'cancel') return;
  e.preventDefault();
  const mode=$('team-color-mode').value,home=TeamColors.normalize($('home-color').value),away=TeamColors.normalize($('away-color').value);
  if (!['auto','manual'].includes(mode) || (mode === 'manual' && (!home || !away))) return;
  teamSettings={mode,home:home || TeamColors.defaults.home,away:away || TeamColors.defaults.away};
  try { localStorage.setItem('touchline-team-colors',JSON.stringify(teamSettings)); } catch (_) {}
  $('team-settings').close(); updateTeamColors();
});
clearData(); updateTeamColors(); set('video-info','프레임 미리보기 · 초당 최대 약 8장 · 분석과 시점 차이 가능'); refresh(state.generation); refreshFrame(state.generation);
