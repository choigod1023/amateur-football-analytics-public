/* Analyst tag page (/tag): one press = one tag with the server time. Presses that cannot be sent are kept on the phone and sent later with the estimated server time. */
(() => {
  const $ = id => document.getElementById(id);
  const MARK = {start_h1: '전반 시작', end_h1: '전반 종료', start_h2: '후반 시작', end_h2: '후반 종료'};
  let offset = 0, items = [], lastId = null, toastTimer = null;
  const serverNow = () => Date.now() / 1000 + offset;
  const two = n => String(n).padStart(2, '0');
  const mmss = s => `${two(Math.floor(s / 60))}:${two(Math.floor(s % 60))}`;
  const halfName = h => (h === 'h1' ? '전반' : h === 'h2' ? '후반' : '');

  function loadPending() { try { return JSON.parse(localStorage.getItem('tagPending') || '[]'); } catch (_) { return []; } }
  function savePending(list) { try { localStorage.setItem('tagPending', JSON.stringify(list.slice(-200))); } catch (_) { /* private mode */ } }

  async function post(url, body) {
    const res = await fetch(url, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body), signal: AbortSignal.timeout(6000)});
    if (!res.ok) throw new Error(String(res.status));
    return res.json();
  }

  function setConn(ok) { const c = $('conn'); c.textContent = ok ? '연결됨' : '연결 끊김 · 폰에 보관 중'; c.className = ok ? 'ok' : 'bad'; }

  function toast(text, id) {
    $('toast-text').textContent = text; $('toast').hidden = false; lastId = id || null;
    $('undo').hidden = !id;
    clearTimeout(toastTimer); toastTimer = setTimeout(() => { $('toast').hidden = true; lastId = null; }, 8000);
  }

  async function press(kind) {
    let note = '';
    if (MARK[kind] && !confirm(`${MARK[kind]}을(를) 지금 시각으로 기록할까요?`)) return;
    if (kind === 'note') { note = prompt('메모 내용') || ''; if (!note) return; }
    const at = serverNow();
    try {
      const r = await post('/api/v1/analyst-tags', {kind, note});
      setConn(true);
      toast(`저장: ${r.label} (${r.time})`, r.id);
      if (navigator.vibrate) navigator.vibrate(40);
    } catch (_) {
      const pending = loadPending(); pending.push({kind, note, at}); savePending(pending);
      setConn(false); toast(`연결이 안 되어 폰에 보관했습니다 (${pending.length}개)`);
    }
    refresh();
  }

  async function flush() {
    const pending = loadPending(); if (!pending.length) return;
    const left = [];
    for (const p of pending) {
      try { await post('/api/v1/analyst-tags', p); } catch (_) { left.push(p); }
    }
    savePending(left);
    if (!left.length) toast(`보관했던 표시 ${pending.length}개를 보냈습니다`);
  }

  function currentClock() {
    let half = null, since = null;
    for (const it of items) {
      if (it.kind === 'start_h1' || it.kind === 'start_h2') { half = it.kind.slice(-2); since = it.epoch; }
      if ((it.kind === 'end_h1' || it.kind === 'end_h2')) { half = null; since = null; }
    }
    $('clock').textContent = half ? `${halfName(half)} ${mmss(serverNow() - since)}` : (items.some(i => i.kind === 'end_h1') && !items.some(i => i.kind === 'start_h2') ? '하프타임' : '경기 시작 전');
  }

  function render() {
    const filter = $('filter').value, list = $('list'); list.replaceChildren();
    const shown = items.filter(it => !filter || it.half === filter).slice().reverse();
    $('count').textContent = `${items.filter(i => !MARK[i.kind]).length}개`;
    for (const it of shown) {
      const li = document.createElement('li'); if (MARK[it.kind]) li.className = 'mark';
      const t = document.createElement('div'); t.className = 't';
      t.textContent = it.clock !== null ? mmss(it.clock) : '--:--';
      const sm = document.createElement('small'); sm.textContent = `${halfName(it.half)} ${it.time}`; t.append(sm);
      const l = document.createElement('div'); l.className = 'l';
      const b = document.createElement('b'); b.textContent = it.label; l.append(b);
      if (it.note) { const s = document.createElement('span'); s.textContent = it.note; l.append(s); }
      const tools = document.createElement('div'); tools.className = 'b';
      if (it.clip === 'done') tools.append(btn('재생', () => play(it.id)));
      else if (it.clip && it.clip !== 'none') tools.append(label({queued: '대기', running: '자르는 중', 'no-recording': '녹화 없음', failed: '실패'}[it.clip] || it.clip));
      if (!MARK[it.kind]) tools.append(btn('메모', () => editNote(it)));
      tools.append(btn('삭제', () => remove(it)));
      li.append(t, l, tools); list.append(li);
    }
  }
  function btn(text, fn) { const b = document.createElement('button'); b.type = 'button'; b.textContent = text; b.addEventListener('click', fn); return b; }
  function label(text) { const s = document.createElement('span'); s.className = 'note'; s.textContent = text; return s; }

  async function remove(it) {
    if (!confirm(`${it.label} 기록을 지울까요?`)) return;
    try { await post('/api/v1/analyst-tags/delete', {id: it.id}); } catch (_) { alert('지우지 못했습니다. 연결을 확인하세요.'); }
    refresh();
  }
  async function editNote(it) {
    const note = prompt('메모', it.note || ''); if (note === null) return;
    try { await post('/api/v1/analyst-tags/note', {id: it.id, note}); } catch (_) { alert('저장하지 못했습니다.'); }
    refresh();
  }
  function play(id) { const v = $('video'); v.src = `/analyst-clip/${id}.mp4`; $('player').showModal(); v.play().catch(() => {}); }

  async function refresh() {
    try {
      const res = await fetch('/api/v1/analyst-tags', {cache: 'no-store', signal: AbortSignal.timeout(6000)});
      if (!res.ok) throw new Error(String(res.status));
      const data = await res.json();
      offset = data.now - Date.now() / 1000; items = data.items; setConn(true);
      render(); currentClock();
      if (loadPending().length) flush();
    } catch (_) { setConn(false); }
  }

  document.querySelectorAll('button[data-kind]').forEach(b => b.addEventListener('click', () => press(b.dataset.kind)));
  $('undo').addEventListener('click', async () => {
    if (!lastId) return; const id = lastId; lastId = null; $('toast').hidden = true;
    try { await post('/api/v1/analyst-tags/delete', {id}); } catch (_) { alert('되돌리지 못했습니다.'); }
    refresh();
  });
  $('filter').addEventListener('change', render);
  $('make-clips').addEventListener('click', async () => {
    try {
      const r = await post('/api/v1/analyst-tags/clips', {});
      $('clip-note').textContent = r.recordings ? `클립 ${r.queued}개를 자르는 중입니다. 하나에 몇 초씩 걸립니다.` : '녹화 폴더를 찾지 못했습니다. 녹화가 켜져 있는지 확인하세요.';
    } catch (_) { $('clip-note').textContent = '요청하지 못했습니다.'; }
    refresh();
  });
  $('close').addEventListener('click', () => { $('video').pause(); $('player').close(); });
  refresh(); setInterval(refresh, 5000); setInterval(currentClock, 1000);
})();
