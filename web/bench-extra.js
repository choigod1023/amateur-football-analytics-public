// Additions to the coach's bench screen (loaded after bench.js, which it does not change): a small map of where both teams stand now, and the two buttons "도움됨" / "아님" for the alerts.
// Reads /api/v1/bench (the same answer as bench.js), /api/v1/bench/minimap and /api/v1/bench/feedback; writes only the coach's answer (POST /api/v1/bench/feedback, kept apart from the reviewer's ratings).
(() => {
  const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
  const NS = 'http://www.w3.org/2000/svg';
  const svgNode = (tag, attrs) => { const e = document.createElementNS(NS, tag); for (const k in attrs) e.setAttribute(k, attrs[k]); return e; };
  const COACH = { ok: '도움됨', wrong: '아님' }, USER = { ok: '맞음', wrong: '틀림', useless: '쓸모없음' };
  const STALE = 5;                       // seconds after which the map is dimmed
  let snap = null, labels = {}, minimap = null, minimapAt = 0, mapKey = '', listKey = '', cardKey = '';
  let cameraView = true;       // the map as the camera sees it (near touchline at the bottom); false = the team's view (own team attacks to the right)
  try { cameraView = localStorage.getItem('benchMapView') !== 'team'; } catch (e) { /* no storage: camera view */ }

  const style = document.createElement('style');
  style.textContent = `
    .xtra { background: #151b23; border-radius: 12px; padding: 12px 14px; margin-bottom: 14px; }
    .xtra h2 { margin: 0 0 8px; font-size: 1.2rem; color: #9aa6b2; font-weight: 600; }
    .xtra svg { width: 100%; height: auto; display: block; border-radius: 8px; }
    .xtra .cap { margin: 6px 0 0; font-size: .95rem; color: #9aa6b2; }
    .xtra.dim svg { opacity: .45; }
    .coach-btns { display: flex; align-items: center; gap: 12px; margin-top: 14px; flex-wrap: wrap; }
    .coach-btns button { font: inherit; font-size: 1.3rem; min-width: 140px; min-height: 56px; border-radius: 12px; border: 3px solid #5b7a99; background: #1b2a3a; color: #f2f5f8; cursor: pointer; }
    .coach-btns button.on { background: #2b6cb0; border-color: #cfe6ff; }
    .coach-btns .says { font-size: 1.1rem; color: #9aa6b2; }
    .recent-fb { list-style: none; margin: 0; padding: 0; display: grid; gap: 8px; }
    .recent-fb li { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
    .recent-fb li b { font-size: 1rem; flex: 1 1 100%; }
    .recent-fb button { font: inherit; font-size: 1rem; min-height: 44px; min-width: 76px; border-radius: 10px; border: 2px solid #5b7a99; background: #1b2a3a; color: #f2f5f8; }
    .recent-fb button.on { background: #2b6cb0; border-color: #cfe6ff; }`;
  document.head.append(style);

  const mapBox = el('section', 'xtra'), listBox = el('section', 'xtra');
  const holder = document.querySelector('.recent');
  if (holder) holder.prepend(mapBox, listBox);

  function drawMap() {
    const p = minimap && minimap.positions;
    mapBox.replaceChildren(el('h2', '', '지금 선수 위치'));
    if (!p) { mapBox.append(el('p', 'cap', '위치 기록이 없습니다. 라이브 실행에 위치 기록 옵션이 켜져 있는지 확인해 주세요.')); return; }
    const age = p.age_s + (Date.now() - minimapAt) / 1000;
    mapBox.classList.toggle('dim', age > STALE);
    const turned = cameraView && p.direction === -1;       // the server turns the picture by 180 degrees when our team attacks to the left of the picture; turn it back
    const X = u => ((turned ? -u : u) + 44.5) * 6, Y = v => ((turned ? -v : v) + 31) * 6;
    const svg = svgNode('svg', { viewBox: '0 0 534 372', role: 'img', 'aria-label': '지금 선수 위치' });
    svg.append(svgNode('rect', { x: 0, y: 0, width: 534, height: 372, rx: 8, fill: '#1d4d2b' }));
    const line = { fill: 'none', stroke: '#9fd0a8', 'stroke-width': 2 };
    svg.append(svgNode('rect', { x: 4, y: 4, width: 526, height: 364, ...line }), svgNode('line', { x1: 267, y1: 4, x2: 267, y2: 368, ...line }), svgNode('circle', { cx: 267, cy: 186, r: 55, ...line }));
    svg.append(svgNode('rect', { x: 4, y: 186 - 121, width: 99, height: 242, ...line }), svgNode('rect', { x: 431, y: 186 - 121, width: 99, height: 242, ...line }));
    const lanes = { left: [0, 124], centre: [124, 248], right: [248, 372] };         // thirds of the width; the team's own left is the top
    for (const team_name of p.empty || []) {
      const name = turned ? { left: 'right', centre: 'centre', right: 'left' }[team_name] : team_name;
      const [y0, y1] = lanes[name];
      svg.append(svgNode('rect', { x: turned ? 276 : 8, y: y0 + 4, width: 250, height: y1 - y0 - 8, rx: 8, fill: '#ffb020', opacity: 0.28 }));
      const t = svgNode('text', { x: turned ? 401 : 133, y: (y0 + y1) / 2 + 6, 'text-anchor': 'middle', fill: '#ffe2a0', 'font-size': 22, 'font-weight': 700 }); t.textContent = '비어 있음'; svg.append(t);
    }
    for (const q of p.theirs) svg.append(svgNode('circle', { cx: X(q[0]), cy: Y(q[1]), r: 13, fill: '#12301b', stroke: '#ff8a6b', 'stroke-width': 5 }));
    for (const q of p.ours) svg.append(svgNode('circle', { cx: X(q[0]), cy: Y(q[1]), r: 13, fill: '#4aa3ff', stroke: '#e8f3ff', 'stroke-width': 2 }));
    const toggle = el('button', 'maptoggle', cameraView ? '우리 팀 기준으로 보기' : '영상 기준으로 보기');
    toggle.type = 'button';
    toggle.addEventListener('click', () => { cameraView = !cameraView; try { localStorage.setItem('benchMapView', cameraView ? 'camera' : 'team'); } catch (e) { /* ignore */ } drawMap(); });
    mapBox.append(toggle);
    mapBox.append(svg, el('p', 'cap', `파란 점 우리 팀, 붉은 테두리 상대 팀. ${turned ? '영상 기준: 우리 팀은 화면 왼쪽으로 공격합니다.' : cameraView ? '영상 기준: 우리 팀은 화면 오른쪽으로 공격합니다.' : '우리 팀 기준: 우리 팀은 오른쪽으로 공격합니다.'}${age > STALE ? ' 위치 기록이 멈춰 있습니다 (마지막 값).' : ''} 위치는 1m 안팎의 오차가 있습니다.`));
  }

  async function answer(alert, label) {
    labels[alert.number] = { ...(labels[alert.number] || {}), coach: label };
    renderButtons(true);
    try {
      await fetch('/api/v1/bench/feedback', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ session: snap.session, number: alert.number, label }) });
    } catch (e) { /* the next poll shows what was saved */ }
    pollFeedback();
  }

  function buttons(alert, big) {
    const state = labels[alert.number] || {};
    const row = big ? el('div', 'coach-btns') : document.createElement('span');
    if (state.user) { row.append(el('span', 'says', `사용자님 판정: ${USER[state.user] || state.user}`)); return row; }
    for (const label of ['ok', 'wrong']) {
      const b = el('button', state.coach === label ? 'on' : '', COACH[label]);
      b.type = 'button'; b.addEventListener('click', () => answer(alert, label)); row.append(b);
    }
    if (big && state.coach) row.append(el('span', 'says', `코치 의견: ${COACH[state.coach]}`));
    return row;
  }

  function renderButtons(force) {
    if (!snap) return;
    const alert = snap.current;
    const card = document.getElementById('alert');
    let slot = document.getElementById('coach-slot');
    if (card && !slot) { slot = el('div'); slot.id = 'coach-slot'; card.append(slot); }
    const key = JSON.stringify([snap.session, alert && alert.number, alert && labels[alert.number]]);
    if (slot && (force || key !== cardKey)) { cardKey = key; slot.replaceChildren(); if (alert && alert.accuracy !== null && !alert.status) slot.append(buttons(alert, true)); }
    const older = (snap.recent || []).filter(a => !a.status);
    const lkey = JSON.stringify([snap.session, older.map(a => [a.number, labels[a.number]])]);
    if (force || lkey !== listKey) {
      listKey = lkey; listBox.replaceChildren(el('h2', '', '이전 알림에 의견 남기기'));
      const list = el('ul', 'recent-fb');
      for (const a of older) { const li = el('li'); li.append(el('b', '', `${a.priority_text} · ${a.title}`), buttons(a, false)); list.append(li); }
      listBox.append(older.length ? list : el('p', 'cap', '이전 알림이 아직 없습니다'));
    }
  }

  async function pollFeedback() {
    if (!snap || !snap.session) return;
    const numbers = [snap.current, ...(snap.recent || [])].filter(a => a && !a.status).map(a => a.number);
    if (!numbers.length) return;
    try {
      const r = await fetch(`/api/v1/bench/feedback?session=${encodeURIComponent(snap.session)}&numbers=${numbers.join(',')}`, { cache: 'no-store' });
      if (r.ok) { labels = { ...labels, ...(await r.json()).labels }; renderButtons(false); }
    } catch (e) { /* keep the last answers */ }
  }

  async function pollSnap() {
    try { const r = await fetch('/api/v1/bench', { cache: 'no-store' }); if (r.ok) snap = await r.json(); } catch (e) { return; }
    renderButtons(false);
  }
  async function pollMap() {
    try { const r = await fetch('/api/v1/bench/minimap' + (snap && snap.session ? `?session=${encodeURIComponent(snap.session)}` : ''), { cache: 'no-store' }); if (r.ok) { minimap = await r.json(); minimapAt = Date.now(); } } catch (e) { /* keep the last map */ }
    drawMap();
  }
  pollSnap(); setInterval(pollSnap, 1000);
  setTimeout(pollMap, 300); setInterval(pollMap, 1000);
  setTimeout(pollFeedback, 800); setInterval(pollFeedback, 2500);
  setInterval(() => { if (minimap && minimap.positions) drawMap(); }, 2000);        // the dimming follows the age even when the server does not answer
})();
