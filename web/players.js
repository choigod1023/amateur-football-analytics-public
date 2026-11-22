(() => {
  const el = id => document.getElementById(id);
  const POSITIONS = ['DF', 'MF', 'FW', 'GK', 'LB', 'LCB', 'CB', 'RCB', 'RB', 'LWB', 'RWB', 'LM', 'LCM', 'CM', 'RCM', 'RM', 'LW', 'RW', 'LS', 'ST', 'RS'];
  let data = {halves: [], roster: [], position_text: {}, state: null};
  let half = '';
  let shown = 30;

  const text = (tag, value, cls) => { const node = document.createElement(tag); node.textContent = value; if (cls) node.className = cls; return node; };
  const clock = seconds => { const s = Math.round(seconds || 0); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`; };
  const say = (message, kind) => { const node = el('message'); node.textContent = message; node.className = 'message ' + (kind || ''); };
  const posText = code => (data.position_text && data.position_text[code]) || code || '';
  function suggestionTag(track) {
    const sug = track.suggestion;
    if (!sug) return null;
    const text0 = sug.level === 'skip' ? `건너뛰기 제안: ${sug.text || ''}` : `제안: ${sug.number}번${sug.level === 'maybe' ? '일 수 있음' : ''}${sug.text ? ' (' + sug.text + ')' : ''}`;
    return text('span', text0, sug.level === 'skip' ? 'tag warn' : 'tag B');
  }
  const label = p => `${p.number !== null && p.number !== undefined ? '#' + p.number + ' ' : ''}${p.name || ''}${p.position ? ' · ' + posText(p.position) : ''}`;

  async function api(path, body) {
    const response = await fetch(path, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body || {})});
    let result = {};
    try { result = await response.json(); } catch (_) { /* no body */ }
    if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : `요청이 실패했습니다 (${response.status})`);
    return result;
  }

  function renderRoster() {
    for (const team of ['A', 'B']) {
      const list = el('roster-' + team);
      const players = data.roster.filter(p => p.team === team);
      list.replaceChildren(...(players.length ? players.map(p => {
        const li = document.createElement('li');
        li.append(text('span', label(p)));
        const del = text('button', '삭제', 'danger'); del.type = 'button';
        del.addEventListener('click', async () => {
          if (!window.confirm(`${label(p)} 선수를 명단과 그 선수로 고른 답에서 지웁니다. 계속할까요?`)) return;
          try { await api('/api/v1/players/roster/delete', {id: p.id}); await load(); } catch (error) { say(error.message, 'bad'); }
        });
        li.append(del);
        return li;
      }) : [text('li', '아직 없습니다')]));
    }
  }

  function trackById(id) { return (data.state ? data.state.tracks : []).find(t => t.id === id); }
  function picture(track, k) {
    const name = track.pictures && track.pictures[k];
    if (!name) return text('div', '', 'noimg');
    const img = document.createElement('img'); img.src = `/player-files/${data.state.half}/${name}`; img.loading = 'lazy'; img.alt = `추적 ${track.id}`;
    return img;
  }

  const skipped = new Set();
  function renderPairs() {
    const state = data.state;
    const box = el('pairs');
    box.replaceChildren();
    if (!state) { el('pairs-empty').hidden = false; return; }
    const wanted = el('team').value;
    const list = state.candidates.filter(c => !skipped.has(c.a + '-' + c.b) && (!wanted || (trackById(c.a) || {}).team === wanted)).slice(0, 4);
    for (const c of list) {
      const a = trackById(c.a), b = trackById(c.b);
      if (!a || !b) continue;
      const row = document.createElement('div'); row.className = 'pair';
      const view = document.createElement('div');
      if (c.clip) {
        const video = document.createElement('video');
        video.src = `/player-files/${state.half}/${c.clip}`; video.autoplay = true; video.loop = true; video.muted = true; video.controls = true; video.playsInline = true; video.preload = 'auto';
        view.append(video);
      } else {
        const two = document.createElement('div'); two.style.display = 'grid'; two.style.gridTemplateColumns = '1fr 1fr'; two.style.gap = '8px';
        two.append(picture(a, 2), picture(b, 0)); view.append(two);
      }
      view.append(text('div', '주황 상자: 앞 조각(끝나는 곳까지) · 하늘색 상자: 뒤 조각(시작하는 곳부터) · 회색: 같은 장면의 다른 선수', 'meta'));
      const hint = c.near_others === undefined ? '' : c.near_others === 0 ? ' · 그 자리에 같은 팀 선수가 더 없어서 같은 사람일 가능성이 높습니다' : ` · 5m 안에 같은 팀 선수가 ${c.near_others}명 더 있어서 헷갈릴 수 있습니다`;
      view.append(text('div', `팀 ${a.team} · 앞 조각 ${clock(a.first)}~${clock(a.last)}, 뒤 조각 ${clock(b.first)}~${clock(b.last)} · 사이 ${c.gap}초, ${c.distance}m 이동${hint}`, 'meta'));
      const buttons = document.createElement('div'); buttons.className = 'verdict';
      for (const [relation, name] of [['same', '같은 사람'], ['different', '다른 사람']]) {
        const button = text('button', name); button.type = 'button';
        button.addEventListener('click', async () => { try { await api('/api/v1/players/link', {half: state.half, a: c.a, b: c.b, relation}); await load(); } catch (error) { say(error.message, 'bad'); } });
        buttons.append(button);
      }
      const skip = text('button', '모르겠음(건너뛰기)', 'ghost'); skip.type = 'button';
      skip.addEventListener('click', () => { skipped.add(c.a + '-' + c.b); renderPairs(); });
      buttons.append(skip);
      row.append(view, buttons);
      box.append(row);
    }
    el('pairs-empty').hidden = list.length > 0;
  }

  function trackCard(track) {
    const state = data.state;
    const card = document.createElement('div');
    card.className = 'track' + (track.player || track.player_by_link ? ' done' : '') + (track.conflict ? ' conflict' : '');
    for (let k = 0; k < 3; k++) card.append(picture(track, k));
    const info = document.createElement('div'); info.className = 'info';
    info.append(text('strong', `팀 ${track.team} · ${clock(track.first)}~${clock(track.last)}`));
    const tags = document.createElement('div');
    tags.append(text('span', `팀 ${track.team}`, 'tag ' + track.team));
    if (track.slot) tags.append(document.createTextNode(' '), text('span', `추정 자리: ${posText(track.slot)}`, 'tag'));
    { const tag = suggestionTag(track); if (tag) tags.append(document.createTextNode(' '), tag); }
    if (state.formation || track.formation) tags.append(document.createTextNode(' '), text('span', `팀 모양 ${track.formation || state.formation}`, 'tag'));
    if (track.group_size > 1) tags.append(document.createTextNode(' '), text('span', `이어진 조각 ${track.group_size}개`, 'tag'));
    if (track.conflict) tags.append(document.createTextNode(' '), text('span', '이어진 조각의 답이 서로 다릅니다', 'tag warn'));
    info.append(tags);
    const select = document.createElement('select');
    select.setAttribute('aria-label', '선수 고르기');
    select.append(new Option('선수 고르기', ''));
    for (const p of data.roster.filter(p => p.team === track.team)) select.append(new Option(label(p), p.id));
    select.value = track.player || '';
    select.addEventListener('change', async () => { try { await api('/api/v1/players/assign', {half: state.half, track: track.id, player: select.value}); await load(); } catch (error) { say(error.message, 'bad'); select.value = track.player || ''; } });
    info.append(select);
    if (track.player_by_link) { const who = data.roster.find(p => p.id === track.player_by_link); info.append(text('span', `이어진 조각의 답: ${who ? label(who) : ''}`, 'tag')); }
    card.append(info);
    return card;
  }

  function renderTracks() {
    const state = data.state;
    const box = el('tracks');
    el('chip-done').textContent = state ? `확인 ${state.done} / ${state.total}` : '확인 0 / 0';
    el('chip-pairs').textContent = `이음 후보 ${state ? state.candidates_left : 0}`;
    if (!state) { box.replaceChildren(); el('tracks-empty').hidden = false; el('more').hidden = true; return; }
    const team = el('team').value, filter = el('filter').value;
    const all = state.tracks.filter(t => (!team || t.team === team) && (filter === 'all' || (filter === 'open' ? !(t.player || t.player_by_link) : (t.player || t.player_by_link))));
    box.replaceChildren(...all.slice(0, shown).map(trackCard));
    el('tracks-empty').hidden = all.length > 0;
    el('more').hidden = all.length <= shown;
  }


  // ---- one player at a time: the chain -------------------------------------------------------------------------------------------
  let chainPlayer = '';
  const LINE_TEXT = {DF: '수비수 줄', MF: '미드필더 줄', FW: '공격수 줄', GK: '골키퍼'};

  function minimap(from, to, direction) {
    const canvas = document.createElement('canvas');
    canvas.width = 500; canvas.height = 330;
    const g = canvas.getContext('2d');
    const X = u => (u + 44.5) / 89 * 500, Y = v => (v + 31) / 62 * 330;
    g.fillStyle = '#1e3a2a'; g.fillRect(0, 0, 500, 330);
    g.strokeStyle = 'rgba(235,245,238,.8)'; g.lineWidth = 2;
    g.strokeRect(X(-44.5) + 1, Y(-31) + 1, 498, 328);
    g.beginPath(); g.moveTo(X(0), 0); g.lineTo(X(0), 330); g.stroke();
    g.beginPath(); g.arc(X(0), Y(0), 9.15 / 89 * 500, 0, 7); g.stroke();
    for (const side of [-1, 1]) { g.strokeRect(side < 0 ? X(-44.5) : X(44.5 - 16.5), Y(-20.15), 16.5 / 89 * 500, 40.3 / 62 * 330); }
    g.fillStyle = 'rgba(255,255,255,.7)'; g.font = '20px sans-serif'; g.fillText('공격 방향 →', 360, 320);
    if (from && to) {
      g.setLineDash([10, 8]); g.strokeStyle = '#fff'; g.lineWidth = 3;
      g.beginPath(); g.moveTo(X(from[0]), Y(from[1])); g.lineTo(X(to[0]), Y(to[1])); g.stroke(); g.setLineDash([]);
    }
    for (const [point, colour, name] of [[from, '#ff9f3c', '앞'], [to, '#5bc8ff', '뒤']]) {
      if (!point) continue;
      g.fillStyle = colour; g.beginPath(); g.arc(X(point[0]), Y(point[1]), 13, 0, 7); g.fill();
      g.fillStyle = '#10151b'; g.font = 'bold 18px sans-serif'; g.fillText(name, X(point[0]) - 9, Y(point[1]) + 6);
    }
    return canvas;
  }

  function offerCard(offer, chain) {
    const card = document.createElement('div'); card.className = 'offer';
    const anchor = chain.mine.find(t => t.id === offer.anchor);
    let from = null, to = null;
    if (anchor && offer.direction === 'after') { from = anchor.last_pos; to = offer.first_pos; }
    else if (anchor && offer.direction === 'before') { from = offer.last_pos; to = anchor.first_pos; }
    const left = document.createElement('div');
    left.append(minimap(from, to));
    left.append(text('div', anchor ? `${offer.direction === 'after' ? '앞 조각' : '뒤 조각'}과 ${offer.gap}초 사이, ${offer.distance}m 떨어짐` : '시작할 조각(이 선수일 가능성이 높은 자리)', 'meta'));
    const shots = document.createElement('div'); shots.className = 'shots';
    const add = (track, k, caption) => {
      const name = track.pictures && track.pictures[k];
      const figure = document.createElement('figure');
      if (name) { const img = document.createElement('img'); img.src = `/player-files/${chain.half}/${name}`; img.loading = 'lazy'; img.alt = caption; figure.append(img); }
      figure.append(text('figcaption', caption)); shots.append(figure);
    };
    if (anchor) add(anchor, 0, '앞 조각의 가장 선명한 장면');
    for (let k = 0; k < 3; k++) add(offer, k, ['이 조각의 선명한 장면 1', '선명한 장면 2', '선명한 장면 3'][k]);
    const middle = document.createElement('div'); middle.append(shots);
    const tags = document.createElement('div'); tags.className = 'chips';
    tags.append(text('span', `${clock(offer.first)}~${clock(offer.last)}`, 'tag'));
    if (offer.slot) tags.append(text('span', `추정 자리 ${posText(offer.slot)}`, 'tag'));
    { const tag = suggestionTag(offer); if (tag) tags.append(tag); }
    if (offer.line_match === true) tags.append(text('span', '포지션 줄이 맞음', 'tag B'));
    if (offer.line_match === false) tags.append(text('span', '포지션 줄이 다름', 'tag warn'));
    middle.append(tags);
    const buttons = document.createElement('div'); buttons.className = 'verdict';
    const yes = text('button', '이 선수가 맞음'); yes.type = 'button';
    yes.addEventListener('click', async () => { try { await api('/api/v1/players/assign', {half: chain.half, track: offer.id, player: chain.player.id}); await load(); } catch (error) { say(error.message, 'bad'); } });
    const no = text('button', '아님'); no.type = 'button';
    no.addEventListener('click', async () => { try { await api('/api/v1/players/reject', {half: chain.half, player: chain.player.id, track: offer.id, rejected: true}); await refreshChain(); } catch (error) { say(error.message, 'bad'); } });
    buttons.append(yes, no);
    card.append(left, middle, buttons);
    return card;
  }

  async function refreshChain() {
    const box = el('chain-offers'), mine = el('chain-mine');
    if (!chainPlayer || !half) { box.replaceChildren(); mine.replaceChildren(); el('chain-empty').hidden = true; return; }
    let chain;
    try { chain = await api('/api/v1/players/chain', {half, player: chainPlayer}); } catch (error) { say(error.message, 'bad'); return; }
    const summary = document.createElement('div');
    const who = `${chain.player.number !== null ? '#' + chain.player.number + ' ' : ''}${chain.player.name}`;
    const minutes = Math.floor(chain.seconds / 60), seconds = Math.round(chain.seconds % 60);
    summary.append(text('strong', `${who}: 정한 조각 ${chain.mine.length}개${chain.mine.length ? `, 합쳐서 ${minutes}분 ${seconds}초` : ''}`), document.createTextNode(` · 후보 ${chain.offers_total}개 중 ${chain.offers.length}개를 보여 줍니다${chain.line ? ' · 포지션 줄: ' + (LINE_TEXT[chain.line] || chain.line) : ''}`));
    const chips = document.createElement('div'); chips.className = 'chips';
    for (const t of chain.mine) {
      const chip = text('span', `${clock(t.first)}~${clock(t.last)}`, 'tag B');
      if (t.player === chain.player.id) {
        const x = text('button', '×'); x.type = 'button'; x.title = '이 조각을 이 선수에서 빼기';
        x.addEventListener('click', async () => { try { await api('/api/v1/players/assign', {half: chain.half, track: t.id, player: ''}); await load(); } catch (error) { say(error.message, 'bad'); } });
        chip.append(x);
      }
      chips.append(chip);
    }
    mine.replaceChildren(summary, chips);
    box.replaceChildren(...chain.offers.map(o => offerCard(o, chain)));
    el('chain-empty').hidden = chain.offers.length > 0;
  }

  function renderChainControls() {
    const players = data.roster.filter(p => p.team === 'B');
    const select = el('chain-player');
    select.replaceChildren(new Option('선수 고르기', ''), ...players.map(p => new Option(label(p), p.id)));
    if (!players.some(p => p.id === chainPlayer)) chainPlayer = '';
    select.value = chainPlayer;
    const halfSelect = el('chain-half');
    halfSelect.replaceChildren(...data.halves.map(h => new Option(h === 'h1' ? '전반' : h === 'h2' ? '후반' : h, h)));
    halfSelect.value = half;
  }
  el('chain-player').addEventListener('change', () => { chainPlayer = el('chain-player').value; refreshChain(); });
  el('chain-half').addEventListener('change', () => { half = el('chain-half').value; shown = 30; load(); });

  async function load() {
    try {
      data = await api('/api/v1/players/state', {half});
      half = data.state ? data.state.half : '';
      const select = el('half');
      select.replaceChildren(...data.halves.map(h => new Option(h === 'h1' ? '전반' : h === 'h2' ? '후반' : h, h)));
      select.value = half;
      renderRoster(); renderPairs(); renderTracks(); renderChainControls(); await refreshChain();
    } catch (error) { say(error.message, 'bad'); }
  }

  el('add-position').replaceChildren(new Option('포지션(선택)', ''), ...POSITIONS.map(p => new Option(p, p)));
  fetch('/api/v1/players/state', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: '{}'}).then(r => r.json()).then(d => {
    for (const option of el('add-position').options) if (d.position_text && d.position_text[option.value]) option.textContent = `${d.position_text[option.value]} (${option.value})`;
  }).catch(() => {});
  el('add').addEventListener('submit', async event => {
    event.preventDefault();
    try {
      await api('/api/v1/players/roster/set', {id: '', team: el('add-team').value, name: el('add-name').value, number: el('add-number').value === '' ? null : Number(el('add-number').value), position: el('add-position').value});
      el('add-name').value = ''; el('add-number').value = ''; say('추가했습니다.', 'good');
      await load();
    } catch (error) { say(error.message, 'bad'); }
  });
  el('half').addEventListener('change', () => { half = el('half').value; shown = 30; load(); });
  for (const id of ['team', 'filter']) el(id).addEventListener('change', () => { shown = 30; renderTracks(); renderPairs(); });
  el('more').addEventListener('click', () => { shown += 30; renderTracks(); });
  load();
})();
