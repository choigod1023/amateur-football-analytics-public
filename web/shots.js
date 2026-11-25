// The shot tagging page: pick a moment, watch the clip, say what happened and click where the shot was taken (our view: our goal on the left).
(() => {
  const el = id => document.getElementById(id);
  const L = 89, W = 62, S = 6, PAD = 18, NS = 'http://www.w3.org/2000/svg';
  const RESULT = [['none', '슛 아님'], ['off', '빗나감(골대 밖)'], ['saved', '유효슈팅(골키퍼가 막음)'], ['blocked', '수비가 막음'], ['post', '골대를 맞힘'], ['goal', '골']];
  const LANES = ['왼쪽 측면', '왼쪽 하프스페이스', '가운데', '오른쪽 하프스페이스', '오른쪽 측면'];
  let data = null, tags = {}, current = null, spot = null, manual = false;
  const px = (u, v) => [PAD + (u + L / 2) * S, PAD + (v + W / 2) * S];
  const node = (name, attrs) => { const n = document.createElementNS(NS, name); for (const k in attrs) n.setAttribute(k, attrs[k]); return n; };
  const post = (path, body) => fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }).then(r => { if (!r.ok) throw new Error(r.status); return r.json(); });

  function sideText(c) { return c.side === 'ours' ? '우리 공격' : c.side === 'theirs' ? '상대 공격' : '골 장면(팀 확인 필요)'; }
  function label(c) { return `${c.match_label} ${c.half} ${Math.floor(c.minute)}분 ${String(Math.round((c.minute % 1) * 60)).padStart(2, '0')}초 · ${sideText(c)}`; }

  function drawPitch(c) {
    const svg = el('pitch');
    svg.replaceChildren();
    svg.append(node('rect', { x: PAD, y: PAD, width: L * S, height: W * S, fill: '#2d6a3e', stroke: '#cfe8d4', 'stroke-width': 2 }));
    const [cx, cy] = px(0, 0);
    svg.append(node('line', { x1: cx, y1: PAD, x2: cx, y2: PAD + W * S, stroke: '#cfe8d4', 'stroke-width': 2 }), node('circle', { cx, cy, r: 9.15 * S, fill: 'none', stroke: '#cfe8d4', 'stroke-width': 2 }));
    for (const sx of [-1, 1]) {
      const [ax, ay] = px(sx * (L / 2 - 16.5), -20.15), [bx] = px(sx * L / 2, 0);
      svg.append(node('rect', { x: Math.min(ax, bx), y: ay, width: 16.5 * S, height: 40.3 * S, fill: 'none', stroke: '#cfe8d4', 'stroke-width': 2 }));
      const [gx0, gy0] = px(sx * (L / 2 - 5.5), -9.15);
      svg.append(node('rect', { x: Math.min(gx0, bx), y: gy0, width: 5.5 * S, height: 18.3 * S, fill: 'none', stroke: '#cfe8d4', 'stroke-width': 1.5 }));
    }
    if (c && c.snapshots) {
      const snap = c.snapshots['0'] || c.snapshots['-2'] || c.snapshots['2'];
      if (snap) {
        for (const [pts, colour] of [[snap.theirs, '#ff8a6b'], [snap.ours, '#6db8ff']]) for (const [u, v] of pts) { const [x, y] = px(u, v); svg.append(node('circle', { cx: x, cy: y, r: 6, fill: colour, opacity: 0.9 })); }
      }
    }
    if (spot) {
      const [x, y] = px(spot.x, spot.y);
      svg.append(node('line', { x1: x - 9, y1: y - 9, x2: x + 9, y2: y + 9, stroke: '#ffe14a', 'stroke-width': 4 }), node('line', { x1: x - 9, y1: y + 9, x2: x + 9, y2: y - 9, stroke: '#ffe14a', 'stroke-width': 4 }));
    }
  }

  el('pitch').addEventListener('click', ev => {
    const svg = el('pitch'), r = svg.getBoundingClientRect();
    const x = (ev.clientX - r.left) / r.width * 570, y = (ev.clientY - r.top) / r.height * 408;
    spot = { x: Math.max(-L / 2, Math.min(L / 2, (x - PAD) / S - L / 2)), y: Math.max(-W / 2, Math.min(W / 2, (y - PAD) / S - W / 2)) };
    drawPitch(manual ? null : current);
    el('pitch-note').textContent = `슛 위치를 눌렀습니다. 이제 결과 단추를 눌러 저장하세요.`;
  });

  function buttons(target, onPick) {
    target.replaceChildren();
    for (const [key, text] of RESULT) {
      const b = document.createElement('button');
      b.type = 'button'; b.textContent = text; if (key === 'none') b.className = 'warn';
      b.addEventListener('click', () => onPick(key));
      target.append(b);
    }
  }

  async function save(result) {
    if (!current) return;
    if (result !== 'none' && !spot) { el('saved').textContent = '먼저 오른쪽 그림에서 슛이 나간 위치를 눌러 주세요.'; return; }
    try {
      const side = current.side === 'unknown' ? (el('side-pick') ? el('side-pick').value : '') : undefined;
      if (current.side === 'unknown' && !side) { el('saved').textContent = '먼저 어느 팀의 슛인지 골라 주세요.'; return; }
      const r = await post('/api/v1/shots/tag', { id: current.id, result, side, x: spot ? spot.x : null, y: spot ? spot.y : null });
      tags[current.id] = r;
      el('saved').textContent = result === 'none' ? '저장했습니다: 슛 아님' : `저장했습니다: ${RESULT.find(x => x[0] === result)[1]}, xG ${r.xg.toFixed(2)}`;
      renderList(); progress();
    } catch (e) { el('saved').textContent = '저장하지 못했습니다. 다시 눌러 주세요.'; }
  }

  async function saveExtra(result) {
    if (result === 'none') return;
    if (!spot) { el('saved').textContent = '먼저 그림에서 슛이 나간 위치를 눌러 주세요.'; return; }
    try {
      const r = await post('/api/v1/shots/extra', { match: el('x-match').value, half: el('x-half').value, minute: Number(el('x-minute').value), side: el('x-side').value, result, x: spot.x, y: spot.y });
      tags[r.id] = r;
      el('saved').textContent = `추가했습니다: ${RESULT.find(x => x[0] === result)[1]}, xG ${r.xg.toFixed(2)}`;
      progress();
    } catch (e) { el('saved').textContent = '추가하지 못했습니다.'; }
  }

  function select(c) {
    current = c; manual = false;
    const t = tags[c.id];
    spot = t && t.x !== undefined ? { x: t.x, y: t.y } : null;
    el('detail').hidden = false;
    el('title').textContent = `${label(c)} · ${LANES[c.lane]}으로 ${c.players}명`;
    const v = el('video'); v.src = '/shots-clip/' + c.clip; v.load();
    drawPitch(c);
    el('pitch-note').textContent = '그림은 우리 골대가 왼쪽입니다. 슛이 나간 위치를 눌러 주세요.';
    el('saved').textContent = t ? `이미 저장됨: ${RESULT.find(x => x[0] === t.result)[1]}${t.xg !== undefined ? `, xG ${t.xg.toFixed(2)}` : ''}` : '';
    buttons(el('buttons'), save);
    const pick = el('side-row'); pick.hidden = c.side !== 'unknown';
    renderList();
  }

  function visible() {
    const m = el('f-match').value, s = el('f-side').value, todo = el('f-todo').checked;
    return data.candidates.filter(c => (!m || c.match === m) && (!s || c.side === s) && (!todo || !tags[c.id]));
  }

  function renderList() {
    const list = el('list');
    list.replaceChildren();
    for (const c of visible()) {
      const li = document.createElement('li');
      const t = tags[c.id];
      li.className = (current && current.id === c.id ? 'on ' : '') + (t ? '' : 'todo');
      li.textContent = label(c);
      const st = document.createElement('span'); st.className = 'st';
      st.textContent = t ? (t.result === 'none' ? '슛 아님' : RESULT.find(x => x[0] === t.result)[1]) : '표시 전';
      li.prepend(st);
      li.addEventListener('click', () => select(c));
      list.append(li);
    }
  }

  function progress() {
    const total = data.candidates.length, done = data.candidates.filter(c => tags[c.id]).length;
    const extra = Object.keys(tags).filter(k => k.startsWith('x-')).length;
    el('progress').textContent = `${total}개 장면 중 ${done}개를 표시했습니다. 직접 추가한 슛 ${extra}개.`;
  }

  async function init() {
    const r = await fetch('/api/v1/shots', { cache: 'no-store' });
    data = await r.json(); tags = data.tags || {};
    const matches = [...new Map(data.candidates.map(c => [c.match, c.match_label]))];
    for (const [k, t] of matches) {
      for (const sel of [el('f-match'), el('x-match')]) { const o = document.createElement('option'); o.value = k; o.textContent = t; sel.append(o); }
    }
    for (const id of ['f-match', 'f-side', 'f-todo']) el(id).addEventListener('change', renderList);
    buttons(el('x-buttons'), saveExtra);
    el('extra').addEventListener('toggle', () => {
      if (el('extra').open) { manual = true; current = null; spot = null; el('detail').hidden = false; el('title').textContent = '직접 추가'; el('video').removeAttribute('src'); el('buttons').replaceChildren(); drawPitch(null); el('saved').textContent = ''; }
    });
    renderList(); progress();
    const first = visible()[0];
    if (first) select(first);
  }
  init().catch(() => { el('progress').textContent = '불러오지 못했습니다.'; });
})();
