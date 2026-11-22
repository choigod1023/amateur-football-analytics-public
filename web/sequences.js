// Saved review clips contain no synchronized analysis until the server supplies it.
(function () {
  const el = id => document.getElementById(id);
  const safeId = value => typeof value === 'string' && /^[0-9a-f]{32}$/i.test(value);
  const number = value => typeof value === 'number' && Number.isFinite(value) ? value.toFixed(1) : '—';
  let items = [], selected = null;

  function drawScenePitch(players, colors) {
    const view = PitchData.prepare(players), canvas = el('sequence-pitch'), ctx = canvas.getContext('2d');
    const w = canvas.width, h = canvas.height;
    ctx.fillStyle = '#263e2b'; ctx.fillRect(0, 0, w, h);
    ctx.strokeStyle = '#8ca688'; ctx.lineWidth = 2; ctx.globalAlpha = .7;
    ctx.strokeRect(27, 25, w-54, h-50); ctx.beginPath(); ctx.moveTo(w/2,25); ctx.lineTo(w/2,h-25); ctx.stroke();
    ctx.beginPath(); ctx.arc(w/2,h/2,56,0,Math.PI*2); ctx.stroke();
    ctx.strokeRect(27,h/2-100,95,200); ctx.strokeRect(w-122,h/2-100,95,200); ctx.globalAlpha = 1;
    for (const p of view.located) {
      const px = 27 + p.x*(w-54), py = 25 + p.y*(h-50);
      const color = p.team === 'home' ? colors.home : p.team === 'away' ? colors.away : '#a4b2a5';
      ctx.beginPath(); ctx.arc(px,py,11,0,Math.PI*2); ctx.fillStyle=color; ctx.fill();
      ctx.strokeStyle='#fff'; ctx.lineWidth=2; ctx.stroke();
      ctx.font='bold 12px sans-serif'; ctx.textAlign='center'; ctx.textBaseline='middle'; ctx.fillStyle=TeamColors.foreground(color);
      ctx.fillText(p.id.length <= 4 ? p.id : p.id.slice(-4),px,py+.5);
    }
    el('sequence-pitch-note').textContent = view.located.length
      ? `확인된 위치 ${view.located.length}명 · 위치 미확인 ${view.missing}명`
      : '이 장면에 저장된 검증된 선수 위치가 없어 표시하지 않습니다.';
  }

  function show(item) {
    selected = item.id;
    el('sequence-detail').hidden = false;
    el('sequence-detail-title').textContent = `${number(item.start_s)}초 ~ ${number(item.end_s)}초`;
    const video = el('sequence-video');
    if (item.status === 'ready') {
      const url = '/api/v1/sequences/' + encodeURIComponent(item.id) + '/video';
      if (video.getAttribute('src') !== url) { video.src = url; video.load(); }
      video.hidden = false;
    } else { video.pause(); video.removeAttribute('src'); video.load(); video.hidden = true; }
    const snapshot = el('sequence-snapshot');
    if (item.snapshot_available === true && Number.isFinite(item.snapshot_source_time_s) && Number.isFinite(item.snapshot_offset_s)) {
      snapshot.src = '/api/v1/sequences/' + encodeURIComponent(item.id) + '/snapshot.jpg';
      snapshot.hidden = false;
      el('sequence-snapshot-note').textContent = `아래 분석은 원본 약 ${number(item.snapshot_source_time_s)}초의 실제 프레임 한 장 기준입니다. 클립과의 시간은 약 ${number(item.snapshot_offset_s)}초이며 재생 영상과 자동 동기화되지 않습니다.`;
    } else {
      snapshot.hidden = true; snapshot.removeAttribute('src');
      el('sequence-snapshot-note').textContent = '저장된 분석 프레임이 없습니다.';
    }
    const colors = TeamColors.resolveColors(teamSettings, item.team_colors);
    drawScenePitch(item.players, colors);
    el('sequence-metrics').textContent = `관측 폭 ${number(item.metrics?.team_width_m)}m · 관측 길이 ${number(item.metrics?.team_length_m)}m`;
    const feedback = el('sequence-feedback'); feedback.replaceChildren();
    const entries = Array.isArray(item.feedback) ? item.feedback : [];
    if (!entries.length) feedback.textContent = '이 장면에 저장된 코칭 결과가 없습니다.';
    for (const entry of entries.slice(0, 5)) {
      if (!entry || typeof entry !== 'object') continue;
      const article = document.createElement('article');
      for (const [label, key] of [['관찰','observation'],['해석','interpretation'],['제안','suggestion'],['한계','limitations']]) {
        if (typeof entry[key] !== 'string' || !entry[key]) continue;
        const p = document.createElement('p'), b = document.createElement('b'); b.textContent = label + ' '; p.append(b,document.createTextNode(entry[key])); article.append(p);
      }
      feedback.append(article);
    }
    el('sequence-limitations').textContent = typeof item.limitations === 'string' && item.limitations ? item.limitations : '저장된 분석의 확인 범위가 제공되지 않았습니다.';
    for (const button of el('sequence-list').querySelectorAll('button')) button.setAttribute('aria-pressed', String(button.dataset.id === selected));
  }

  function hideDetail() {
    selected = null; el('sequence-detail').hidden = true;
    const video = el('sequence-video'); video.pause(); video.removeAttribute('src'); video.load();
  }

  function renderList() {
    const list = el('sequence-list'); list.replaceChildren();
    el('sequence-empty').hidden = items.length > 0;
    for (const item of items) {
      const li = document.createElement('li'), button = document.createElement('button');
      button.type='button'; button.dataset.id=item.id; button.setAttribute('aria-pressed',String(item.id === selected));
      button.textContent = `${number(item.start_s)}초 ~ ${number(item.end_s)}초${item.status === 'ready' ? '' : ' · 준비 중'}`;
      button.addEventListener('click',() => show(item)); li.append(button); list.append(li);
    }
    const current = items.find(item => item.id === selected);
    if (current) show(current); else if (selected) hideDetail();
  }

  async function refreshSequences() {
    try {
      const response = await fetch('/api/v1/sequences', {cache:'no-store',signal:AbortSignal.timeout(5000)});
      if (!response.ok) throw new Error('unavailable');
      const data = await response.json();
      if (!Array.isArray(data.items)) throw new Error('invalid');
      items = data.items.filter(item => item && safeId(item.id) && Number.isFinite(item.start_s) && Number.isFinite(item.end_s)).slice(0,100);
      renderList();
      el('sequence-empty').textContent = '저장된 장면이 없습니다';
    } catch (_) {
      items = []; renderList();
      el('sequence-empty').textContent = '장면 목록을 불러오지 못했습니다.';
    }
  }

  el('sequence-refresh').addEventListener('click', refreshSequences);
  el('sequence-form').addEventListener('submit', async event => {
    event.preventDefault();
    const start = Number(el('sequence-start').value), end = Number(el('sequence-end').value);
    if (!Number.isFinite(start) || !Number.isFinite(end) || start < 0 || end <= start || end-start > 20) {
      el('sequence-message').textContent = '시작·종료 시간을 확인해 주세요. 구간은 최대 20초입니다.'; return;
    }
    const button = el('sequence-save'); button.disabled = true; el('sequence-message').textContent = '장면을 저장하고 있습니다.';
    try {
      const response = await fetch('/api/v1/sequences', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({start_s:start,end_s:end}), signal:AbortSignal.timeout(120000)});
      if (!response.ok) {
        if (response.status === 409) throw new Error('업로드한 영상이 준비되어 있는지 확인해 주세요.');
        if (response.status === 422 || response.status === 400) throw new Error('영상 길이와 선택한 구간을 확인해 주세요.');
        throw new Error('장면 저장에 실패했습니다. 서버 상태를 확인해 주세요.');
      }
      const item = await response.json();
      if (!item || !safeId(item.id)) throw new Error('장면 저장 결과를 확인하지 못했습니다.');
      el('sequence-message').textContent = item.snapshot_available ? '장면과 분석 프레임 한 장을 저장했습니다.' : '장면을 저장했습니다. 연결할 분석 프레임은 없습니다.';
      await refreshSequences();
      const saved = items.find(value => value.id === item.id);
      if (saved) show(saved);
    } catch (error) { el('sequence-message').textContent = error?.message || '장면 저장 중 연결이 끊겼습니다.'; }
    finally { button.disabled = false; }
  });
  el('sequence-video').addEventListener('error', () => { el('sequence-message').textContent='저장된 영상을 재생하지 못했습니다.'; });
  refreshSequences();
})();
