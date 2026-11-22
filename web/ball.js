/* Ball labeling: only a click by the reviewer becomes a label; the circles are unverified proposals. */
(() => {
  const el = id => document.getElementById(id);
  const post = (path, body) => fetch('/api/v1/ball/' + path, {method:'POST', headers:{'Content-Type':'application/json'}, body: body && JSON.stringify(body)});
  const W = 1920, H = 1080, CW = 1200, CH = 675;
  const canvas = el('ball-canvas'), ctx = canvas.getContext('2d'), overview = el('ball-overview'), octx = overview.getContext('2d');
  const images = new Map();
  let clips = [], clip = null, idx = 0, center = [W / 2, H * 0.75], zoom = 4, busy = false;
  const status = text => { el('ball-status').textContent = text; };
  const frameName = () => clip.frames[idx].file;
  const label = (i = idx) => clip && clip.labels[clip.frames[i].file];
  const url = (i) => `/ball-media/${clip.id}/${clip.frames[i].file}`;
  function image(i) {
    const key = url(i); let img = images.get(key);
    if (!img) { img = new Image(); img.src = key; img.addEventListener('load', draw); images.set(key, img); }
    return img;
  }
  const lastKnown = () => { for (let i = idx - 1; i >= 0; i--) { const l = label(i); if (l && l.state === 'ball') return [l.x, l.y]; } return null; };
  function candidates() {
    const w = CW / zoom, h = CH / zoom, cands = clip.frames[idx].cands || [];
    return cands.filter(c => Math.abs(c[0] - center[0]) < w / 2 && Math.abs(c[1] - center[1]) < h / 2)
      .sort((a, b) => Math.hypot(a[0] - center[0], a[1] - center[1]) - Math.hypot(b[0] - center[0], b[1] - center[1])).slice(0, 9);
  }
  // The suggestion is the candidate that best continues the last labelled position (or the strongest one).
  let pickProbability = null;
  function suggestion() {
    pickProbability = null;
    // A path chosen by the trained re-ranker (prepared offline, field `pick`) comes first: it uses the people around and the motion of the ball, not only the score of one circle.
    const pick = clip.frames[idx].pick;
    if (pick) {
      pickProbability = pick[2];
      const near = (clip.frames[idx].cands || []).find(c => Math.hypot(c[0] - pick[0], c[1] - pick[1]) < 3);
      return near || pick;
    }
    const prev = lastKnown(); let best = null, bestValue = -1e9;
    for (const c of clip.frames[idx].cands || []) {
      const d = prev ? Math.hypot(c[0] - prev[0], c[1] - prev[1]) : 0;
      if (prev && d > 150) continue;
      const value = c[2] - (prev ? d / 200 : 0);
      if (value > bestValue) { bestValue = value; best = c; }
    }
    return best || (!prev ? (clip.frames[idx].cands || [])[0] || null : null);
  }
  const roundTo = v => Math.round(v * 10) / 10;
  const saveCandidate = (c, source) => save('ball', roundTo(c[0]), roundTo(c[1]), source);
  function drawGallery(img) {
    const box = el('ball-gallery'); box.replaceChildren();
    const sug = suggestion(), list = candidates();
    el('ball-suggest-info').textContent = sug ? (pickProbability !== null ? `추천: 모델이 공의 경로로 고른 곳(확률 ${Math.round(pickProbability * 100)}%, ${pickProbability >= 0.7 ? '강함' : '약함: 꼭 확인하세요'})` : `추천: 후보 점수 ${Math.round(sug[2] * 100)}점`) + (pickProbability === null && lastKnown() ? ' · 앞 프레임 위치에서 이어짐' : '') : '추천할 후보가 없습니다';
    list.forEach((c, n) => {
      const tile = document.createElement('button'); tile.type = 'button'; tile.className = 'ball-tile' + (sug && c === sug ? ' is-suggested' : '');
      const cv = document.createElement('canvas'); cv.width = 120; cv.height = 120; const g = cv.getContext('2d'); g.imageSmoothingEnabled = false;
      if (img.complete && img.naturalWidth) g.drawImage(img, c[0] - 30, c[1] - 30, 60, 60, 0, 0, 120, 120);
      g.strokeStyle = 'rgba(255,255,255,.5)'; g.beginPath(); g.moveTo(60, 50); g.lineTo(60, 56); g.moveTo(60, 64); g.lineTo(60, 70); g.moveTo(50, 60); g.lineTo(56, 60); g.moveTo(64, 60); g.lineTo(70, 60); g.stroke();
      const label = document.createElement('small'); label.textContent = `${n + 1}번 · ${Math.round(c[2] * 100)}점${sug && c === sug ? ' · 추천' : ''}`;
      tile.append(cv, label); tile.addEventListener('click', () => saveCandidate(c, 'tile')); box.append(tile);
    });
    const none = document.createElement('button'); none.type = 'button'; none.className = 'ball-tile ball-none-tile'; none.textContent = '이 중에 공 없음 (N)'; none.addEventListener('click', () => save('none')); box.append(none);
  }
  function draw() {
    if (!clip) return;
    const img = image(idx), w = CW / zoom, h = CH / zoom;
    center = [Math.min(W - w / 2, Math.max(w / 2, center[0])), Math.min(H - h / 2, Math.max(h / 2, center[1]))];
    const sx = center[0] - w / 2, sy = center[1] - h / 2;
    ctx.imageSmoothingEnabled = false; ctx.fillStyle = '#000'; ctx.fillRect(0, 0, CW, CH);
    if (img.complete && img.naturalWidth) ctx.drawImage(img, sx, sy, w, h, 0, 0, CW, CH);
    const toCanvas = (x, y) => [(x - sx) * zoom, (y - sy) * zoom];
    // positions labelled in the last few frames show where the ball was
    for (let k = 1; k <= 4; k++) { const l = idx - k >= 0 ? label(idx - k) : null; if (l && l.state === 'ball') { const [cx, cy] = toCanvas(l.x, l.y); ctx.fillStyle = `rgba(255,255,255,${0.5 - k * 0.1})`; ctx.beginPath(); ctx.arc(cx, cy, 5, 0, 7); ctx.fill(); } }
    const prev = lastKnown();
    ctx.font = '16px sans-serif';
    candidates().forEach((c, n) => {
      const [cx, cy] = toCanvas(c[0], c[1]), near = prev && Math.hypot(c[0] - prev[0], c[1] - prev[1]) < 90;
      ctx.strokeStyle = near ? '#ffd24f' : '#b8b8b8'; ctx.lineWidth = 2; ctx.beginPath(); ctx.arc(cx, cy, 16, 0, 7); ctx.stroke();
      ctx.fillStyle = near ? '#ffd24f' : '#e0e0e0'; ctx.fillText(String(n + 1), cx + 18, cy - 14);
    });
    const l = label();
    if (l && l.state === 'ball') {
      const [cx, cy] = toCanvas(l.x, l.y); ctx.strokeStyle = '#3dff6f'; ctx.lineWidth = 2;
      ctx.beginPath(); ctx.moveTo(cx - 14, cy); ctx.lineTo(cx + 14, cy); ctx.moveTo(cx, cy - 14); ctx.lineTo(cx, cy + 14); ctx.stroke();
    }
    ctx.fillStyle = 'rgba(0,0,0,.6)'; ctx.fillRect(0, 0, 330, 26); ctx.fillStyle = '#fff'; ctx.font = '14px sans-serif';
    ctx.fillText(`프레임 ${idx + 1}/${clip.frames.length} · ${l ? ({ball:'공 위치 저장됨', none:'공 안 보임', unsure:'불확실'})[l.state] : '아직 답 없음'}`, 8, 18);
    drawOverview(img, sx, sy, w, h);
    drawGallery(img);
    const imgLabel = clip.frames.filter((f, i) => clip.labels[f.file]).length;
    el('ball-frameinfo').textContent = `이 클립 ${imgLabel}/${clip.frames.length}프레임에 답함 · 후보 ${(clip.frames[idx].cands || []).length}개(자동 추천)`;
  }
  function drawOverview(img, sx, sy, w, h) {
    octx.fillStyle = '#000'; octx.fillRect(0, 0, 480, 270);
    if (img.complete && img.naturalWidth) octx.drawImage(img, 0, 0, 480, 270);
    octx.strokeStyle = '#ffd24f'; octx.lineWidth = 2; octx.strokeRect(sx / 4, sy / 4, w / 4, h / 4);
    octx.fillStyle = '#3dff6f';
    for (let i = 0; i < clip.frames.length; i++) { const l = label(i); if (l && l.state === 'ball') { octx.fillRect(l.x / 4 - 1, l.y / 4 - 1, 3, 3); } }
  }
  function go(i, keepCenter) {
    if (!clip) return;
    idx = Math.min(clip.frames.length - 1, Math.max(0, i));
    if (!keepCenter) {
      const l = label();
      const prev = l && l.state === 'ball' ? [l.x, l.y] : lastKnown();
      if (prev) center = prev;
      else { const c = (clip.frames[idx].cands || [])[0]; if (c) center = [c[0], c[1]]; }
    }
    draw(); if (idx + 1 < clip.frames.length) image(idx + 1);
  }
  async function save(state, x, y, source) {
    if (!clip || busy) return; busy = true;
    try {
      const body = {clip:clip.id, frame:frameName(), state, x: state === 'ball' ? x : null, y: state === 'ball' ? y : null};
      let r = await post('label', {...body, source: state === 'ball' ? (source || null) : null});
      // an older server does not know the "source" field: save the position without it rather than fail
      if (r.status === 422 && state === 'ball') r = await post('label', body);
      if (!r.ok) throw new Error();
      const saved = (await r.json()).saved;
      if (saved) clip.labels[frameName()] = saved; else delete clip.labels[frameName()];
    } catch (_) { status('저장하지 못했습니다. 서버 연결을 확인하세요.'); busy = false; return; }
    busy = false; refreshList();
    if (state !== 'clear' && el('ball-auto').checked) go(idx + 1); else draw();
  }
  function toImage(event) {
    const r = canvas.getBoundingClientRect(), w = CW / zoom, h = CH / zoom;
    return [center[0] - w / 2 + (event.clientX - r.left) / r.width * w, center[1] - h / 2 + (event.clientY - r.top) / r.height * h];
  }
  function refreshList() {
    const box = el('ball-clips'); box.replaceChildren();
    for (const c of clips) {
      const b = document.createElement('button'); b.type = 'button'; b.className = 'ev-item' + (clip && clip.id === c.id ? ' is-current' : '') + (c.labeled >= c.frames ? ' has-label' : '');
      const cur = clip && clip.id === c.id ? clip : null;
      const done = cur ? cur.frames.filter(f => cur.labels[f.file]).length : c.labeled;
      b.innerHTML = ''; const t = document.createElement('strong'); t.textContent = `${c.id} · ${c.camera} · ${Math.floor(c.start / 60)}:${String(c.start % 60).padStart(2, '0')}`;
      const s = document.createElement('small'); s.textContent = `${done}/${c.frames}프레임 답함`; b.append(t, s);
      b.addEventListener('click', () => open(c.id)); box.append(b);
    }
    const total = clips.reduce((a, c) => a + c.frames, 0), done = clips.reduce((a, c) => a + (clip && clip.id === c.id ? clip.frames.filter(f => clip.labels[f.file]).length : c.labeled), 0);
    status(`전체 ${done} / ${total}프레임에 답함`);
  }
  async function open(id) {
    try {
      const r = await post('clip', {id}); if (!r.ok) throw new Error();
      clip = await r.json();
    } catch (_) { status('클립을 불러오지 못했습니다.'); return; }
    el('ball-main').hidden = false; el('ball-title').textContent = `클립 ${clip.id} · 카메라 ${clip.camera} · 경기 구간 ${Math.floor(clip.start / 60)}:${String(clip.start % 60).padStart(2, '0')}부터 10초(초당 ${clip.fps}프레임)`;
    const first = clip.frames.findIndex(f => !clip.labels[f.file]); center = [W / 2, H * 0.75];
    go(first >= 0 ? first : 0); refreshList();
  }

  canvas.addEventListener('click', event => {
    const [x, y] = toImage(event), reach = 22 / zoom;
    // a click close to a proposed circle uses the circle's centre; elsewhere the exact click is kept
    const near = (clip.frames[idx].cands || []).map(c => [c, Math.hypot(c[0] - x, c[1] - y)]).filter(p => p[1] <= reach).sort((a, b) => a[1] - b[1])[0];
    if (near) saveCandidate(near[0], 'snap'); else save('ball', roundTo(x), roundTo(y), 'manual');
  });
  el('ball-accept').addEventListener('click', () => { const s = suggestion(); if (s) saveCandidate(s, 'suggestion'); });
  overview.addEventListener('click', event => { const r = overview.getBoundingClientRect(); center = [(event.clientX - r.left) / r.width * W, (event.clientY - r.top) / r.height * H]; draw(); });
  el('ball-prev').addEventListener('click', () => go(idx - 1)); el('ball-next').addEventListener('click', () => go(idx + 1));
  el('ball-none').addEventListener('click', () => save('none')); el('ball-unsure').addEventListener('click', () => save('unsure')); el('ball-clear').addEventListener('click', () => save('clear'));
  el('ball-zoom').addEventListener('change', () => { zoom = Number(el('ball-zoom').value); draw(); });
  el('ball-export').addEventListener('click', async () => {
    const out = [];
    for (const c of clips) { const r = await post('clip', {id:c.id}); if (!r.ok) continue; const d = await r.json(); out.push({id:d.id, camera:d.camera, start:d.start, fps:d.fps, width:d.width, height:d.height, labels:d.labels}); }
    const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([JSON.stringify({exported:new Date().toISOString(), clips:out}, null, 1)], {type:'application/json'})); a.download = 'ball_labels.json'; a.click();
  });
  document.addEventListener('keydown', event => {
    if (event.ctrlKey || event.altKey || event.metaKey || !clip || document.body.dataset.mode === 'verify') return;
    if (['INPUT', 'SELECT', 'TEXTAREA'].includes(event.target && event.target.tagName)) return;
    const k = event.key.toLowerCase();
    if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); const s = suggestion(); if (s) saveCandidate(s, 'suggestion'); return; }
    if (k >= '1' && k <= '9') { const c = candidates()[Number(k) - 1]; if (c) { event.preventDefault(); save('ball', Math.round(c[0] * 10) / 10, Math.round(c[1] * 10) / 10, 'key'); } }
    else if (k === 'n') save('none'); else if (k === 'u') save('unsure'); else if (k === 'backspace' || k === 'delete') { event.preventDefault(); save('clear'); }
    else if (event.key === 'ArrowRight') { event.preventDefault(); go(idx + 1); } else if (event.key === 'ArrowLeft') { event.preventDefault(); go(idx - 1); }
    else if (k === 'w' || k === 'a' || k === 's' || k === 'd') { const step = 120 / (zoom / 4); center = [center[0] + (k === 'd' ? step : k === 'a' ? -step : 0), center[1] + (k === 's' ? step : k === 'w' ? -step : 0)]; draw(); }
  });
  (async () => {
    try { const r = await post('list'); if (!r.ok) throw new Error(); const d = await r.json(); clips = d.clips; }
    catch (_) { status('공 클립을 불러오지 못했습니다. 서버가 새 버전인지 확인하세요.'); return; }
    if (!clips.length) { status('아직 준비된 공 클립이 없습니다.'); return; }
    refreshList(); open(clips[0].id);
  })();
})();
