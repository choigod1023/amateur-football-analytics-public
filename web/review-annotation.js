/* Optional review tools. Labels remain review data until a separate training run. */
(() => {
  const el = id => document.getElementById(id);
  const stage = el('label-stage'), image = el('label-image'), role = el('label-role');
  if (!stage || !image || !role || !el('label-message')) return;
  const message = text => { el('label-message').textContent = text; };

  for (const [value, text] of [['spectator','관중'],['shadow','그림자·사물'],['duplicate','중복 상자']]) {
    if (![...role.options].some(option => option.value === value)) {
      const option = document.createElement('option'); option.value = value; option.textContent = text; role.append(option);
    }
  }
  role.addEventListener('change', () => {
    if (['spectator','shadow','duplicate'].includes(role.value)) {
      el('label-team').value = 'unknown'; el('label-shirt').value = 'unknown';
      const detail = el('label-shirt-detail'); if (detail) detail.value = '';
      message('이 항목은 선수로 세지 않고 선택한 오탐 유형으로 저장합니다.');
    }
  });
  for (const id of ['label-team','label-shirt']) el(id).addEventListener('change', () => {
    if (['spectator','shadow','duplicate'].includes(role.value)) {
      el(id).value = 'unknown'; message('오탐 상자는 팀과 옷 색을 지정하지 않습니다.');
    }
  });

  const tools = document.createElement('div'); tools.className = 'review-box-tools';
  const toggle = document.createElement('button'), cancel = document.createElement('button');
  for (const button of [toggle, cancel]) button.type = 'button';
  toggle.textContent = '놓친 사람 상자 추가'; cancel.textContent = '상자 추가 끝내기';
  cancel.hidden = true;
  tools.append(toggle, cancel); stage.parentElement.before(tools);
  const draft = document.createElement('div'); draft.className = 'review-box-draft'; draft.hidden = true; stage.append(draft);
  let mode = false, start = null, bbox = null, dragging = false, busy = false;
  const endMode = () => {
    mode = dragging = false; start = bbox = null; draft.hidden = true;
    stage.classList.remove('review-draw-mode'); toggle.hidden = false;
    cancel.hidden = true;
  };
  const point = event => {
    const rect = image.getBoundingClientRect();
    if (!rect.width || !rect.height) return null;
    return [Math.max(0,Math.min(1,(event.clientX-rect.left)/rect.width)),Math.max(0,Math.min(1,(event.clientY-rect.top)/rect.height))];
  };
  const draw = (a,b) => {
    const x1=Math.min(a[0],b[0]), y1=Math.min(a[1],b[1]), x2=Math.max(a[0],b[0]), y2=Math.max(a[1],b[1]);
    bbox=[x1,y1,x2,y2]; draft.hidden=false;
    Object.assign(draft.style,{left:`${x1*100}%`,top:`${y1*100}%`,width:`${(x2-x1)*100}%`,height:`${(y2-y1)*100}%`});
  };
  const tooSmall = () => !bbox || bbox[2]-bbox[0] < .004 || bbox[3]-bbox[1] < .004;
  toggle.addEventListener('click', () => {
    if (stage.hidden || !image.naturalWidth || !sessionStorage.getItem('training-label-snapshot')) {
      message('먼저 확인할 화면을 불러오세요.'); return;
    }
    mode=true; stage.classList.add('review-draw-mode'); toggle.hidden=true; cancel.hidden=false;
    message('놓친 사람의 머리부터 발끝까지 드래그하고 놓으면 바로 추가됩니다. 계속 그릴 수 있고, 끝나면 ‘상자 추가 끝내기’를 누르세요.');
  });
  cancel.addEventListener('click', () => { endMode(); message('상자 추가를 끝냈습니다.'); });
  stage.addEventListener('pointerdown', event => {
    if (!mode || busy || event.button !== 0) return;
    const p=point(event); if (!p) return;
    event.preventDefault(); start=p; dragging=true; stage.setPointerCapture(event.pointerId); draw(p,p);
  });
  stage.addEventListener('pointermove', event => {
    if (!mode || !dragging) return;
    event.preventDefault(); const p=point(event); if (p) draw(start,p);
  });
  stage.addEventListener('pointerup', event => {
    if (!mode || !dragging) return;
    event.preventDefault(); const p=point(event); if (p) draw(start,p);
    dragging=false;
    if (tooSmall()) { bbox=null; draft.hidden=true; message('상자가 너무 작습니다. 다시 그려 주세요.'); return; }
    submitBox(bbox);
  });
  stage.addEventListener('pointercancel', () => { dragging=false; bbox=null; draft.hidden=true; });
  stage.addEventListener('click', event => { if (mode) { event.preventDefault(); event.stopPropagation(); } }, true);
  // Releasing the drag adds the box at once; the page is not reloaded when the host page can show it in place.
  async function submitBox(box) {
    if (!mode || busy) return;
    const token = sessionStorage.getItem('training-label-snapshot');
    if (!token) { message('화면을 다시 불러와 주세요.'); return; }
    busy=true;
    try {
      const response=await fetch('/api/v1/training-labels/manual-box', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token,bbox:box})});
      if (!response.ok) throw new Error('request failed');
      const result=await response.json();
      if (result.token !== token || !result.person?.id) throw new Error('invalid result');
      draft.hidden=true; bbox=null;
      const hooks = globalThis.__reviewHooks || {};
      if (hooks.addPerson) {
        hooks.addPerson({...result.person, bbox: result.person.bbox || box});
        message('상자를 추가했습니다. 역할을 확인하고 Enter로 저장하세요. 이어서 다음 사람을 드래그해도 됩니다.');
      } else {
        message('상자를 추가했습니다. 같은 화면을 다시 불러옵니다.'); window.location.reload();
      }
    } catch (_) { draft.hidden=true; bbox=null; message('상자를 추가하지 못했습니다. 서버 연결을 확인하고 다시 시도하세요.'); }
    finally { busy=false; }
  }

  /* Pitch region: one polygon per camera setup. Scenes without their own polygon reuse the
     nearest earlier one (by clip time). It only drives review hints; it never saves a label. */
  const hooks = (globalThis.__reviewHooks = globalThis.__reviewHooks || {});
  let timeline = [], regions = {}, regionApi = false, drawingRegion = false, points = [], active = null;
  const regionBtn = document.createElement('button'), regionSave = document.createElement('button'),
        regionUndo = document.createElement('button'), regionCancel = document.createElement('button'),
        regionClear = document.createElement('button'), regionStatus = document.createElement('span');
  for (const button of [regionBtn, regionSave, regionUndo, regionCancel, regionClear]) { button.type = 'button'; button.hidden = true; }
  regionBtn.textContent = '경기장 영역 그리기'; regionSave.textContent = '영역 저장';
  regionUndo.textContent = '마지막 점 취소'; regionCancel.textContent = '영역 그리기 취소';
  regionClear.textContent = '이 장면 영역 지우기'; regionStatus.className = 'pitch-region-status';
  tools.append(regionBtn, regionUndo, regionSave, regionCancel, regionClear, regionStatus);
  const overlay = document.createElement('canvas'); overlay.className = 'pitch-region-canvas'; stage.append(overlay);
  const post = (url, body) => fetch('/api/v1/training-labels/' + url, {method:'POST', headers:{'Content-Type':'application/json'}, body: body && JSON.stringify(body)});
  const currentToken = () => sessionStorage.getItem('training-label-snapshot');
  const inside = (poly, [x, y]) => {
    let hit = false;
    for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
      const [xi, yi] = poly[i], [xj, yj] = poly[j];
      if ((yi > y) !== (yj > y) && x < (xj - xi) * (y - yi) / (yj - yi) + xi) hit = !hit;
    }
    return hit;
  };
  function findActive(token) {
    const index = timeline.findIndex(s => s.token === token);
    if (index < 0) return null;
    // A region only carries over to scenes of the same camera setting. A scene with no usable camera (the
    // camera is being moved) gets none; an older server that reports no camera field keeps the old behaviour.
    const camera = timeline[index].camera;
    if (camera === null) return null;
    for (let i = index; i >= 0; i--) {
      if (camera !== undefined && timeline[i].camera !== camera) continue;
      const poly = regions[timeline[i].token];
      if (Array.isArray(poly) && poly.length >= 3) return {polygon: poly, own: i === index, clip: timeline[i].clip_time};
    }
    return null;
  }
  function paint() {
    const ctx = overlay.getContext && overlay.getContext('2d'); if (!ctx) return;
    const w = overlay.width = image.naturalWidth || 1920, h = overlay.height = image.naturalHeight || 1080;
    ctx.clearRect(0, 0, w, h);
    const poly = drawingRegion ? points : (active ? active.polygon : null);
    if (!poly || !poly.length) return;
    ctx.lineWidth = Math.max(2, w / 500); ctx.strokeStyle = drawingRegion ? '#f4c66c' : '#d17cff';
    ctx.setLineDash(drawingRegion ? [] : [14, 8]); ctx.beginPath();
    poly.forEach((q, i) => { const px = q[0] * w, py = q[1] * h; if (i) ctx.lineTo(px, py); else ctx.moveTo(px, py); });
    if (!drawingRegion || poly.length > 2) ctx.closePath();
    ctx.stroke();
    if (drawingRegion) { ctx.fillStyle = '#f4c66c'; for (const q of poly) { ctx.beginPath(); ctx.arc(q[0] * w, q[1] * h, w / 300, 0, 7); ctx.fill(); } }
  }
  function refreshState() {
    const token = currentToken(); active = token ? findActive(token) : null;
    regionStatus.textContent = !regionApi ? '' : active
      ? (active.own ? '이 장면에 그린 경기장 영역을 쓰는 중입니다.' : '앞쪽 장면에서 그린 경기장 영역을 이어서 쓰는 중입니다. 카메라가 바뀌었으면 다시 그려 주세요.')
      : '경기장 영역이 없습니다. 영역을 그리면 바깥 후보를 관중 후보로 자동 표시합니다.';
    regionClear.hidden = !regionApi || drawingRegion || !(active && active.own);
    paint();
  }
  function endRegionDraw() {
    drawingRegion = false; points = []; stage.classList.remove('review-draw-mode');
    regionBtn.hidden = !regionApi; regionSave.hidden = regionUndo.hidden = regionCancel.hidden = true; refreshState();
  }
  // In the labelled scenes a player on the pitch is never taller than about 62 px in a 1080-px frame, while the
  // spectators who stand at the fence are 98 px or taller. A person that tall is a spectator whatever the
  // polygon says, so a polygon edge that is a few pixels off at the fence cannot turn a spectator into a player.
  const TALL_PX = 90, SMALL_PX = 80;
  hooks.insidePitch = p => {
    if (!active) return null;
    const [x1, y1, x2, y2] = p.bbox, cx = (x1 + x2) / 2, h = y2 - y1, tall = h * (image.naturalHeight || 1080);
    if (tall >= TALL_PX) return false;
    if (inside(active.polygon, [cx, y2])) return true;
    // a rail can hide the feet of a small player: allow a second point a little above the box bottom
    return tall < SMALL_PX && inside(active.polygon, [cx, y2 - 0.15 * h]);
  };
  hooks.sceneShown = async token => {
    try {
      const [s, r] = await Promise.all([post('scenes'), post('pitch-regions')]);
      if (!s.ok || !r.ok) throw new Error();
      const scenes = (await s.json()).scenes || [];
      timeline = scenes.filter(v => typeof v.clip_time === 'number').sort((a, b) => a.clip_time - b.clip_time);
      regions = (await r.json()).regions || {}; regionApi = true;
    } catch (_) { regionApi = false; }
    if (currentToken() !== token) return;
    if (!drawingRegion) regionBtn.hidden = !regionApi;
    refreshState();
    if (hooks.rerender) hooks.rerender();
  };
  regionBtn.addEventListener('click', () => {
    if (stage.hidden || !image.naturalWidth || !currentToken()) { message('먼저 확인할 화면을 불러오세요.'); return; }
    if (mode) { endMode(); }
    drawingRegion = true; points = []; stage.classList.add('review-draw-mode');
    regionBtn.hidden = true; regionSave.hidden = regionUndo.hidden = regionCancel.hidden = false; regionClear.hidden = true; paint();
    message('경기장 잔디 영역의 모서리를 순서대로 클릭하세요(3점 이상). 끝나면 ‘영역 저장’을 누르세요.');
  });
  stage.addEventListener('click', event => {
    if (!drawingRegion) return;
    event.preventDefault(); event.stopPropagation();
    const p = point(event); if (!p) return;
    if (points.length >= 40) { message('점은 최대 40개까지 찍을 수 있습니다.'); return; }
    points.push(p); paint();
  }, true);
  regionUndo.addEventListener('click', () => { points.pop(); paint(); });
  regionCancel.addEventListener('click', () => { endRegionDraw(); message('경기장 영역 그리기를 취소했습니다.'); });
  async function saveRegion(polygon) {
    const token = currentToken(); if (!token) return;
    try {
      const response = await post('pitch-region', {token, polygon});
      if (!response.ok) throw new Error();
      regions = (await response.json()).regions || {};
      endRegionDraw(); if (hooks.rerender) hooks.rerender();
      message(polygon.length ? '경기장 영역을 저장했습니다. 바깥 후보는 관중 후보로 표시됩니다.' : '이 장면의 경기장 영역을 지웠습니다.');
    } catch (_) { message('경기장 영역을 저장하지 못했습니다. 점 3개 이상으로 충분히 넓게 그리고, 서버 연결을 확인하세요.'); }
  }
  regionSave.addEventListener('click', () => { if (points.length >= 3) saveRegion(points); else message('점을 3개 이상 찍어 주세요.'); });
  regionClear.addEventListener('click', () => saveRegion([]));
})();
