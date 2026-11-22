/* Verification of saved ball positions: right, wrong or moved. Only the reviewer's answer counts. */
(() => {
  const el = id => document.getElementById(id);
  if (!el('ball-verify')) return;
  const post = (path, body) => fetch('/api/v1/ball/' + path, {method:'POST', headers:{'Content-Type':'application/json'}, body: body && JSON.stringify(body)});
  const PANEL = 330, SPAN = 66, SCALE = PANEL / SPAN;           // 66 x 66 px of the frame shown at 5x
  const canvas = el('vf-canvas'), ctx = canvas.getContext('2d');
  const SOURCE_NAMES = {suggestion:'추천 후보를 Enter로 수락', tile:'확대 그림을 눌러 선택', key:'숫자키로 후보 선택', snap:'후보 근처 클릭(자동 흡착)', manual:'직접 클릭', verify_click:'검증 중 직접 수정'};
  const FILTERS = [['pending', '미검증', i => !i.verified], ['risk', '추천 수락·방식 기록 없음(먼저 확인)', i => !i.verified && (i.source === 'suggestion' || !i.source)],
    ['ok', '맞음·수정', i => i.verified === 'ok' || i.verified === 'moved'], ['rejected', '공이 아님', i => i.verified === 'rejected'], ['all', '전체', () => true]];
  const images = new Map();
  let items = [], filter = 'risk', pos = 0, active = false, busy = false;
  const status = text => { el('vf-status').textContent = text; };
  function image(clipId, file) {
    const key = `/ball-media/${clipId}/${file}`; let img = images.get(key);
    if (!img) { img = new Image(); img.src = key; img.addEventListener('load', draw); images.set(key, img); }
    return img;
  }
  const visible = () => {
    const test = (FILTERS.find(f => f[0] === filter) || FILTERS[0])[2];
    return items.filter(test);
  };
  const current = () => visible()[Math.min(pos, Math.max(0, visible().length - 1))];

  async function load() {
    status('저장한 공 위치를 불러오는 중입니다.');
    try {
      const l = await post('list'); if (!l.ok) throw new Error();
      const list = (await l.json()).clips; items = [];
      for (const c of list) {
        const r = await post('clip', {id:c.id}); if (!r.ok) continue; const d = await r.json();
        d.frames.forEach((f, i) => { const lab = d.labels[f.file]; if (lab && lab.state === 'ball') items.push({clip:d.id, camera:d.camera, start:d.start, files:d.frames.map(x => x.file), labels:d.labels, i, file:f.file,
          x:lab.x, y:lab.y, source:lab.source, verified:lab.verified}); });
      }
    } catch (_) { status('불러오지 못했습니다. 서버가 새 버전인지 확인하세요.'); return false; }
    items.sort((a, b) => ((b.source === 'suggestion' || !b.source) - (a.source === 'suggestion' || !a.source)) || a.clip.localeCompare(b.clip) || a.i - b.i);
    return true;
  }
  function renderFilters() {
    const bar = el('vf-filters'); bar.replaceChildren();
    for (const [key, label, test] of FILTERS) {
      const b = document.createElement('button'); b.type = 'button'; b.className = 'scene-filter' + (key === filter ? ' is-active' : ''); b.textContent = `${label} ${items.filter(test).length}`;
      b.addEventListener('click', () => { filter = key; pos = 0; render(); }); bar.append(b);
    }
  }
  function render() {
    renderFilters();
    const list = visible(), total = items.length, done = items.filter(i => i.verified).length;
    status(`저장한 공 위치 ${total}개 중 확인 ${done}개 · 맞음 ${items.filter(i => i.verified === 'ok').length} · 수정 ${items.filter(i => i.verified === 'moved').length} · 공이 아님 ${items.filter(i => i.verified === 'rejected').length}`);
    el('vf-card').hidden = !list.length;
    if (!list.length) { status(el('vf-status').textContent + ' · 이 필터에는 확인할 위치가 없습니다.'); return; }
    pos = Math.min(pos, list.length - 1); draw();
  }
  function draw() {
    const it = current(); if (!it || !active) return;
    ctx.imageSmoothingEnabled = false; ctx.fillStyle = '#000'; ctx.fillRect(0, 0, PANEL * 3, PANEL);
    const labels = ['앞 프레임', '현재(저장한 위치)', '다음 프레임'];
    for (let k = 0; k < 3; k++) {
      const fi = it.i + k - 1, ox = k * PANEL;
      if (fi < 0 || fi >= it.files.length) { ctx.fillStyle = '#555'; ctx.font = '16px sans-serif'; ctx.fillText('프레임 없음', ox + 110, PANEL / 2); continue; }
      const img = image(it.clip, it.files[fi]);
      if (img.complete && img.naturalWidth) ctx.drawImage(img, it.x - SPAN / 2, it.y - SPAN / 2, SPAN, SPAN, ox, 0, PANEL, PANEL);
      ctx.strokeStyle = k === 1 ? '#3dff6f' : 'rgba(255,255,255,.55)'; ctx.lineWidth = 2;
      const cx = ox + PANEL / 2, cy = PANEL / 2;
      ctx.beginPath(); ctx.moveTo(cx - 22, cy); ctx.lineTo(cx - 8, cy); ctx.moveTo(cx + 8, cy); ctx.lineTo(cx + 22, cy); ctx.moveTo(cx, cy - 22); ctx.lineTo(cx, cy - 8); ctx.moveTo(cx, cy + 8); ctx.lineTo(cx, cy + 22); ctx.stroke();
      const nb = it.labels[it.files[fi]];                           // where the ball was saved in the neighbouring frames
      if (k !== 1 && nb && nb.state === 'ball') {
        const dx = (nb.x - it.x) * SCALE + cx, dy = (nb.y - it.y) * SCALE + cy;
        if (dx > ox && dx < ox + PANEL && dy > 0 && dy < PANEL) { ctx.fillStyle = '#ffd24f'; ctx.beginPath(); ctx.arc(dx, dy, 6, 0, 7); ctx.fill(); }
      }
      ctx.fillStyle = 'rgba(0,0,0,.65)'; ctx.fillRect(ox, 0, PANEL, 22); ctx.fillStyle = '#fff'; ctx.font = '14px sans-serif'; ctx.fillText(labels[k], ox + 8, 16);
      ctx.strokeStyle = '#222'; ctx.strokeRect(ox, 0, PANEL, PANEL);
    }
    const src = it.source ? SOURCE_NAMES[it.source] || it.source : '방식 기록 없음(예전에 저장한 위치)';
    el('vf-info').textContent = `클립 ${it.clip}(${it.camera}) · 프레임 ${it.i + 1}/${it.files.length} · 저장 방식: ${src}` + (it.verified ? ` · 이미 확인함: ${({ok:'맞음', moved:'수정', rejected:'공이 아님'})[it.verified]}` : '') + ` · 위치 ${Math.round(it.x)}, ${Math.round(it.y)} (노란 점은 이웃 프레임에 저장한 위치)`;
  }
  async function verdict(kind, x, y) {
    const it = current(); if (!it || busy) return; busy = true;
    try {
      const r = await post('verify', {clip:it.clip, frame:it.file, verdict:kind, x: kind === 'moved' ? x : null, y: kind === 'moved' ? y : null});
      if (!r.ok) throw new Error();
      const saved = (await r.json()).saved;
      it.verified = saved.verified; it.x = saved.x; it.y = saved.y; it.source = saved.source; it.labels[it.file] = saved;
    } catch (_) { status('확인 결과를 저장하지 못했습니다. 서버가 새 버전인지, 연결이 되는지 확인하세요.'); busy = false; return; }
    busy = false;
    const before = visible().length; render();
    if (visible().length === before) pos = Math.min(pos + 1, visible().length - 1);   // the item stays in this filter: step on
    draw();
  }
  function move(step) { const n = visible().length; if (n) { pos = Math.min(n - 1, Math.max(0, pos + step)); draw(); } }

  canvas.addEventListener('click', event => {
    const it = current(); if (!it) return;
    const r = canvas.getBoundingClientRect(), px = (event.clientX - r.left) / r.width * PANEL * 3, py = (event.clientY - r.top) / r.height * PANEL;
    if (px < PANEL || px > 2 * PANEL) { status('위치를 고치려면 가운데 그림을 눌러 주세요.'); return; }
    verdict('moved', Math.round((it.x - SPAN / 2 + (px - PANEL) / SCALE) * 10) / 10, Math.round((it.y - SPAN / 2 + py / SCALE) * 10) / 10);
  });
  el('vf-ok').addEventListener('click', () => verdict('ok')); el('vf-no').addEventListener('click', () => verdict('rejected'));
  el('vf-skip').addEventListener('click', () => move(1)); el('vf-prev').addEventListener('click', () => move(-1));
  document.addEventListener('keydown', event => {
    if (!active || event.ctrlKey || event.altKey || event.metaKey) return;
    if (['INPUT', 'SELECT', 'TEXTAREA'].includes(event.target && event.target.tagName)) return;
    const k = event.key.toLowerCase();
    if (k === 'o' || event.key === 'Enter') { event.preventDefault(); verdict('ok'); }
    else if (k === 'x') verdict('rejected'); else if (k === 's' || event.key === 'ArrowRight') move(1); else if (event.key === 'ArrowLeft') move(-1);
  });
  async function setMode(verify) {
    active = verify; document.body.dataset.mode = verify ? 'verify' : 'label';
    el('ball-main').hidden = verify || !el('ball-title').textContent || el('ball-title').textContent === '클립'; el('ball-verify').hidden = !verify;
    el('mode-label').classList.toggle('is-active', !verify); el('mode-verify').classList.toggle('is-active', verify);
    if (verify && (await load())) render();
  }
  el('mode-label').addEventListener('click', () => setMode(false)); el('mode-verify').addEventListener('click', () => setMode(true));
})();
