/* Analyst tag page (/tag): one press = one tag with the server time. Presses that cannot be sent are kept on the phone and sent later with the estimated server time. */
(() => {
  const $ = id => document.getElementById(id);
  const MARK = {start_h1: '전반 시작', end_h1: '전반 종료', start_h2: '후반 시작', end_h2: '후반 종료'};
  const GOAL = {goal_ours: 'ours', goal_theirs: 'opp'};
  let offset = 0, items = [], lastId = null, toastTimer = null, lastScored = false;
  // Score board of the bench screen (POST /api/v1/score). Returns true when the score was changed; a failure never blocks the tag.
  async function score(body) {
    try {
      const now = await fetch('/api/v1/score', {cache: 'no-store', signal: AbortSignal.timeout(4000)}).then(r => r.json());
      if (!now.session) return false;
      await post('/api/v1/score', {session: now.session, source: 'manual', ...body});
      return true;
    } catch (_) { return false; }
  }
  const serverNow = () => Date.now() / 1000 + offset;
  const two = n => String(n).padStart(2, '0');
  const mmss = s => `${two(Math.floor(s / 60))}:${two(Math.floor(s % 60))}`;
  // the particle after a word: 을 when its last syllable ends in a consonant, 를 when it ends in a vowel ("전반 시작을", "후반 종료를")
  const josa = (word, withFinal, without) => { const c = word.charCodeAt(word.length - 1) - 0xAC00; return c >= 0 && c < 11172 && c % 28 !== 0 ? withFinal : without; };
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
    if (MARK[kind] && !confirm(`${MARK[kind]}${josa(MARK[kind], '을', '를')} 지금 기록할까요?`)) return;
    if (kind === 'note') { note = prompt('메모 내용') || ''; if (!note) return; }
    const at = serverNow();
    try {
      const r = await post('/api/v1/analyst-tags', {kind, note});
      setConn(true);
      // A goal tag also raises the score of the bench screen, so one press does both. The undo of the toast takes it back again.
      let scored = false;
      if (GOAL[kind]) scored = await score({kind: 'goal', team: GOAL[kind]});
      toast(`저장: ${r.label} (${r.time})${GOAL[kind] ? (scored ? ' · 점수 반영' : ' · 점수는 벤치 화면에서 올리세요') : ''}`, r.id);
      lastScored = scored;
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

  // The clock itself is drawn by match-clock.js from the server (GET /api/v1/clock); here it is only asked to look again after a press.
  function currentClock() { if (window.MatchClock) window.MatchClock.refresh(); }

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
    if (!lastId) return; const id = lastId, wasScored = lastScored; lastId = null; lastScored = false; $('toast').hidden = true;
    try { await post('/api/v1/analyst-tags/delete', {id}); if (wasScored) await score({kind: 'undo'}); } catch (_) { alert('되돌리지 못했습니다.'); }
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
  // The score of the bench screen, shown beside the clock so one person can work from this page alone.
  async function showScore() {
    try { const s = await fetch('/api/v1/score', {cache: 'no-store', signal: AbortSignal.timeout(4000)}).then(r => r.json()); $('tag-score').textContent = s.session ? `${s.ours} : ${s.opp}` : ''; } catch (_) { /* keep the last score */ }
  }
  showScore(); setInterval(showScore, 2000);
  // The newest alert of the bench screen as one line under the clock; a tap opens the bench screen.
  async function showAlert() {
    try {
      const d = await fetch('/api/v1/bench', {cache: 'no-store', signal: AbortSignal.timeout(4000)}).then(r => r.json());
      const g = window.MatchClock ? window.MatchClock.gate(d) : d;
      const a = g && g.current, box = $('tag-alert');
      if (!a) {                                                    // nothing to show: before the first half a short line says why
        if (g && g.quiet) { box.dataset.priority = ''; const q = document.createElement('small'); q.textContent = g.quiet; box.replaceChildren(q); box.hidden = false; } else box.hidden = true;
        return;
      }
      box.dataset.priority = a.priority || '';
      const b = document.createElement('b'); b.textContent = `${a.priority_text || '알림'} · ${a.title}`;
      const s = document.createElement('small'); s.textContent = a.text || '';
      box.replaceChildren(b, s); box.hidden = false;
    } catch (_) { /* keep the last alert */ }
  }
  showAlert(); setInterval(showAlert, 2000);
  refresh(); setInterval(refresh, 5000);
})();
