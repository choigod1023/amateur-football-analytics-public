/* A frozen analysis image and its own boxes/tokens must stay together. */
(() => {
  const el = id => document.getElementById(id);
  const message = text => { el('manual-message').textContent = text; };
  let snapshot = null, selected = null, deadline = 0, expiry = null, generation = 0, busy = false;

  function invalidate(text) {
    snapshot = null; selected = null; deadline = 0;
    clearTimeout(expiry); expiry = null;
    el('manual-stage').hidden = true;
    el('manual-image').removeAttribute('src');
    el('manual-boxes').replaceChildren(); el('manual-list').replaceChildren();
    el('manual-selected').textContent = '선택된 사람 없음';
    delete el('manual-panel').dataset.frozen;
    const crop = el('manual-crop');
    crop.getContext('2d').clearRect(0, 0, crop.width, crop.height);
    el('manual-save').disabled = true;
    if (text) message(text);
  }
  function expire(text) {
    clearTimeout(expiry); expiry = null;
    deadline = 0;
    el('manual-save').disabled = true;
    message(text || '사진은 보관됩니다. 라이브 적용 시간이 지나 현재 화면을 다시 가져와야 합니다.');
  }
  function validPerson(p) {
    const b = p?.bbox_image_norm;
    return typeof p?.id === 'string' && p.id.length > 0 && p.id.length <= 128 &&
      typeof p.annotation_token === 'string' && /^[A-Za-z0-9_-]{1,128}$/.test(p.annotation_token) &&
      Array.isArray(b) && b.length === 4 && b.every(n => Number.isFinite(n) && n >= 0 && n <= 1) && b[0] < b[2] && b[1] < b[3];
  }
  function select(p) {
    if (!snapshot || busy) return;
    selected = p;
    el('manual-selected').textContent = `선택한 추적 ID ${p.id}`;
    el('manual-role').value = ''; el('manual-team').value = '';
    el('manual-team').disabled = true;
    el('manual-save').disabled = performance.now() >= deadline;
    const image = el('manual-image'), canvas = el('manual-crop'), ctx = canvas.getContext('2d');
    const [x1,y1,x2,y2] = p.bbox_image_norm;
    const draw = () => {
      if (!image.naturalWidth || selected !== p) return;
      const x = x1 * image.naturalWidth, y = y1 * image.naturalHeight;
      const w = (x2-x1) * image.naturalWidth, h = (y2-y1) * image.naturalHeight;
      ctx.clearRect(0,0,canvas.width,canvas.height);
      const scale = Math.min(canvas.width / w, canvas.height / h);
      ctx.imageSmoothingEnabled = false;
      ctx.drawImage(image, x, y, w, h, (canvas.width-w*scale)/2, (canvas.height-h*scale)/2, w*scale, h*scale);
    };
    if (image.complete) draw(); else image.addEventListener('load', draw, {once:true});
    for (const button of el('manual-list').querySelectorAll('button')) button.setAttribute('aria-pressed', String(button.dataset.track === p.id));
    message(performance.now() >= deadline ? '사진은 보관됩니다. 라이브 적용을 위해 현재 화면을 다시 가져오세요.' : '확대 화면에서 확인한 뒤 역할과 팀을 지정하세요.');
  }
  async function getFrame() {
    const mine = ++generation, started = performance.now();
    invalidate('분석 화면을 가져오는 중입니다.');
    el('manual-refresh').disabled = true;
    const controller = new AbortController(), timer = setTimeout(() => controller.abort(), 5000);
    try {
      const response = await fetch('/api/v1/manual-snapshot', {cache:'no-store', signal:controller.signal});
      if (mine !== generation) return;
      if (response.status === 409) { message('확인할 화면이 없습니다. 분석 중인지와 서버의 수동 확인 모드를 확인하세요.'); return; }
      if (!response.ok) throw new Error('unavailable');
      const data = await response.json();
      const b64 = data?.image_jpeg_base64;
      if (typeof b64 !== 'string' || b64.length > 2700000 || !/^\/9j\/[A-Za-z0-9+/]*={0,2}$/.test(b64) ||
          typeof data.snapshot_token !== 'string' || !/^[A-Za-z0-9_-]{1,128}$/.test(data.snapshot_token) ||
          !Array.isArray(data.players) || !Number.isFinite(data.expires_in_s) || data.expires_in_s <= 0 || data.expires_in_s > 60) throw new Error('invalid');
      const counts = new Map();
      for (const person of data.players) if (validPerson(person)) counts.set(person.id, (counts.get(person.id) || 0) + 1);
      const people = data.players.filter(p => validPerson(p) && counts.get(p.id) === 1).slice(0,100);
      deadline = started + data.expires_in_s * 1000;
      if (performance.now() >= deadline) { message('화면이 만료됐습니다. 다시 가져와 주세요.'); return; }
      snapshot = {token:data.snapshot_token, people};
      el('manual-panel').dataset.frozen = 'true';
      el('manual-image').src = 'data:image/jpeg;base64,' + b64;
      el('manual-stage').hidden = false;
      for (const person of people) {
        const box = document.createElement('button'), item = document.createElement('button');
        const [x1,y1,x2,y2] = person.bbox_image_norm;
        box.type = item.type = 'button'; box.className = 'manual-box';
        box.style.left = `${x1*100}%`; box.style.top = `${y1*100}%`;
        box.style.width = `${(x2-x1)*100}%`; box.style.height = `${(y2-y1)*100}%`;
        box.textContent = person.id; box.setAttribute('aria-hidden','true'); box.tabIndex = -1;
        const hint = [0, 1].includes(person.suggested_color_group) ? ` · 색상 후보 ${person.suggested_color_group === 0 ? 'A' : 'B'} (미확인)` : '';
        item.textContent = `추적 ID ${person.id}${hint}`; item.dataset.track = person.id;
        item.setAttribute('aria-pressed','false');
        box.addEventListener('click', () => select(person)); item.addEventListener('click', () => select(person));
        el('manual-boxes').append(box); el('manual-list').append(item);
      }
      message(people.length ? `같은 분석 화면에서 ${people.length}명을 찾았습니다. 화면 또는 목록에서 선택하세요.` : '이 화면에서 확인할 수 있는 사람이 없습니다.');
      expiry = setTimeout(() => expire(), Math.max(0, deadline-performance.now()));
    } catch (_) {
      if (mine === generation) invalidate('화면을 가져오지 못했습니다. 서버 연결을 확인하세요.');
    } finally { clearTimeout(timer); if (mine === generation) el('manual-refresh').disabled = false; }
  }
  el('manual-refresh').addEventListener('click', getFrame);
  el('manual-role').addEventListener('change', () => {
    const player = ['player','goalkeeper'].includes(el('manual-role').value);
    el('manual-team').disabled = !player; if (!player) el('manual-team').value = '';
  });
  el('manual-form').addEventListener('submit', async event => {
    event.preventDefault();
    if (busy || !selected || !snapshot || performance.now() >= deadline) { expire(); return; }
    const role = el('manual-role').value, teamMember = ['player','goalkeeper'].includes(role), team = teamMember ? el('manual-team').value : 'unknown';
    if (!['player','referee','goalkeeper','unknown'].includes(role) || (teamMember && !['home','away'].includes(team))) { message('역할을 선택하고, 선수나 골키퍼라면 팀도 선택하세요.'); return; }
    const mine = generation, body = {snapshot_token:snapshot.token,id:selected.id,token:selected.annotation_token,role,team};
    busy = true; el('manual-save').disabled = true;
    const controller = new AbortController(), timer = setTimeout(() => controller.abort(),5000);
    try {
      const response = await fetch('/api/v1/manual-track', {method:'POST',cache:'no-store',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),signal:controller.signal});
      if (mine !== generation) return;
      if (response.status === 409) { expire('추적이 끊겼거나 화면이 만료됐습니다. 사진은 남겨두었으며 라이브 적용은 새 화면에서 확인해 주세요.'); return; }
      if (!response.ok) throw new Error('request failed');
      message(`추적 ID ${selected.id}의 확인 내용을 적용했습니다. 추적이 끊기거나 시간이 지나면 다시 확인해야 합니다.`);
    } catch (_) { if (mine === generation) message('확인 내용을 적용하지 못했습니다. 서버 연결을 확인하세요.'); }
    finally { clearTimeout(timer); busy = false; if (mine === generation && snapshot && selected && performance.now() < deadline) el('manual-save').disabled = false; }
  });
})();
