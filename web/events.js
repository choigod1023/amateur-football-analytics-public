/* Event review: the reviewer's answers are the only ground truth; candidates are suggestions. */
(() => {
  const el = id => document.getElementById(id);
  const NAMES = {kickoff:'킥오프', goal:'골', set_piece:'세트피스', shot:'슈팅', other:'기타', none:'아님', unsure:'모르겠음'};
  const KEYS = {'1':'kickoff', '2':'goal', '3':'set_piece', '4':'shot', '5':'other', '0':'none', n:'none', u:'unsure'};
  const post = (path, body) => fetch('/api/v1/events/' + path, {method:'POST', headers:{'Content-Type':'application/json'}, body: body && JSON.stringify(body)});
  const clock = s => (typeof s === 'number' && isFinite(s)) ? `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}` : '-';
  let data = null, current = null, marked = null, filter = 'all';
  const FILTERS = [['all', '전체', c => true], ['todo', '미검토', c => !c.label], ['kickoff', '킥오프', c => c.label && c.label.label === 'kickoff'],
    ['goal', '골', c => c.label && c.label.label === 'goal'], ['set_piece', '세트피스', c => c.label && c.label.label === 'set_piece'],
    ['other', '슈팅·기타', c => c.label && ['shot', 'other'].includes(c.label.label)], ['none', '아님·모름', c => c.label && ['none', 'unsure'].includes(c.label.label)]];
  const status = text => { el('ev-status').textContent = text; };

  async function load() {
    try {
      const r = await post('list'); if (!r.ok) throw new Error();
      data = await r.json();
    } catch (_) { status('이벤트 후보를 불러오지 못했습니다. 서버가 새 버전인지, 후보 파일이 만들어졌는지 확인하세요.'); return false; }
    if (!data.candidates.length && !data.manual.length) status('아직 이벤트 후보가 없습니다. 후보 생성 스크립트를 실행해야 합니다.');
    return true;
  }
  const visible = () => {
    const test = (FILTERS.find(f => f[0] === filter) || FILTERS[0])[2];
    const list = data.candidates.filter(test);
    return el('ev-sort').value === 'score' ? [...list].sort((a, b) => (b.score || 0) - (a.score || 0)) : [...list].sort((a, b) => (a.t || 0) - (b.t || 0));
  };
  function renderSummary() {
    const reviewed = data.candidates.filter(c => c.label).length;
    const counts = {}; for (const c of [...data.candidates.map(c => c.label), ...data.manual]) if (c) counts[c.label] = (counts[c.label] || 0) + 1;
    status(`검토 ${reviewed} / ${data.candidates.length}` + ['kickoff', 'goal', 'set_piece', 'shot', 'other'].filter(k => counts[k]).map(k => ` · ${NAMES[k]} ${counts[k]}`).join(''));
  }
  function renderFilters() {
    const bar = el('ev-filters'); bar.replaceChildren();
    for (const [key, label, test] of FILTERS) {
      const b = document.createElement('button'); b.type = 'button'; b.className = 'scene-filter' + (key === filter ? ' is-active' : '');
      b.textContent = `${label} ${data.candidates.filter(test).length}`;
      b.addEventListener('click', () => { filter = key; renderFilters(); renderList(); }); bar.append(b);
    }
  }
  function renderList() {
    const list = el('ev-list'); list.replaceChildren();
    for (const c of visible()) {
      const b = document.createElement('button'); b.type = 'button';
      b.className = 'ev-item' + (current && current.id === c.id ? ' is-current' : '') + (c.label ? ' has-label label-' + c.label.label : '');
      const img = document.createElement('img'); img.alt = ''; img.width = 96; img.height = 24; img.src = `/event-media/${c.id}.jpg`; img.addEventListener('error', () => { img.hidden = true; });
      const t = document.createElement('strong'); t.textContent = `${clock(c.t)} · ${c.id}`;
      const s = document.createElement('small'); s.textContent = c.label ? NAMES[c.label.label] : `추천 ${Math.round((c.score || 0) * 100)}점`;
      b.append(img, t, s); b.addEventListener('click', () => select(c.id)); list.append(b);
    }
  }
  function renderSaved() {
    const box = el('ev-saved'); box.replaceChildren();
    const rows = [...data.candidates.filter(c => c.label && ['kickoff', 'goal', 'set_piece', 'shot', 'other'].includes(c.label.label)).map(c => ({id:c.id, time:c.label.event_time != null ? c.label.event_time : c.t, label:c.label.label, note:c.label.note, manual:false})),
      ...data.manual.map(m => ({id:m.id, time:m.event_time, label:m.label, note:m.note, manual:true}))].sort((a, b) => a.time - b.time);
    el('ev-summary').textContent = `(${rows.length}건)`;
    if (!rows.length) { box.textContent = '아직 저장한 사건이 없습니다.'; return; }
    for (const r of rows) {
      const line = document.createElement('div'); line.className = 'ev-row';
      line.textContent = `${clock(r.time)} · ${NAMES[r.label]}${r.manual ? ' (직접 추가)' : ''}${r.note ? ' · ' + r.note : ''} `;
      if (r.manual) { const del = document.createElement('button'); del.type = 'button'; del.textContent = '삭제'; del.addEventListener('click', async () => { await post('label', {id:r.id, label:'clear'}); await refresh(); }); line.append(del); }
      box.append(line);
    }
  }
  function renderLabels() {
    const box = el('ev-labels'); box.replaceChildren();
    const order = ['kickoff', 'goal', 'set_piece', 'shot', 'other', 'none', 'unsure'];
    const keys = {kickoff:'1', goal:'2', set_piece:'3', shot:'4', other:'5', none:'0', unsure:'U'};
    for (const label of order) {
      const b = document.createElement('button'); b.type = 'button'; b.className = 'ev-label label-' + label + (current && current.label && current.label.label === label ? ' is-active' : '');
      b.textContent = `${NAMES[label]} (${keys[label]})`; b.addEventListener('click', () => save(label)); box.append(b);
    }
    const clear = document.createElement('button'); clear.type = 'button'; clear.className = 'ev-label'; clear.textContent = '답 지우기'; clear.addEventListener('click', () => save('clear')); box.append(clear);
  }
  function select(id) {
    const c = data.candidates.find(x => x.id === id); if (!c) return;
    current = c; marked = c.label && c.label.event_time != null ? c.label.event_time : null;
    el('ev-main').hidden = false;
    el('ev-title').textContent = `후보 ${c.id} · 경기 구간 ${clock(c.t)} 부근 (영상 ${clock(c.start)}~${clock(c.end)})`;
    el('ev-reasons').textContent = '추천 이유: ' + (c.reasons || []).join(' / ') + ' (자동 규칙이며 정답이 아닙니다)';
    el('ev-note').value = c.label ? c.label.note || '' : '';
    const v = el('ev-video'); v.src = `/event-media/${c.id}.mp4`; v.poster = `/event-media/${c.id}.jpg`; v.playbackRate = 1; v.play && v.play().catch(() => {});
    renderMarked(); renderLabels(); renderList();
  }
  const renderMarked = () => { el('ev-marked').textContent = marked != null ? `사건 시각: 경기 구간 ${clock(marked)}` : '사건 시각을 표시하지 않았습니다(후보 시각 사용)'; };
  async function refresh() { await load(); renderFilters(); renderList(); renderSaved(); renderSummary(); if (current) { current = data.candidates.find(c => c.id === current.id) || current; renderLabels(); } }
  function nextTodo(from) {
    const list = visible(); const i = list.findIndex(c => c.id === from);
    return list.slice(i + 1).find(c => !c.label) || list.find(c => !c.label && c.id !== from);
  }
  async function save(label) {
    if (!current) return;
    const id = current.id;
    try {
      const r = await post('label', {id, label, event_time: label === 'clear' ? null : marked, note: el('ev-note').value});
      if (!r.ok) throw new Error();
    } catch (_) { status('저장하지 못했습니다. 서버 연결을 확인하고 다시 시도하세요.'); return; }
    const next = label === 'clear' ? null : nextTodo(id);
    await refresh();
    if (next) select(next.id); else { current = data.candidates.find(c => c.id === id) || current; renderLabels(); renderList(); }
  }
  function neighbour(step) {
    const list = visible(); const i = list.findIndex(c => current && c.id === current.id);
    const t = list[Math.min(list.length - 1, Math.max(0, i + step))]; if (t) select(t.id);
  }
  function parseTime(text) {
    const m = /^\s*(?:(\d{1,3}):)?(\d{1,2})(?:\.(\d+))?\s*$/.exec(text); if (!m) return null;
    return (m[1] ? Number(m[1]) * 60 : 0) + Number(m[2]) + (m[3] ? Number('0.' + m[3]) : 0);
  }

  el('ev-sort').addEventListener('change', renderList);
  for (const b of document.querySelectorAll('[data-rate]')) b.addEventListener('click', () => { el('ev-video').playbackRate = Number(b.dataset.rate); });
  el('ev-mark').addEventListener('click', () => { if (!current) return; marked = current.start + el('ev-video').currentTime; renderMarked(); });
  el('ev-export').addEventListener('click', () => {
    const rows = [...data.candidates.filter(c => c.label).map(c => ({id:c.id, candidate_time:c.t, event_time:c.label.event_time, label:c.label.label, note:c.label.note, manual:false})),
      ...data.manual.map(m => ({id:m.id, candidate_time:null, event_time:m.event_time, label:m.label, note:m.note, manual:true}))];
    const blob = new Blob([JSON.stringify({basis:data.basis, exported:new Date().toISOString(), events:rows}, null, 1)], {type:'application/json'});
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = 'event_labels.json'; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  });
  el('ev-manual-form').addEventListener('submit', async event => {
    event.preventDefault();
    const t = parseTime(el('ev-manual-time').value);
    if (t == null) { status('시각은 분:초로 적어 주세요. 예: 12:34'); return; }
    try {
      const r = await post('manual', {time:t, label:el('ev-manual-label').value, note:el('ev-manual-note').value}); if (!r.ok) throw new Error();
      el('ev-manual-time').value = ''; el('ev-manual-note').value = ''; await refresh(); status('사건을 추가했습니다.');
    } catch (_) { status('사건을 추가하지 못했습니다.'); }
  });
  document.addEventListener('keydown', event => {
    if (event.ctrlKey || event.altKey || event.metaKey) return;
    if (['INPUT', 'SELECT', 'TEXTAREA'].includes(event.target && event.target.tagName)) return;
    const k = event.key.toLowerCase();
    if (KEYS[k]) { event.preventDefault(); save(KEYS[k]); }
    else if (k === ' ' && current) { event.preventDefault(); const v = el('ev-video'); v.paused ? v.play() : v.pause(); }
    else if (k === 'm') el('ev-mark').click();
    else if (event.key === 'ArrowRight') neighbour(1);
    else if (event.key === 'ArrowLeft') neighbour(-1);
  });
  for (const label of ['kickoff', 'goal', 'set_piece', 'shot', 'other', 'unsure']) {
    const o = document.createElement('option'); o.value = label; o.textContent = NAMES[label]; el('ev-manual-label').append(o);
  }
  (async () => {
    if (!(await load())) return;
    renderFilters(); renderList(); renderSaved(); renderSummary();
    const first = data.candidates.find(c => !c.label) || data.candidates[0]; if (first) select(first.id);
  })();
})();
