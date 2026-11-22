/* Pitch calibration and a still-frame minimap. Everything here is a measurement aid: pitch size is an
   estimate, calibration quality depends on the clicked landmarks, and nothing is saved as a label. */
(() => {
  const el = id => document.getElementById(id);
  const panel = el('minimap-panel'), stage = el('label-stage'), image = el('label-image');
  if (!panel || !stage || !image) return;
  const hooks = (globalThis.__reviewHooks = globalThis.__reviewHooks || {});
  const post = (url, body) => fetch('/api/v1/training-labels/' + url, {method:'POST', headers:{'Content-Type':'application/json'}, body: body && JSON.stringify(body)});
  const DEFAULTS = {length:105, width:68, circle_r:9.15, goal_width:7.32, pa_depth:16.5, pa_width:40.3, ga_depth:5.5, ga_width:18.3};
  const DIM_LABELS = {length:'길이(골라인 사이)', width:'폭(터치라인 사이)', circle_r:'센터서클 반지름', goal_width:'골대 폭',
    pa_depth:'페널티 박스 깊이', pa_width:'페널티 박스 폭', ga_depth:'골 에어리어 깊이', ga_width:'골 에어리어 폭'};
  const LIMITS = {length:[20,130], width:[15,100], circle_r:[1,15], goal_width:[1.5,9], pa_depth:[3,25], pa_width:[8,50], ga_depth:[1,10], ga_width:[4,25]};
  let dims = {...DEFAULTS}, calibrations = {}, apiReady = false, scene = null, scenes = [], saved = {};
  let points = [], clicking = false, solved = null;

  // ---- pitch model: X along the length (left negative), Y across the width (near touchline positive) ----
  function landmarks(d) {
    const out = [{id:'center', label:'센터 스폿', X:0, Y:0}, {id:'half_near', label:'하프라인 · 가까운 터치라인', X:0, Y:d.width/2},
      {id:'half_far', label:'하프라인 · 먼 터치라인', X:0, Y:-d.width/2},
      {id:'circle_left', label:'센터서클 왼쪽', X:-d.circle_r, Y:0}, {id:'circle_right', label:'센터서클 오른쪽', X:d.circle_r, Y:0},
      {id:'circle_near', label:'센터서클 가까운쪽', X:0, Y:d.circle_r}, {id:'circle_far', label:'센터서클 먼쪽', X:0, Y:-d.circle_r}];
    for (const [s, sx, sn] of [['l',-1,'왼쪽'], ['r',1,'오른쪽']]) for (const [n, sy, nn] of [['near',1,'가까운'], ['far',-1,'먼']]) {
      const g = `${sn} ${nn}`, L = d.length/2;
      out.push({id:`corner_${s}_${n}`, label:`${g} 코너`, X:sx*L, Y:sy*d.width/2},
        {id:`post_${s}_${n}`, label:`${g} 골대 기둥`, X:sx*L, Y:sy*d.goal_width/2},
        {id:`pa_${s}_${n}`, label:`${g} 페널티 박스 안쪽 모서리`, X:sx*(L-d.pa_depth), Y:sy*d.pa_width/2},
        {id:`pa_goalline_${s}_${n}`, label:`${g} 페널티 박스·골라인 만나는 점`, X:sx*L, Y:sy*d.pa_width/2},
        {id:`ga_${s}_${n}`, label:`${g} 골 에어리어 안쪽 모서리`, X:sx*(L-d.ga_depth), Y:sy*d.ga_width/2},
        {id:`ga_goalline_${s}_${n}`, label:`${g} 골 에어리어·골라인 만나는 점`, X:sx*L, Y:sy*d.ga_width/2});
    }
    return out;
  }
  function pitchLines(d) {
    const L = d.length/2, W = d.width/2, lines = [[[-L,-W],[L,-W],[L,W],[-L,W],[-L,-W]], [[0,-W],[0,W]]];
    const circle = []; for (let i = 0; i <= 48; i++) circle.push([d.circle_r*Math.cos(i/48*2*Math.PI), d.circle_r*Math.sin(i/48*2*Math.PI)]);
    lines.push(circle);
    for (const sx of [-1, 1]) {
      const pd = L - d.pa_depth, gd = L - d.ga_depth;
      lines.push([[sx*L,-d.pa_width/2],[sx*pd,-d.pa_width/2],[sx*pd,d.pa_width/2],[sx*L,d.pa_width/2]],
        [[sx*L,-d.ga_width/2],[sx*gd,-d.ga_width/2],[sx*gd,d.ga_width/2],[sx*L,d.ga_width/2]],
        [[sx*L,-d.goal_width/2],[sx*(L+1.5),-d.goal_width/2],[sx*(L+1.5),d.goal_width/2],[sx*L,d.goal_width/2]]);
    }
    return lines;
  }

  // ---- homography: normalized reference-frame image coordinates -> pitch metres (least squares) ----
  function solveH(pairs) {
    const n = 8, N = Array.from({length:n}, () => new Array(n + 1).fill(0));
    for (const {u, v, X, Y} of pairs) {
      for (const [row, rhs] of [[[u, v, 1, 0, 0, 0, -u*X, -v*X], X], [[0, 0, 0, u, v, 1, -u*Y, -v*Y], Y]]) {
        for (let i = 0; i < n; i++) { for (let j = 0; j < n; j++) N[i][j] += row[i]*row[j]; N[i][n] += row[i]*rhs; }
      }
    }
    for (let c = 0; c < n; c++) {
      let p = c; for (let r = c + 1; r < n; r++) if (Math.abs(N[r][c]) > Math.abs(N[p][c])) p = r;
      if (Math.abs(N[p][c]) < 1e-12) return null;
      [N[c], N[p]] = [N[p], N[c]];
      for (let r = 0; r < n; r++) if (r !== c) { const f = N[r][c]/N[c][c]; for (let k = c; k <= n; k++) N[r][k] -= f*N[c][k]; }
    }
    const h = N.map((row, i) => row[n]/row[i]);
    return [h[0], h[1], h[2], h[3], h[4], h[5], h[6], h[7], 1];
  }
  const applyH = (H, u, v) => { const w = H[6]*u + H[7]*v + H[8]; return w ? [(H[0]*u + H[1]*v + H[2])/w, (H[3]*u + H[4]*v + H[5])/w, w] : null; };
  function invert(H) {
    const [a, b, c, d, e, f, g, h, i] = H, A = e*i - f*h, B = -(d*i - f*g), C = d*h - e*g, det = a*A + b*B + c*C;
    if (Math.abs(det) < 1e-18) return null;
    return [A, -(b*i - c*h), b*f - c*e, B, a*i - c*g, -(a*f - c*d), C, -(a*h - b*g), a*e - b*d].map(v => v/det);
  }

  // ---- frame <-> reference-frame mapping (small background similarity transform per scene) ----
  const size = () => [image.naturalWidth || 1920, image.naturalHeight || 1080];
  function toRef(u, v) {
    const [W, H] = size(), bg = scene && scene.bg, x = u*W, y = v*H;
    if (!bg) return [u, v];
    const [a, b, tx, ty] = bg; return [(a*x - b*y + tx)/W, (b*x + a*y + ty)/H];
  }
  function fromRef(u, v) {
    const [W, H] = size(), bg = scene && scene.bg, x = u*W, y = v*H;
    if (!bg) return [u, v];
    const [a, b, tx, ty] = bg, k = a*a + b*b;
    return [(a*(x - tx) + b*(y - ty))/k/W, (-b*(x - tx) + a*(y - ty))/k/H];
  }
  const toMetres = (p) => { if (!solved) return null; const r = applyH(solved.H, p[0], p[1]); return r && r[2] > 0 ? [r[0], r[1]] : null; };

  // ---- calibration state ----
  const camera = () => scene && scene.camera;
  function fit(d) {
    if (points.length < 4) return null;
    const byId = Object.fromEntries(landmarks(d).map(l => [l.id, l]));
    const pairs = points.filter(p => byId[p.landmark]).map(p => ({u:p.x, v:p.y, X:byId[p.landmark].X, Y:byId[p.landmark].Y, id:p.landmark}));
    let H = pairs.length >= 4 ? solveH(pairs) : null;
    if (!H) return null;
    // A homography and its negative are the same mapping. With the last entry fixed to 1 the scale factor w of the clicked
    // points is often negative (the image corner lies above the horizon), which made every point look "behind the camera".
    if (pairs.reduce((s, q) => s + H[6]*q.u + H[7]*q.v + H[8], 0) < 0) H = H.map(v => -v);
    const errors = pairs.map(q => { const r = applyH(H, q.u, q.v); return r ? Math.hypot(r[0] - q.X, r[1] - q.Y) : NaN; });
    const rms = Math.sqrt(errors.reduce((s, e) => s + e*e, 0)/errors.length);
    return isFinite(rms) ? {H, errors, ids: pairs.map(q => q.id), rms} : null;
  }
  function recompute() { solved = fit(dims); }
  // Fit length and width from the clicked points (the standard-size penalty area, goal area and circle stay fixed).
  function estimateSize() {
    if (points.length < 7) { status.textContent = '길이·폭 자동 추정은 기준점이 7개 이상일 때 믿을 만합니다(4개는 항상 오차 0이 되어 정보가 없습니다).'; return; }
    let best = null;
    for (let L = 60; L <= 125; L++) for (let W = 40; W <= 85; W++) {
      const f = fit({...dims, length:L, width:W});
      if (f && (!best || f.rms < best.f.rms)) best = {L, W, f};
    }
    if (!best) { status.textContent = '길이·폭을 추정하지 못했습니다. 기준점을 더 넓게 찍어 주세요.'; return; }
    const before = solved ? solved.rms : NaN;
    dims.length = best.L; dims.width = best.W; try { localStorage.setItem('pitch-dims', JSON.stringify(dims)); } catch (_) {}
    buildDims(); buildSelect(); recompute(); refresh();
    status.textContent = `추정 결과: 길이 ${best.L}m, 폭 ${best.W}m (오차 ${isFinite(before) ? before.toFixed(2) + 'm에서 ' : ''}${best.f.rms.toFixed(2)}m). 점이 많고 넓게 퍼질수록 믿을 만하며, 실제 크기를 아시면 그 값을 쓰세요.`;
  }
  function loadCalibration() {
    const cam = camera(), c = cam && calibrations[cam];
    if (c) { points = c.points.map(p => ({...p})); dims = {...DEFAULTS, ...c.pitch}; } else points = [];
    recompute();
  }

  // ---- UI: dimensions, landmark picker, points list ----
  const dimsBox = el('minimap-dims'), select = el('minimap-landmark'), list = el('minimap-points'), status = el('minimap-status');
  function buildDims() {
    dimsBox.replaceChildren();
    for (const key of Object.keys(DEFAULTS)) {
      const label = document.createElement('label'), input = document.createElement('input');
      label.textContent = DIM_LABELS[key] + ' '; input.type = 'number'; input.step = '0.1'; input.min = LIMITS[key][0]; input.max = LIMITS[key][1];
      input.value = dims[key]; input.dataset.key = key;
      input.addEventListener('change', () => {
        const v = Number(input.value);
        if (!(v >= LIMITS[key][0] && v <= LIMITS[key][1])) { input.value = dims[key]; return; }
        dims[key] = v; try { localStorage.setItem('pitch-dims', JSON.stringify(dims)); } catch (_) {}
        buildSelect(); recompute(); refresh();
      });
      label.append(input); dimsBox.append(label);
    }
  }
  function buildSelect() {
    const current = select.value; select.replaceChildren();
    for (const l of landmarks(dims)) { const o = document.createElement('option'); o.value = l.id; o.textContent = l.label; select.append(o); }
    if (current) select.value = current;
  }
  function renderPoints() {
    list.replaceChildren();
    const names = Object.fromEntries(landmarks(dims).map(l => [l.id, l.label]));
    points.forEach((p, i) => {
      const li = document.createElement('li'); const err = solved && solved.ids.indexOf(p.landmark) >= 0 ? solved.errors[solved.ids.indexOf(p.landmark)] : null;
      li.textContent = `${names[p.landmark] || p.landmark}${err == null || !isFinite(err) ? '' : ` · 오차 ${err.toFixed(2)}m`}`;
      const del = document.createElement('button'); del.type = 'button'; del.textContent = '삭제';
      del.addEventListener('click', () => { points.splice(i, 1); recompute(); refresh(); });
      li.append(' ', del); list.append(li);
    });
  }

  // ---- overlay on the frame: clicked landmarks and the projected pitch lines ----
  const overlay = document.createElement('canvas'); overlay.className = 'pitch-region-canvas calib-canvas'; stage.append(overlay);
  function paintOverlay() {
    const ctx = overlay.getContext && overlay.getContext('2d'); if (!ctx) return;
    const [W, H] = size(); overlay.width = W; overlay.height = H; ctx.clearRect(0, 0, W, H);
    if (el('minimap-lines').checked && solved) {
      const inv = invert(solved.H);
      if (inv) {
        ctx.lineWidth = Math.max(2, W/700); ctx.strokeStyle = '#4fd1ff'; ctx.setLineDash([]);
        for (const line of pitchLines(dims)) {
          ctx.beginPath(); let pen = false;
          for (const [X, Y] of line) {
            const r = applyH(inv, X, Y);
            if (!r || r[2] <= 0) { pen = false; continue; }
            const [u, v] = fromRef(r[0], r[1]), px = u*W, py = v*H;
            if (Math.abs(px) > W*3 || Math.abs(py) > H*3) { pen = false; continue; }
            if (pen) ctx.lineTo(px, py); else { ctx.moveTo(px, py); pen = true; }
          }
          ctx.stroke();
        }
      }
    }
    ctx.font = `${Math.round(W/70)}px sans-serif`; ctx.fillStyle = '#ffd24f'; ctx.strokeStyle = '#000';
    for (const p of points) {
      const [u, v] = fromRef(p.x, p.y), px = u*W, py = v*H;
      ctx.beginPath(); ctx.arc(px, py, Math.max(4, W/260), 0, 7); ctx.fill(); ctx.lineWidth = 1; ctx.stroke();
    }
  }

  // ---- minimap ----
  const canvas = el('minimap-canvas');
  function classify(p) {
    const s = saved[p.id];
    if (s) {
      if (['spectator', 'shadow', 'duplicate', 'unknown'].includes(s.role)) return null;
      if (s.role === 'referee') return {k:'ref', saved:true};
      return {k:s.team_group === 'team_a' ? 'a' : s.team_group === 'team_b' ? 'b' : 'u', saved:true, gk:s.role === 'goalkeeper'};
    }
    const t = hooks.tierOf ? hooks.tierOf(p) : 'todo';
    if (t === 'spectator') return null;
    return {k:t === 'team_a' ? 'a' : t === 'team_b' ? 'b' : t === 'referee' ? 'ref' : 'u', saved:false};
  }
  function hull(pts) {
    const p = [...pts].sort((x, y) => x[0] - y[0] || x[1] - y[1]); if (p.length < 3) return p;
    const cross = (o, a, b) => (a[0] - o[0])*(b[1] - o[1]) - (a[1] - o[1])*(b[0] - o[0]), lower = [], upper = [];
    for (const q of p) { while (lower.length >= 2 && cross(lower[lower.length-2], lower[lower.length-1], q) <= 0) lower.pop(); lower.push(q); }
    for (const q of [...p].reverse()) { while (upper.length >= 2 && cross(upper[upper.length-2], upper[upper.length-1], q) <= 0) upper.pop(); upper.push(q); }
    return lower.slice(0, -1).concat(upper.slice(0, -1));
  }
  const area = h => Math.abs(h.reduce((s, p, i) => s + p[0]*h[(i+1) % h.length][1] - h[(i+1) % h.length][0]*p[1], 0))/2;
  function teamStats(pts) {
    const n = pts.length; if (n < 4) return null;
    const xs = pts.map(p => p[0]), ys = pts.map(p => p[1]);
    let nn = 0; for (const p of pts) nn += Math.min(...pts.filter(q => q !== p).map(q => Math.hypot(p[0] - q[0], p[1] - q[1])));
    return {n, cx:xs.reduce((a, b) => a + b)/n, cy:ys.reduce((a, b) => a + b)/n, depth:Math.max(...xs) - Math.min(...xs),
      width:Math.max(...ys) - Math.min(...ys), hull:area(hull(pts)), nn:nn/n};
  }
  function drawMinimap() {
    const ctx = canvas.getContext && canvas.getContext('2d'); if (!ctx) return;
    const cw = canvas.width, ch = canvas.height, pad = 28, s = Math.min((cw - 2*pad)/dims.length, (ch - 2*pad)/dims.width);
    const X = x => cw/2 + x*s, Y = y => ch/2 + y*s;
    ctx.fillStyle = '#1f5a2a'; ctx.fillRect(0, 0, cw, ch); ctx.strokeStyle = '#e9f5e5'; ctx.lineWidth = 1.5; ctx.setLineDash([]);
    for (const line of pitchLines(dims)) { ctx.beginPath(); line.forEach(([x, y], i) => i ? ctx.lineTo(X(x), Y(y)) : ctx.moveTo(X(x), Y(y))); ctx.stroke(); }
    const stats = el('minimap-stats'); stats.replaceChildren();
    if (!solved) { ctx.fillStyle = '#fff'; ctx.font = '14px sans-serif'; ctx.fillText('경기장 보정이 없어 사람 위치를 그리지 않습니다.', 16, 24); return; }
    if (solved.rms > 5) {
      // an inconsistent calibration would produce confident-looking but wrong positions and metrics
      ctx.fillStyle = '#ffb3b3'; ctx.font = '14px sans-serif';
      ctx.fillText(`보정 오차가 ${solved.rms.toFixed(1)}m로 커서 사람 위치와 지표를 그리지 않습니다.`, 16, 24);
      ctx.fillText('기준점을 잘못 골랐거나 경기장 크기가 맞지 않을 수 있습니다. 오차가 큰 점을 지우거나 크기를 고쳐 보세요.', 16, 46);
      const warnBig = document.createElement('p'); warnBig.textContent = '보정 오차가 5m를 넘으면 위치와 지표를 내지 않습니다. 아래 점 목록에서 오차가 가장 큰 점부터 확인하세요.';
      stats.append(warnBig); return;
    }
    const groups = {a:[], b:[], ref:[], u:[]}, counts = {a:0, b:0, ref:0, u:0}, hint = {a:0, b:0, ref:0, u:0};
    let skipped = 0;
    const colors = {a:'#d7ff3a', b:'#9fb3c8', ref:'#ff6fae', u:'#ffffff'};
    for (const p of (hooks.people ? hooks.people() : [])) {
      const c = classify(p); if (!c) continue;
      const [x1, , x2, y2] = p.bbox, [ru, rv] = toRef((x1 + x2)/2, y2), m = toMetres([ru, rv]);
      if (!m || Math.abs(m[0]) > dims.length/2 + 4 || Math.abs(m[1]) > dims.width/2 + 4) { skipped++; continue; }
      counts[c.k]++; if (!c.saved) hint[c.k]++; groups[c.k].push(m);
      ctx.beginPath(); ctx.arc(X(m[0]), Y(m[1]), c.k === 'ref' ? 6 : 5, 0, 7);
      if (c.saved) { ctx.fillStyle = colors[c.k]; ctx.fill(); ctx.strokeStyle = '#000'; ctx.lineWidth = 1; ctx.stroke(); }
      else { ctx.strokeStyle = colors[c.k]; ctx.lineWidth = 2; ctx.stroke(); }
    }
    ctx.fillStyle = '#fff'; ctx.font = '12px sans-serif'; ctx.fillText('위: 먼 터치라인 · 아래: 가까운 터치라인(카메라 쪽)', 10, ch - 8);
    const lines = [['a', '팀 A'], ['b', '팀 B']].map(([k, name]) => {
      const st = teamStats(groups[k]);
      const head = `${name}: ${counts[k]}명(확정 ${counts[k] - hint[k]}명, 추천 ${hint[k]}명)`;
      return st ? `${head} · 깊이(좌우) ${st.depth.toFixed(1)}m · 폭(위아래) ${st.width.toFixed(1)}m · 점유 면적 ${st.hull.toFixed(0)}㎡ · 가장 가까운 동료와 평균 ${st.nn.toFixed(1)}m` : `${head} · 4명 미만이라 지표를 내지 않습니다`;
    });
    lines.push(`심판 ${counts.ref}명, 팀 미정 ${counts.u}명(흰 점) 표시. 채운 점은 사용자님이 저장한 답, 빈 점은 자동 추천입니다.`);
    if (skipped) lines.push(`경기장 밖으로 계산되어 그리지 않은 사람 ${skipped}명: 기준점이 한쪽에 몰렸거나 경기장 크기가 실제와 다르면 많아집니다. 보정 선을 겹쳐 보고 점을 더 넓게 찍어 보세요.`);
    for (const t of lines) { const p = document.createElement('p'); p.textContent = t; stats.append(p); }
    const warn = document.createElement('p');
    warn.textContent = `보정 오차(기준점 평균) ${solved.rms.toFixed(2)}m · 경기장 크기는 추정값이라 모든 거리가 같은 비율로 틀릴 수 있습니다. 먼 선수일수록 오차가 큽니다. 한 장면의 정지 화면 지표이며 전술 평가가 아닙니다.`;
    stats.append(warn);
  }

  function refresh() {
    const cam = camera();
    status.textContent = !apiReady ? '' : !scene ? '장면을 불러오는 중입니다.' : !cam
      ? '이 장면은 카메라 설정을 알 수 없어(카메라를 옮기는 중) 보정을 쓸 수 없습니다.'
      : `카메라 설정 ${cam} · 기준점 ${points.length}개${solved ? ` · 오차 ${solved.rms.toFixed(2)}m` : points.length >= 4 ? ' · 계산 실패(점이 한 직선에 가깝지 않은지 확인)' : ' · 4개 이상 찍어야 계산됩니다'}${calibrations[cam] ? ' · 저장됨' : ' · 아직 저장 안 됨'}`;
    el('minimap-click').textContent = clicking ? '기준점 찍기 끝내기' : '기준점 찍기 시작';
    renderPoints(); paintOverlay(); drawMinimap(); paintHud();
  }

  // ---- floating helper while clicking: which landmark is next, shown on a small pitch drawing ----
  // The panel sits at the bottom of the page, so this box stays on screen while the photo is scrolled.
  const hud = document.createElement('div'); hud.className = 'calib-hud'; hud.hidden = true;
  const hudTitle = document.createElement('p'), hudCount = document.createElement('p'), hudCanvas = document.createElement('canvas'), hudBar = document.createElement('div');
  hudTitle.className = 'calib-hud-title'; hudCount.className = 'calib-hud-count'; hudCanvas.width = 260; hudCanvas.height = 170; hudBar.className = 'calib-hud-bar';
  const hudButton = (text, onClick) => { const b = document.createElement('button'); b.type = 'button'; b.textContent = text; b.addEventListener('click', onClick); hudBar.append(b); return b; };
  hudButton('건너뛰기 ▶', () => { select.selectedIndex = (select.selectedIndex + 1) % Math.max(1, select.options.length); refresh(); });
  hudButton('마지막 점 취소', () => { points.pop(); recompute(); refresh(); });
  hudButton('좌우 옮기기', () => { hud.classList.toggle('is-left'); });
  hudButton('찍기 끝내기', () => { clicking = false; stage.classList.remove('calib-mode'); refresh(); });
  hud.append(hudTitle, hudCount, hudCanvas, hudBar); (document.body || stage).append(hud);
  function paintHud() {
    hud.hidden = !clicking; if (!clicking) return;
    const all = landmarks(dims), target = all.find(l => l.id === select.value), done = new Set(points.map(p => p.landmark));
    hudTitle.textContent = target ? `지금 찍을 점: ${target.label}${done.has(target.id) ? ' (이미 찍음, 다시 찍으면 바뀝니다)' : ''}` : '찍을 점을 고르세요';
    hudCount.textContent = `찍은 점 ${points.length}개 · 6~8개를 서로 멀리 떨어진 곳에 찍어 주세요 · 그림의 위쪽이 먼 터치라인, 아래쪽이 카메라 쪽입니다`;
    const ctx = hudCanvas.getContext && hudCanvas.getContext('2d'); if (!ctx) return;
    const w = hudCanvas.width, h = hudCanvas.height, L = dims.length / 2, W = dims.width / 2, pad = 10, s = Math.min((w - 2 * pad) / (2 * L), (h - 2 * pad) / (2 * W));
    const at = (X, Y) => [w / 2 + X * s, h / 2 + Y * s];
    ctx.fillStyle = '#1f5a2a'; ctx.fillRect(0, 0, w, h); ctx.strokeStyle = '#e9f5e5'; ctx.lineWidth = 1.2; ctx.setLineDash([]);
    for (const line of pitchLines(dims)) { ctx.beginPath(); line.forEach(([X, Y], i) => { const [x, y] = at(X, Y); if (i) ctx.lineTo(x, y); else ctx.moveTo(x, y); }); ctx.stroke(); }
    for (const l of all) if (done.has(l.id) && l.id !== (target && target.id)) { const [x, y] = at(l.X, l.Y); ctx.fillStyle = '#7bd88f'; ctx.beginPath(); ctx.arc(x, y, 3.5, 0, 7); ctx.fill(); }
    if (target) { const [x, y] = at(target.X, target.Y); ctx.strokeStyle = '#ff5a5a'; ctx.lineWidth = 2.5; ctx.beginPath(); ctx.arc(x, y, 9, 0, 7); ctx.stroke(); ctx.fillStyle = '#ff5a5a'; ctx.beginPath(); ctx.arc(x, y, 4, 0, 7); ctx.fill(); }
  }
  select.addEventListener('change', () => refresh());

  // ---- interactions ----
  el('minimap-click').addEventListener('click', () => {
    if (!camera()) { status.textContent = '이 장면에서는 보정할 수 없습니다. 다른 장면으로 이동하세요.'; return; }
    clicking = !clicking; stage.classList.toggle('calib-mode', clicking); refresh();
  });
  stage.addEventListener('click', event => {
    if (!clicking) return;
    if (stage.className.includes('review-draw-mode')) { status.textContent = '다른 그리기 도구를 먼저 끝내세요.'; return; }
    event.preventDefault(); event.stopPropagation();
    const rect = image.getBoundingClientRect(); if (!rect.width || !rect.height) return;
    const [x, y] = toRef((event.clientX - rect.left)/rect.width, (event.clientY - rect.top)/rect.height);
    const id = select.value; points = points.filter(p => p.landmark !== id); points.push({landmark:id, x, y});
    if (select.selectedIndex < select.options.length - 1) select.selectedIndex += 1;
    recompute(); refresh();
  }, true);
  el('minimap-estimate').addEventListener('click', estimateSize);
  el('minimap-undo').addEventListener('click', () => { points.pop(); recompute(); refresh(); });
  el('minimap-lines').addEventListener('change', paintOverlay);
  el('minimap-save').addEventListener('click', async () => {
    const cam = camera(); if (!cam) { status.textContent = '이 장면은 카메라 설정을 알 수 없어 보정을 저장할 수 없습니다. 상태 줄에 카메라 설정이 표시되는 장면에서 하세요.'; return; }
    if (points.length < 4) { status.textContent = '기준점을 4개 이상 찍어 주세요.'; return; }
    try {
      const r = await post('calibration', {setting:cam, points, pitch:dims, ref_token:scene.token});
      if (!r.ok) throw new Error(); calibrations = (await r.json()).calibrations || {};
      status.textContent = '보정을 저장했습니다.'; refresh();
    } catch (_) { status.textContent = '보정을 저장하지 못했습니다. 기준점이 서로 다른 4개 이상인지 확인하세요.'; }
  });
  el('minimap-clear').addEventListener('click', async () => {
    const cam = camera(); if (!cam) { status.textContent = '이 장면은 카메라 설정을 알 수 없어 지울 보정이 없습니다.'; return; }
    // a saved calibration is replaced for every scene of this camera setting, so ask first
    if (calibrations[cam] && !window.confirm(`${cam}의 저장된 보정을 지울까요? 이 카메라 설정의 모든 장면에 영향을 줍니다.`)) return;
    try {
      const r = await post('calibration', {setting:cam, points:[], pitch:dims}); if (!r.ok) throw new Error();
      calibrations = (await r.json()).calibrations || {}; points = []; recompute(); refresh();
    } catch (_) { status.textContent = '보정을 지우지 못했습니다.'; }
  });

  hooks.minimapScene = async token => {
    try {
      const [s, c, l] = await Promise.all([post('scenes'), post('calibrations'), post('scene-labels', {token})]);
      if (!s.ok || !c.ok) throw new Error();
      scenes = (await s.json()).scenes || []; calibrations = (await c.json()).calibrations || {};
      saved = {}; if (l.ok) for (const x of (await l.json()).labels || []) saved[x.track_id] = x;
      apiReady = true; panel.hidden = false;
    } catch (_) { apiReady = false; panel.hidden = true; return; }
    if (sessionStorage.getItem('training-label-snapshot') !== token) return;
    scene = scenes.find(x => x.token === token) || null; clicking = false; stage.classList.remove('calib-mode');
    loadCalibration(); buildDims(); buildSelect(); refresh();
  };
  let labelTimer = null;
  hooks.changed = () => {
    if (!apiReady || !scene) return;
    paintOverlay(); drawMinimap();
    // saved answers change while reviewing: refresh them shortly after the last change
    clearTimeout(labelTimer); const token = scene.token;
    labelTimer = setTimeout(async () => {
      try {
        const l = await post('scene-labels', {token}); if (!l.ok || !scene || scene.token !== token) return;
        const next = {}; for (const x of (await l.json()).labels || []) next[x.track_id] = x;
        if (JSON.stringify(next) !== JSON.stringify(saved)) { saved = next; drawMinimap(); }
      } catch (_) {}
    }, 800);
  };
  hooks.minimapMath = {solveH, applyH, invert, landmarks, pitchLines, setPoints(p, d) { points = p; dims = {...dims, ...d}; }, fit, estimateSize};
  buildDims(); buildSelect();
})();
