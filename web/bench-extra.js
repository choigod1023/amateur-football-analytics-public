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
    .xtra { background: var(--c-card, #122019); border: 1px solid var(--c-line, #24392c); border-radius: var(--r-lg, 18px); padding: 14px; margin-bottom: 14px; display: grid; gap: 8px; }
    .xtra h2 { margin: 0; font-size: 1.15rem; color: var(--c-text, #eef3ee); font-weight: 900; }
    .xtra svg { width: 100%; height: auto; display: block; border-radius: 12px; }
    .xtra .cap { margin: 0; font-size: .9rem; color: var(--c-mute, #93a89a); }
    .xtra.dim svg { opacity: .45; }
    .xtra[hidden] { display: none; }
    .xtra .maptoggle { justify-self: start; }
    .coach-btns { display: flex; align-items: center; gap: 10px; margin-top: 6px; flex-wrap: wrap; }
    .coach-btns button { font: inherit; font-size: 1.2rem; font-weight: 700; min-width: 130px; min-height: 52px; border-radius: var(--r-md, 14px); border: 1px solid var(--c-line-2, #3b5a47); background: var(--c-card-2, #18291f); color: var(--c-text, #eef3ee); cursor: pointer; touch-action: manipulation; }
    .coach-btns button.on { background: var(--c-pitch, #40d678); border-color: var(--c-pitch, #40d678); color: var(--c-on-accent, #0b1310); font-weight: 900; }
    .coach-btns .says { font-size: 1rem; color: var(--c-mute, #93a89a); }
    .recent-fb { list-style: none; margin: 0; padding: 0; display: grid; gap: 8px; }
    .recent-fb li { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; background: var(--c-card-2, #18291f); border: 1px solid var(--c-line, #24392c); border-radius: var(--r-md, 14px); padding: 8px 10px; }
    .recent-fb li b { font-size: 1rem; flex: 1 1 100%; }
    .recent-fb button { font: inherit; font-size: 1rem; font-weight: 700; min-height: 44px; min-width: 76px; border-radius: var(--r-sm, 9px); border: 1px solid var(--c-line-2, #3b5a47); background: var(--c-card, #122019); color: var(--c-text, #eef3ee); }
    .recent-fb button.on { background: var(--c-pitch, #40d678); border-color: var(--c-pitch, #40d678); color: var(--c-on-accent, #0b1310); }`;
  document.head.append(style);

  const mapBox = el('section', 'xtra'), listBox = el('section', 'xtra');
  const holder = document.querySelector('.recent');
  if (holder) holder.prepend(mapBox);
  const fold = document.getElementById('recent-fold');
  if (fold) fold.append(listBox); else if (holder) holder.append(listBox);
  const FRESH = 15;            // seconds an alert is "now" (bench.js dims it after this): its picture takes the place of the map of now
  let snapAt = 0, picKey = '';

  function pitch(label) {
    // drawn like the half-time report (web/halftime.js): grass, thin chalk lines, penalty and goal boxes; the colours are classes of web/bench.css
    const svg = svgNode('svg', { viewBox: '0 0 534 372', role: 'img', 'aria-label': label });
    svg.append(svgNode('rect', { x: 0, y: 0, width: 534, height: 372, rx: 12, class: 'mm-grass' }));
    const line = { class: 'mm-chalk' };
    svg.append(svgNode('rect', { x: 4, y: 4, width: 526, height: 364, ...line }), svgNode('line', { x1: 267, y1: 4, x2: 267, y2: 368, ...line }), svgNode('circle', { cx: 267, cy: 186, r: 55, ...line }));
    svg.append(svgNode('rect', { x: 4, y: 186 - 121, width: 99, height: 242, ...line }), svgNode('rect', { x: 431, y: 186 - 121, width: 99, height: 242, ...line }));
    svg.append(svgNode('rect', { x: 4, y: 186 - 55, width: 33, height: 110, ...line }), svgNode('rect', { x: 497, y: 186 - 55, width: 33, height: 110, ...line }));
    return svg;
  }
  // "우리 골문" at our goal and "우리 공격 →" toward the other goal, on the bottom edge like the half-time report; on the top edge when `top` (a line label is at the bottom)
  function sides(svg, turned, top) {
    const y = top ? 26 : 360, goalLeft = !turned;
    const g = svgNode('text', { x: goalLeft ? 12 : 522, y, 'text-anchor': goalLeft ? 'start' : 'end', class: 'mm-goal' }); g.textContent = '우리 골문';
    const a = svgNode('text', { x: goalLeft ? 522 : 12, y, 'text-anchor': goalLeft ? 'end' : 'start', class: 'mm-attack' }); a.textContent = goalLeft ? '우리 공격 →' : '← 우리 공격';
    svg.append(g, a);
  }
  // team view (u toward the goal we attack, v across) -> picture; turned back by 180 degrees in the camera view when our team attacks to the left of the picture
  const mapper = direction => { const turned = cameraView && direction === -1; return { turned, X: u => ((turned ? -u : u) + 44.5) * 6, Y: v => ((turned ? -v : v) + 31) * 6 }; };
  function toggleView() { cameraView = !cameraView; try { localStorage.setItem('benchMapView', cameraView ? 'camera' : 'team'); } catch (e) { /* ignore */ } picKey = ''; drawMap(); drawPicture(); }
  const currentAge = () => (snap && snap.current ? snap.current.age_s + (Date.now() - snapAt) / 1000 : Infinity);
  const pictureShown = () => !!(snap && snap.current && snap.current.picture && currentAge() <= FRESH);

  function arrow(svg, x1, y1, x2, y2, cls) {
    const len = Math.hypot(x2 - x1, y2 - y1); if (len < 4) return;
    const ux = (x2 - x1) / len, uy = (y2 - y1) / len, head = 16, bx = x2 - ux * head, by = y2 - uy * head;
    svg.append(svgNode('line', { x1, y1, x2: bx, y2: by, class: 'pic-arrow ' + cls }));
    svg.append(svgNode('polygon', { points: `${x2},${y2} ${bx - uy * 9},${by + ux * 9} ${bx + uy * 9},${by - ux * 9}`, class: 'pic-head' + (cls.includes('theirs') ? ' theirs' : '') }));
  }

  function drawPicture() {
    const slot = document.getElementById('pic-slot');
    if (!slot) return;
    const pic = pictureShown() ? snap.current.picture : null;
    const key = JSON.stringify([pic && snap.current.number, snap && snap.session, cameraView, !!pic]);
    if (key === picKey) return;
    picKey = key;
    slot.replaceChildren();
    if (!pic) return;
    const { turned, X, Y } = mapper(pic.direction);
    const isPos = pic.type === 'position';       // the position map: where both teams stood, one marked area, no arrows or suggestions
    const svg = pitch(isPos ? '알림 순간의 선수 위치' : '알림 순간의 선수 위치와 제안');
    for (const z of pic.zones || []) {
      const xs = [X(z.u0), X(z.u1)], ys = [Y(z.v0), Y(z.v1)];
      svg.append(svgNode('rect', { x: Math.min(...xs), y: Math.min(...ys), width: Math.abs(xs[1] - xs[0]), height: Math.abs(ys[1] - ys[0]), class: 'pic-zone' }));
    }
    for (const l of pic.lines || []) {
      svg.append(svgNode('line', { x1: X(l.u), y1: 4, x2: X(l.u), y2: 368, class: { now: 'pic-now', back: 'pic-now', before: 'pic-before', theirs: 'pic-their-line' }[l.style] || 'pic-before' }));
      const name = { now: '지금', back: '수비 줄', before: '전' }[l.style];
      if (name) { const right = X(l.u) < 470; const t = svgNode('text', { x: X(l.u) + (right ? 8 : -8), y: l.style === 'now' ? 358 : 32, 'text-anchor': right ? 'start' : 'end', class: 'pic-label ' + l.style }); t.textContent = name; svg.append(t); }
    }
    for (const q of pic.theirs || []) svg.append(svgNode('circle', { cx: X(q[0]), cy: Y(q[1]), r: 12, class: 'pic-theirs' }));
    for (const q of pic.ours || []) svg.append(svgNode('circle', { cx: X(q[0]), cy: Y(q[1]), r: 12, class: 'pic-ours' }));
    for (const a of (isPos ? [] : pic.arrows || [])) arrow(svg, X(a.from[0]), Y(a.from[1]), X(a.to[0]), Y(a.to[1]), (a.style === 'dashed' ? 'dashed' : 'solid') + (a.side === 'theirs' ? ' theirs' : ''));
    for (const q of pic.threat || []) svg.append(svgNode('circle', { cx: X(q[0]), cy: Y(q[1]), r: 13, class: 'pic-threat' }));
    for (const q of pic.focus || []) svg.append(svgNode('circle', { cx: X(q[0]), cy: Y(q[1]), r: 20, class: 'pic-focus' }));
    // the goal and attack labels go where no line label ("지금" at the bottom, "전" at the top) sits near an edge; with both edges taken the caption below says it
    const near = (style) => (pic.lines || []).some(l => l.style === style && (X(l.u) < 150 || X(l.u) > 384));
    if (!near('now')) sides(svg, turned, false); else if (!near('before')) sides(svg, turned, true);
    const cap = el('p', 'piccap');
    cap.append(el('span', '', isPos ? '' : '노랑 선수 · 점선 제안 · '), el('b', 'picdir', `우리 공격 ${turned ? '←' : '→'}`));      // the direction in body size and the accent colour: the picture may have no room for it
    const b = el('button', '', '방향 바꾸기'); b.type = 'button'; b.addEventListener('click', toggleView); cap.append(b);
    slot.append(svg);
    if (isPos) slot.append(el('p', 'piclegend', pic.legend || ''));      // one line of what the fill, ring and line mean, between the picture and the direction row
    slot.append(cap);
  }

  function drawMap() {
    const p = minimap && minimap.positions;
    mapBox.hidden = pictureShown();        // one place: the picture of a fresh alert, otherwise where the players stand now
    mapBox.replaceChildren(el('h2', '', '지금 선수 위치'));
    if (!p) { mapBox.append(el('p', 'cap', '위치 기록이 아직 없습니다')); return; }
    const age = p.age_s + (Date.now() - minimapAt) / 1000;
    mapBox.classList.toggle('dim', age > STALE);
    const { turned, X, Y } = mapper(p.direction);
    const svg = pitch('지금 선수 위치');
    const lanes = { left: [0, 124], centre: [124, 248], right: [248, 372] };         // thirds of the width; the team's own left is the top
    for (const team_name of p.empty || []) {
      const name = turned ? { left: 'right', centre: 'centre', right: 'left' }[team_name] : team_name;
      const [y0, y1] = lanes[name];
      svg.append(svgNode('rect', { x: turned ? 276 : 8, y: y0 + 4, width: 250, height: y1 - y0 - 8, rx: 8, class: 'mm-empty' }));
      const t = svgNode('text', { x: turned ? 401 : 133, y: (y0 + y1) / 2 + 6, 'text-anchor': 'middle', class: 'mm-empty-t' }); t.textContent = '비어 있음'; svg.append(t);
    }
    for (const q of p.theirs) svg.append(svgNode('circle', { cx: X(q[0]), cy: Y(q[1]), r: 13, class: 'mm-theirs' }));
    for (const q of p.ours) svg.append(svgNode('circle', { cx: X(q[0]), cy: Y(q[1]), r: 13, class: 'mm-ours' }));
    sides(svg, turned, false);
    const toggle = el('button', 'maptoggle', cameraView ? '지금: 영상과 같은 방향 (바꾸기)' : '지금: 우리 공격이 오른쪽 (바꾸기)');
    toggle.type = 'button';
    toggle.addEventListener('click', toggleView);
    mapBox.append(toggle);
    mapBox.append(svg, el('p', 'cap', `굵은 테두리 우리 · 가는 테두리 상대 · 우리 공격 ${turned ? '←' : '→'}${age > STALE ? ' · 위치 멈춤 (마지막 값)' : ''}`));
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
    if (card && !slot) { slot = el('div'); slot.id = 'coach-slot'; const more = document.getElementById('more'); if (more && more.parentNode === card) card.insertBefore(slot, more); else card.append(slot); }
    const key = JSON.stringify([snap.session, alert && alert.number, alert && labels[alert.number]]);
    if (slot && (force || key !== cardKey)) { cardKey = key; slot.replaceChildren(); if (alert && alert.accuracy !== null && !alert.status) slot.append(buttons(alert, true)); }
    const older = (snap.recent || []).filter(a => !a.status);
    const lkey = JSON.stringify([snap.session, older.map(a => [a.number, labels[a.number]])]);
    if (force || lkey !== listKey) {
      listKey = lkey; listBox.replaceChildren(el('h2', '', '이전 알림 평가'));
      const list = el('ul', 'recent-fb');
      for (const a of older) { const li = el('li'); li.append(el('b', '', `${a.priority_text} · ${a.line || a.title}`), buttons(a, false)); list.append(li); }
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
    try { const r = await fetch('/api/v1/bench', { cache: 'no-store' }); if (r.ok) { snap = await r.json(); if (window.MatchClock) snap = window.MatchClock.gate(snap); snapAt = Date.now(); } } catch (e) { return; }
    renderButtons(false);
    try { drawPicture(); } catch (e) { /* the picture is an addition: the rest of the screen goes on */ }
  }
  // the shirt colours of the match as page variables for the dots (same rule as web/halftime.js): a very dark opponent colour gets a light thin ring
  let coloursKey = '';
  function teamColours(c) {
    const hex = v => (typeof v === 'string' && /^#[0-9a-f]{6}$/i.test(v) ? v : null);
    const ours = hex(c && c.ours) || '#40d678', theirs = hex(c && c.theirs) || '#c8cec9';
    if (ours + theirs === coloursKey) return;
    coloursKey = ours + theirs;
    const lum = x => { const n = [1, 3, 5].map(i => parseInt(x.slice(i, i + 2), 16) / 255).map(v => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4)); return 0.2126 * n[0] + 0.7152 * n[1] + 0.0722 * n[2]; };
    const root = document.documentElement.style;
    root.setProperty('--dot-ours', ours); root.setProperty('--dot-theirs', theirs);
    root.setProperty('--dot-theirs-ring', lum(theirs) < 0.06 ? '#cfe3d4' : '#0b1310');
  }
  teamColours(null);
  async function pollMap() {
    try { const r = await fetch('/api/v1/bench/minimap' + (snap && snap.session ? `?session=${encodeURIComponent(snap.session)}` : ''), { cache: 'no-store' }); if (r.ok) { minimap = await r.json(); minimapAt = Date.now(); teamColours(minimap.team_colours); } } catch (e) { /* keep the last map */ }
    drawMap();
  }
  pollSnap(); setInterval(pollSnap, 1000);
  setTimeout(pollMap, 300); setInterval(pollMap, 1000);
  setTimeout(pollFeedback, 800); setInterval(pollFeedback, 2500);
  setInterval(() => { try { drawPicture(); } catch (e) { /* ignore */ } if (minimap && minimap.positions) drawMap(); else mapBox.hidden = pictureShown(); }, 2000);        // the dimming follows the age even when the server does not answer
})();
