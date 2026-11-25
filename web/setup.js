// Match preparation (/setup) as three groups in time order: 1 about 30 minutes before the kickoff (warm-up), 2 just before the kickoff, 3 the kickoff.
// The state comes from GET /api/v1/setup every 3 seconds. There is no password (the owner's decision); stopping the run and starting a new
// match ask for the last four characters of the match name, only so that a wrong tap does not do it.
(() => {
  const $ = (id) => document.getElementById(id);
  const ui = { name: null, nameConflict: false, pick: null, opp: null, reader: null, sentence: null, open: {}, busy: false, msg: {}, linesAt: 0, newCode: '', stopCode: '', askStop: false };
  const FEW = 6;                     // fewer own players than this: the colours were probably read wrong (the temporary 6 of the match-day sheet)
  const ORD = ['첫째', '둘째', '셋째', '넷째', '다섯째'];   // the colour groups in the order of the server (largest first)
  let state = null, lastSig = '';

  async function post(path, body) {
    const r = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) { const e = new Error(typeof data.detail === 'string' ? data.detail : '다시 눌러 주세요.'); e.status = r.status; throw e; }
    return data;
  }

  // ---- "analysis stopped": restart at the top of the page ---------------------------------------------------------------------
  function restartView() {
    const a = state.analysis;
    const show = !!a.ended && !a.running && !(state.job && ['photos', 'choose', 'starting'].includes(state.job.phase));
    $('restart-box').hidden = !show;
    if (show) $('restart-title').textContent = a.ended === 'stopped' ? '분석을 멈췄습니다' : '분석이 꺼졌습니다';
  }
  $('restart').addEventListener('click', async () => {
    $('restart').disabled = true; $('restart-msg').textContent = '시작하는 중입니다…';
    try { await post('/api/v1/setup/restart', {}); $('restart-msg').textContent = ''; }
    catch (e) { $('restart-msg').textContent = e.message; }
    $('restart').disabled = false; refresh(true);
  });

  // ---- video at the top -------------------------------------------------------------------------------------------------------
  const video = $('video');
  const hlsOn = () => !!(window.LiveHls && window.LiveHls.active());   // web/live-hls.js is playing: no picture
  function loadVideo() { if (hlsOn()) return; video.src = '/live-video.mjpg?t=' + Date.now(); }
  video.addEventListener('load', () => { if (!hlsOn()) $('video-none').hidden = true; });
  video.addEventListener('error', () => { if (hlsOn()) return; $('video-none').hidden = false; setTimeout(loadVideo, 3000); });
  window.addEventListener('livehls-off', () => { $('video-none').hidden = false; loadVideo(); });   // HLS stopped working: the picture again
  loadVideo();

  // ---- helpers ----------------------------------------------------------------------------------------------------------------
  function el(tag, attrs, ...children) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (k === 'class') node.className = v;
      else if (k === 'on') for (const [ev, fn] of Object.entries(v)) node.addEventListener(ev, fn);
      else if (v === true) node.setAttribute(k, '');
      else if (v !== false && v != null) node.setAttribute(k, v);
    }
    for (const c of children.flat()) if (c != null && c !== false) node.append(c.nodeType ? c : document.createTextNode(String(c)));
    return node;
  }
  const p = (text, cls) => el('p', { class: cls || '' }, text);
  const todo = (text) => p(text, 'todo');
  const dirText = (d) => (d === 1 ? '오른쪽으로 공격 →' : '← 왼쪽으로 공격');
  const dirSide = (d) => (d === 1 ? '화면 오른쪽' : '화면 왼쪽');
  function msgLine(id) { const m = ui.msg[id]; return m ? p(m.text, 'msg' + (m.bad ? ' bad' : '')) : null; }
  async function act(id, fn) {
    if (ui.busy) return;
    ui.busy = true; ui.msg[id] = { text: '처리 중입니다…' }; render(true);
    try { await fn(); ui.msg[id] = null; }
    catch (e) { ui.msg[id] = { text: e.message, bad: true, status: e.status }; }
    ui.busy = false; await refresh(true);
  }
  const jobBusy = () => !!(state.job && ['photos', 'choose', 'starting'].includes(state.job.phase));
  const memText = (m) => `컴퓨터 여유: 메모리 ${m.ram_gb ?? '?'} GB, 그래픽 메모리 ${m.vram_gb ?? '?'} GB`;

  // The two numbers of the own-team check. They are written in place by liveUpdate (classes), so a tap is never lost to a redraw.
  function numbers(c, big) {
    return el('div', { class: 'numbers' + (big ? ' bigger' : '') },
      el('div', {}, el('b', { class: 'own-now' }, c.own_now ?? '-'), el('span', {}, '우리 팀 지금')),
      el('div', {}, el('b', { class: 'own-mean' }, c.own_mean ?? '-'), el('span', { class: 'own-secs' }, `최근 ${c.seconds || 0}초 평균`)));
  }

  // The choice of the own team from the two groups of pictures (the existing /api/v1/team-select API).
  function colourPicker(s) {
    const c = s.colours;
    const make = () => act('colours', () => post('/api/v1/setup/team-photos', {}));
    // two groups: one press ("이 묶음이 우리 팀"), the other group is the opponent. Three or more (2026-11-25): the own group first, then the
    // opponent group ("이 묶음이 상대 팀"); the groups chosen by nobody (referee, coats) are left out.
    const many = c.groups.length > 2;
    const ask = (own, opp) => act('colours', async () => {
      const reply = await post('/api/v1/team-select/choose', many ? { group: own, opponent: opp, confirmed: false, created: c.created } : { group: own, confirmed: false, created: c.created });
      ui.pick = own; ui.opp = many ? opp : null; ui.sentence = reply.sentence; ui.reader = { on: reply.reader_on, text: reply.reader_text };
    });
    const choose = (index) => {
      if (!many) return ask(index);
      ui.pick = index; ui.opp = null; ui.sentence = null; ui.reader = null; render(true);
    };
    const chooseOpp = (index) => ask(ui.pick, index);
    const yes = () => act('colours', async () => {
      await post('/api/v1/team-select/choose', many ? { group: ui.pick, opponent: ui.opp, confirmed: true, created: c.created } : { group: ui.pick, confirmed: true, created: c.created });
      ui.pick = null; ui.opp = null; ui.sentence = null; ui.reader = null;
    });
    const reset = () => { ui.pick = null; ui.opp = null; ui.sentence = null; ui.reader = null; render(true); };
    const body = [];
    if (c.few_people) {
      body.push(el('div', { class: 'card warn' },
        p('선수가 적게 보였습니다. 선수들이 경기장에 퍼져 있을 때 다시 만들어 주세요.'),
        el('button', { class: 'big', type: 'button', disabled: ui.busy || jobBusy(), on: { click: make } }, '사진 다시 만들기')));
    }
    const ownPicked = many && ui.pick != null && ui.pick < c.groups.length;
    if (!many) body.push(todo('우리 팀 옷 색인 묶음을 누르세요.'));
    else body.push(todo(ownPicked ? `이제 상대 팀 옷 색인 묶음을 누르세요(${ORD[ui.pick]} 묶음은 우리 팀).` : '먼저 우리 팀 옷 색인 묶음을 누르세요. 그다음 상대 팀 묶음을 누릅니다.'));
    body.push(p(many ? '심판, 겉옷 입은 사람 같은 묶음은 누르지 않습니다(버려집니다). 우리 팀 옷 색을 모르면 코치에게 물어보세요.'
      : '우리 팀 옷 색을 모르면 코치에게 물어보세요. 심판이나 골키퍼는 섞여도 괜찮습니다.', 'small'));
    if (c.tries > 1) body.push(p(`팀 색을 ${c.tries}번 찍어 가장 뚜렷한 사진을 보여 줍니다.`, 'small'));
    if (c.weak) body.push(p('두 팀 색이 비슷하게 보입니다. 사진을 잘 보고 고르세요.', 'small bad'));
    // the run decides at its start whether the bib-colour reader is on (Small-box team reader ON/OFF); the server works it out for these pictures the same way
    if (c.reader_on === false && c.reader_text) body.push(el('div', { class: 'card problem reader-weak' }, p(c.reader_text, 'strong bad')));
    const groups = el('div', { class: 'groups' + (many ? ' groups-many' : '') });
    c.groups.forEach((g, i) => {
      const role = !many ? null : i === ui.pick ? '우리 팀' : i === ui.opp ? '상대 팀' : null;
      const buttons = [el('button', { class: 'pick', type: 'button', 'aria-pressed': ui.pick === i ? 'true' : 'false', disabled: ui.busy, on: { click: () => choose(i) } }, '이 묶음이 우리 팀')];
      if (ownPicked && i !== ui.pick) buttons.push(el('button', { class: 'pick pick-opp', type: 'button', 'aria-pressed': ui.opp === i ? 'true' : 'false', disabled: ui.busy, on: { click: () => chooseOpp(i) } }, '이 묶음이 상대 팀'));
      groups.append(el('div', { class: 'group' + (role ? ' chosen' : '') },
        el('h3', {}, `${ORD[i]} 묶음: ${g.colour} 옷`, many ? el('span', { class: 'ds-pill is-info group-people' }, `${g.people}명`) : null, role ? el('span', { class: 'ds-pill group-role' + (role === '상대 팀' ? ' is-alarm' : '') }, role) : null),
        el('div', { class: 'pics' }, g.urls.map((u) => el('img', { src: u, alt: '선수 사진' }))),
        ...buttons));
    });
    body.push(groups);
    if (ui.sentence) {
      const r = ui.reader || {};
      const readerLine = r.on === true ? p('두 팀 색이 잘 구분됩니다.', 'good strong reader-after') : r.on === false ? p(c.reader_text || r.text, 'bad strong reader-after') : null;
      body.push(el('div', { class: 'card warn' }, p(ui.sentence.replace('사진 왼쪽', '첫째 묶음').replace('사진 오른쪽', '둘째 묶음')), readerLine,
        el('div', { class: 'two' }, el('button', { class: 'big', type: 'button', on: { click: yes } }, '맞습니다'),
          el('button', { type: 'button', on: { click: reset } }, '아니요'))));
    }
    return body;
  }

  // ---- group 1: the steps (about 30 minutes before the kickoff) --------------------------------------------------------------------
  function stepMatch(s) {
    const done = !!s.match;
    const name = ui.name ?? (s.match ? s.match.name : s.suggested_name);
    const input = el('input', { id: 'match-name', value: name, autocapitalize: 'off', autocomplete: 'off', spellcheck: 'false', 'aria-label': '경기 이름',
      on: { input: (e) => { ui.name = e.target.value; ui.nameConflict = false; } } });
    const start = () => act('match', async () => {
      const value = (ui.name ?? name).trim();
      try { await post('/api/v1/setup/match', { name: value, mode: 'new', confirm: ui.newCode }); ui.name = null; ui.nameConflict = false; ui.newCode = ''; }
      catch (e) { if (e.status === 409 && /같은 이름/.test(e.message)) ui.nameConflict = true; throw e; }
    });
    const typed = (ui.name ?? name).trim();
    const code = el('input', { id: 'match-code', value: ui.newCode, inputmode: 'text', autocapitalize: 'off', autocomplete: 'off', maxlength: '4', 'aria-label': '확인 네 글자',
      on: { input: (e) => { ui.newCode = e.target.value; } } });
    const cont = () => act('match', async () => { await post('/api/v1/setup/match', { name: (ui.name ?? name).trim(), mode: 'continue' }); ui.name = null; ui.nameConflict = false; });
    const another = () => { const base = (ui.name ?? name).trim().replace(/-\d+$/, ''); ui.name = base + '-2'; ui.nameConflict = false; ui.msg.match = null; render(true); };
    return {
      id: 'match', title: '새 경기 시작', sub: done ? `경기 이름: ${s.match.name}` : '오늘 경기 이름을 정합니다', done,
      body: () => [
        done ? p(`지금 경기: ${s.match.name}. 다른 경기를 시작할 때만 아래를 누르세요.`, 'small') : todo('아래 이름 그대로 "새 경기 시작"을 누르세요.'),
        input,
        ui.nameConflict ? null : p('지난 경기의 팀 색과 팀 색 사진은 보관함으로 옮깁니다(지우지 않음). 점수와 기록은 새로 시작합니다.', 'small'),
        ui.nameConflict ? null : el('label', { class: 'code' }, el('span', {}, `실수 방지: 경기 이름의 마지막 네 글자 "${typed.slice(-4)}"를 넣으세요 (비밀번호 아님)`), code),
        ui.nameConflict
          ? el('div', { class: 'two' }, el('button', { type: 'button', on: { click: cont } }, '이어서 하기'), el('button', { type: 'button', on: { click: another } }, '새 이름으로'))
          : el('button', { class: done ? '' : 'big', type: 'button', disabled: ui.busy, on: { click: start } }, '새 경기 시작'),
        ui.nameConflict ? p('같은 이름의 경기가 이미 있습니다. 같은 경기를 이어 가면 "이어서 하기", 다른 경기면 "새 이름으로".', 'small') : null,
        msgLine('match'),
      ],
    };
  }

  function stepVideo(s) {
    const v = s.video;
    return {
      id: 'video', title: '영상 확인', sub: v.text, done: v.state === 'ok', problem: v.state === 'problem',
      body: () => [
        todo(v.state === 'ok' ? '영상이 들어오고 있습니다.' : v.state === 'problem' ? v.text : '휴대폰에서 송출을 시작하세요.'),
        v.state === 'wait' ? p('송출을 켰는데 30초가 지나도 영상이 안 보이면, 휴대폰 송출을 껐다가 다시 켜세요.', 'small') : null,
        v.state !== 'problem' && !v.recording ? p('녹화가 꺼져 있습니다. 담당자에게 알려 주세요(분석은 계속할 수 있습니다).', 'small bad') : null,
      ],
    };
  }

  function stepLines(s) {
    const answer = s.lines.answer;
    const done = answer === 'ok' || answer === 'skip';
    const send = (a) => act('lines', () => post('/api/v1/setup/lines', { answer: a }));
    if (!ui.linesAt && s.lines.can_draw) ui.linesAt = Date.now();
    return {
      id: 'lines', title: '경기장 선 확인', sub: answer === 'ok' ? '선이 맞음' : answer === 'skip' ? '안 맞지만 그대로 진행' : answer === 'bad' ? '선이 안 맞음' : '그림의 선이 경기장 선과 맞는지 봅니다',
      done, problem: answer === 'bad',
      body: () => [
        todo('분홍 선이 경기장의 흰 선 위에 겹치는지 보세요.'),
        s.lines.can_draw ? el('img', { class: 'picture', src: '/api/v1/setup/lines.jpg?t=' + ui.linesAt, alt: '경기장 선을 그린 그림' }) : p('영상이 들어오면 그림이 나옵니다.', 'small'),
        el('div', { class: 'examples' },
          el('span', { class: 'good' }, '맞음: 분홍 선이 흰 선(중앙선, 페널티 박스, 터치라인) 바로 위에 있음'),
          el('span', { class: 'bad' }, '안 맞음: 분홍 선이 흰 선에서 선수 한 명 키 이상 떨어져 있음')),
        el('div', { class: 'two' },
          el('button', { class: 'big', type: 'button', disabled: !s.lines.can_draw || ui.busy, on: { click: () => send('ok') } }, '맞음'),
          el('button', { type: 'button', disabled: !s.lines.can_draw || ui.busy, on: { click: () => send('bad') } }, '안 맞음')),
        answer === 'bad' ? p('담당자에게 연락하세요. 기다릴 수 없으면 "그대로 진행"을 누르세요. 선수 위치가 조금 틀릴 수 있습니다.', 'bad') : null,
        answer === 'bad' ? el('button', { type: 'button', on: { click: () => send('skip') } }, '그대로 진행') : null,
        el('button', { class: 'link', type: 'button', on: { click: () => { ui.linesAt = Date.now(); render(true); } } }, '그림 새로 보기'),
        msgLine('lines'),
      ],
    };
  }

  function stepColours(s) {
    const c = s.colours;
    const make = () => act('colours', () => post('/api/v1/setup/team-photos', {}));
    const body = [];
    const redoing = s.job && s.job.kind === 'recolour' && ['photos', 'choose', 'starting'].includes(s.job.phase);
    if (redoing) {
      body.push(todo('팀 색을 다시 찍는 중입니다.'), p('아래 "킥오프 직전" 묶음에서 이어서 하세요.', 'small'));
    } else if (c.state === 'ok') {
      body.push(todo('우리 팀을 골랐습니다(임시).'), p(c.text, 'small'), p('워밍업 때는 겉옷을 입거나 섞여 있어 틀릴 수 있습니다. 킥오프 직전에 아래 묶음에서 한 번 더 확인합니다.', 'small'));
      if (!s.analysis.running) body.push(el('button', { class: 'link', type: 'button', on: { click: make } }, '사진 다시 만들기'));
    } else if (c.state === 'making') {
      body.push(el('p', { class: 'todo spin' + (c.retake ? ' retake' : '') }, c.retake ? c.text : '사진을 만드는 중입니다. 약 1분 30초 걸립니다.'));
    } else if (c.state === 'choose') {
      body.push(...colourPicker(s));
      body.push(el('button', { class: 'link', type: 'button', on: { click: make } }, '사진 다시 만들기'));
    } else {
      body.push(todo(c.state === 'retry' ? c.text : '"팀 색 사진 만들기"를 누르세요.'));
      if (c.state !== 'retry') body.push(p('워밍업 중이어도 됩니다. 사진은 1분 동안의 영상으로 만듭니다(약 1분 30초). 틀리면 킥오프 직전에 다시 찍을 수 있습니다.', 'small'));
      body.push(el('button', { class: 'big', type: 'button', disabled: ui.busy || !s.match, on: { click: make } }, c.state === 'retry' ? '사진 다시 만들기' : '팀 색 사진 만들기'));
    }
    body.push(msgLine('colours'));
    return { id: 'colours', title: '팀 색 사진과 고르기 (임시)', sub: c.state === 'ok' ? c.text : '우리 팀 옷 색을 일단 고릅니다', done: c.state === 'ok' && !redoing, body: () => body };
  }

  function stepAnalysis(s) {
    const a = s.analysis, m = s.memory, d = s.direction;
    const start = () => act('analysis', () => post('/api/v1/setup/start', {}));
    const body = [];
    if (a.running) {
      body.push(todo('분석이 돌고 있습니다.'));
      body.push(p(d.confirmed ? `우리 팀 공격 방향: ${dirSide(d.value)}으로` : `공격 방향: 임시값(${dirSide(d.value)}). 킥오프 직전에 정합니다.`, 'small'));
      if (a.text) body.push(p(a.text, 'small'));
    } else {
      if (a.ended) {
        body.push(todo(a.text));
        body.push(el('button', { class: 'big', type: 'button', disabled: ui.busy, on: { click: () => act('analysis', () => post('/api/v1/setup/restart', {})) } }, '분석 다시 시작'));
      } else {
        body.push(todo('"분석 미리 시작"을 누르세요.'));
        body.push(p('워밍업 중에 켜 둡니다. 공격 방향은 묻지 않습니다(임시값으로 시작). 킥오프 직전에 아래 묶음에서 정합니다. 워밍업 동안의 알림은 화면에 나오지 않습니다.', 'small'));
        const mem = p(memText(m) + (m.state === 'ok' ? '' : ' · ' + m.text), m.state === 'ok' ? 'small' : (m.state === 'low' ? 'caution' : 'bad'));
        mem.className += ' mem-line';
        body.push(mem);
        body.push(el('button', { class: 'big', type: 'button', disabled: ui.busy || m.state === 'block' || s.colours.state !== 'ok' || jobBusy(), on: { click: start } }, '분석 미리 시작'));
        if (s.colours.state !== 'ok') body.push(p('팀 색을 먼저 고르세요.', 'small'));
      }
    }
    body.push(msgLine('analysis'));
    return { id: 'analysis', title: '분석 미리 시작', sub: a.running ? '분석 중' : a.ended ? '분석이 꺼졌습니다' : '워밍업 중에 켜 둡니다', done: a.running, problem: !!a.ended && !jobBusy(), body: () => body };
  }

  // The own-team numbers: never folded away, always shown (2026-11-24 rehearsal: they were inside a folded step).
  function checkBlock(s) {
    const c = s.check || {};
    const running = s.analysis.running;
    const box = el('section', { class: 'card check', 'aria-label': '우리 팀 인원 확인' }, el('h3', {}, '우리 팀 인원 확인'));
    if (!running) box.append(p('분석을 시작하면 여기에 숫자가 나옵니다.', 'small'));
    else if (c.waiting) box.append(el('p', { class: 'todo spin' }, '분석이 켜지는 중입니다. 1분쯤 기다리세요.'));
    else {
      box.append(numbers(c, false));
      box.append(p(c.few ? `우리 팀이 적게 보입니다(평균 ${FEW}명 미만). 킥오프 직전 묶음에서 "팀 색 다시 찍기"를 쓰세요.` : '6 이상이면 됩니다.', c.few ? 'bad' : 'small'));
      box.append(p(c.reader_text || '', 'small'));
    }
    const ready = running && c.seconds >= 30 && !c.few;
    return { node: box, done: !!ready };
  }

  // ---- group 2: just before the kickoff -----------------------------------------------------------------------------------------
  function group2(s, ready1) {
    const c = s.check || {}, d = s.direction, job = s.job, clock = s.clock.state;
    const wait = s.restart_seconds;
    const running = s.analysis.running;
    const node = [];
    if (clock !== 'before') return { nodes: [p('전반이 시작되어 여기서는 바꿀 수 없습니다.', 'small')], done: true };
    node.push(p('양 팀이 경기 옷으로 섰을 때 합니다. 워밍업 때는 겉옷을 입거나 섞여 있어 팀 색이 틀리게 잡혔을 수 있습니다.', 'small'));
    node.push(numbers(c, true));
    const good = c.own_now != null && c.own_now >= FEW && c.own_mean != null && c.own_mean >= FEW;
    if (!running) node.push(p(job && job.phase !== 'done' ? '' : '분석이 꺼져 있습니다. 위 "분석 미리 시작"(또는 맨 위 "분석 다시 시작")을 먼저 누르세요.', 'bad'));
    else node.push(p(good ? '6 이상입니다. "팀 색 그대로 사용"을 권합니다.' : '6보다 적습니다. 팀 색이 틀렸을 수 있습니다. "팀 색 다시 찍기"를 권합니다.', good ? 'good strong' : 'bad strong'));
    const kept = s.colours_kept;
    const recoloured = job && job.kind === 'recolour' && job.phase === 'done';
    if (job && job.kind === 'recolour' && ['photos', 'choose', 'starting', 'failed', 'done'].includes(job.phase)) {
      const cls = job.phase === 'failed' ? 'card problem' : job.phase === 'done' ? 'card done' : 'card warn';
      const inner = [p(job.text, 'strong' + (job.phase === 'failed' ? ' bad' : ''))];
      if (job.phase === 'photos') inner.push(el('p', { class: 'spin small' }, '기다리세요'));
      if (job.phase === 'choose' && s.colours.state === 'choose') inner.push(...colourPicker(s));
      if (job.phase === 'starting') inner.push(el('p', { class: 'spin small' }, '시작한 지 ', el('span', { class: 'job-elapsed' }, String(job.elapsed ?? 0)), '초'));
      node.push(el('div', { class: cls }, inner));
    }
    const busy = ui.busy || jobBusy() || !running;
    const keep = () => act('kickoff', () => post('/api/v1/setup/kickoff/colours-keep', {}));
    const redo = () => act('kickoff', () => post('/api/v1/setup/kickoff/recolour', {}));
    node.push(el('div', { class: 'two' },
      el('button', { class: good ? 'big' : '', type: 'button', disabled: busy, 'aria-pressed': kept ? 'true' : 'false', on: { click: keep } }, kept || recoloured ? '✓ 팀 색 그대로 사용' : '팀 색 그대로 사용'),
      el('button', { class: good ? '' : 'big', type: 'button', disabled: ui.busy || (jobBusy() && !(job && job.phase === 'choose')) || (!running && !(job && ['failed', 'choose'].includes(job.phase))), on: { click: redo } }, '팀 색 다시 찍기')));
    node.push(p(`"다시 찍기": 사진 약 1분 30초, 우리 팀을 고르면 분석이 저절로 다시 시작됩니다(약 ${wait}초 걸립니다). 그 사이 녹화와 영상은 계속됩니다.`, 'small'));
    // the colours from before "팀 색 다시 찍기" (P4, 2026-11-25): a warning when the new ones read fewer own players, and one press to bring the old ones back
    const prev = s.colours_previous;
    if (prev && prev.worse && prev.text) node.push(el('div', { class: 'card problem revert-warn', role: 'alert' }, p(prev.text, 'strong bad')));
    if (prev && prev.available) {
      const revert = () => act('kickoff', () => post('/api/v1/setup/kickoff/colours-revert', {}));
      node.push(el('button', { class: prev.worse ? 'big' : '', type: 'button', id: 'colours-revert', disabled: ui.busy || (jobBusy() && !(job && job.phase === 'choose')), on: { click: revert } }, prev.label));
      node.push(p(`"${prev.label}": 다시 찍기 전의 팀 색으로 돌아가고 분석이 저절로 다시 시작됩니다(약 ${wait}초).`, 'small'));
    }
    if (job && job.kind === 'revert' && ['starting', 'done', 'failed'].includes(job.phase)) {
      node.push(el('div', { class: job.phase === 'failed' ? 'card problem' : job.phase === 'done' ? 'card done' : 'card warn' }, p(job.text, 'strong')));
    }
    // the attack direction
    node.push(el('h3', { class: 'sub' }, '공격 방향'));
    node.push(p(d.confirmed ? `확정: 우리 팀은 ${dirSide(d.value)}으로 공격` : '아직 확정하지 않았습니다. 동전 던지기 뒤 방향을 누르세요. 방향은 휴대폰 화면 기준입니다.', d.confirmed ? 'good strong' : 'bad strong'));
    const go = (value) => act('kickoff', () => post('/api/v1/setup/kickoff/direction', { direction: value }));
    node.push(el('div', { class: 'two' },
      el('button', { class: 'pick', type: 'button', 'aria-pressed': d.confirmed && d.value === -1 ? 'true' : 'false', disabled: ui.busy || jobBusy(), on: { click: () => go(-1) } }, '← 왼쪽으로 공격'),
      el('button', { class: 'pick', type: 'button', 'aria-pressed': d.confirmed && d.value === 1 ? 'true' : 'false', disabled: ui.busy || jobBusy(), on: { click: () => go(1) } }, '오른쪽으로 공격 →')));
    node.push(p(`지금 분석과 방향이 다르면 분석이 저절로 다시 시작됩니다(약 ${wait}초). 같으면 그대로 확정만 합니다.`, 'small'));
    if (job && job.kind === 'direction' && ['starting', 'done', 'failed'].includes(job.phase)) {
      node.push(el('div', { class: job.phase === 'failed' ? 'card problem' : job.phase === 'done' ? 'card done' : 'card warn' }, p(job.text, 'strong')));
    }
    node.push(msgLine('kickoff'));
    const reverted = job && job.kind === 'revert' && job.phase === 'done';
    return { nodes: node, done: !!(running && (kept || recoloured || reverted) && d.confirmed && !jobBusy()) };
  }

  // ---- group 3: the kickoff ---------------------------------------------------------------------------------------------------------
  function group3(s, ready2) {
    const started = s.clock.marks.includes('start_h1');
    const nodes = [];
    if (started) {
      nodes.push(todo('전반이 시작되었습니다.'), p('이제 장면 표시 화면으로 갑니다.', 'strong'), el('a', { class: 'go', href: '/tag' }, '장면 표시 열기'),
        el('a', { class: 'go second', href: '/bench' }, '벤치 열기'));
      return { nodes, done: true };
    }
    const kick = () => {
      if (!confirm('전반 시작을 지금 기록할까요?')) return;
      act('kickoff3', async () => { await post('/api/v1/analyst-tags', { kind: 'start_h1', note: '' }); });
    };
    nodes.push(p('양 팀이 킥오프 위치에 서고 심판이 휘슬을 불 때 누르세요. (장면 표시 화면의 "전반 시작"과 같은 기록입니다.)', 'small'));
    if (!s.direction.confirmed) nodes.push(p('공격 방향을 아직 확정하지 않았습니다. 위 "킥오프 직전"에서 방향을 먼저 누르세요.', 'bad strong'));
    if (jobBusy()) nodes.push(p('분석이 다시 시작되는 중입니다. 끝나면 누르세요.', 'bad strong'));
    nodes.push(el('button', { class: 'huge', type: 'button', disabled: ui.busy || !s.direction.confirmed || jobBusy() || !s.match, on: { click: kick } }, '전반 시작'));
    nodes.push(msgLine('kickoff3'));
    return { nodes, done: false };
  }

  // ---- the part for trouble -----------------------------------------------------------------------------------------------------
  function trouble(s) {
    const a = s.analysis;
    const stop = () => act('trouble', async () => { await post('/api/v1/setup/stop', { confirm: ui.stopCode }); ui.stopCode = ''; ui.askStop = false; });
    const body = [p('평소에는 누르지 않습니다. 담당자의 말을 듣고 누르세요.', 'small')];
    if (!a.running) body.push(p('지금 돌고 있는 분석이 없습니다.', 'small'));
    else if (a.other && !a.mine) body.push(p(a.text, 'bad'));            // started elsewhere: never stopped from this page
    else if (!ui.askStop) {
      body.push(el('button', { class: 'stop', type: 'button', disabled: ui.busy, on: { click: () => { ui.askStop = true; render(true); } } }, '분석 멈춤'));
    } else {
      body.push(el('div', { class: 'card warn' },
        p('경기 중에는 멈추지 마세요. 멈추면 알림과 선수 위치가 끊깁니다.'),
        el('label', { class: 'code' }, el('span', {}, `실수 방지: 경기 이름의 마지막 네 글자 "${a.confirm_hint || ''}"를 넣으세요 (비밀번호 아님)`),
          el('input', { id: 'stop-code', value: ui.stopCode, autocapitalize: 'off', autocomplete: 'off', maxlength: '4', 'aria-label': '확인 네 글자', on: { input: (e) => { ui.stopCode = e.target.value; } } })),
        el('div', { class: 'two' },
          el('button', { class: 'stop', type: 'button', disabled: ui.busy, on: { click: stop } }, '멈춤 확인'),
          el('button', { type: 'button', on: { click: () => { ui.askStop = false; ui.stopCode = ''; render(true); } } }, '취소'))));
    }
    body.push(msgLine('trouble'));
    return el('section', { class: 'trouble card' }, el('h2', {}, '문제가 있을 때'), body);
  }

  // ---- drawing ----------------------------------------------------------------------------------------------------------------
  function groupCard(num, title, done, hint, content, cls) {
    return el('section', { class: 'gcard ' + (cls || '') + (done ? ' gdone' : '') },
      el('header', { class: 'ghead' }, el('span', { class: 'gnum', 'aria-hidden': 'true' }, done ? '✓' : String(num)), el('div', {}, el('h2', {}, title), el('p', { class: 'ghint' }, hint))),
      el('div', { class: 'gbody' }, content));
  }

  function render(force) {
    if (!state) return;
    const steps = [stepMatch(state), stepVideo(state), stepLines(state), stepColours(state), stepAnalysis(state)];
    const check = checkBlock(state);
    // Numbers that change every few seconds are written in place (liveUpdate) and do not redraw the page, so a tap is never lost.
    const quiet = { ...state, memory: { state: state.memory.state }, restart_seconds: state.restart_seconds, job: state.job && { ...state.job, elapsed: null },
      check: { ...state.check, own_now: null, own_mean: null, seconds: Math.min(30, state.check.seconds || 0), good: (state.check.own_now ?? 0) >= FEW && (state.check.own_mean ?? 0) >= FEW } };
    const sig = JSON.stringify([quiet, ui.pick, ui.opp, ui.reader, ui.sentence, ui.nameConflict, ui.msg, ui.busy, ui.open, ui.linesAt, ui.askStop]);
    if (!force && sig === lastSig) return;
    const active = document.activeElement;
    if (!force && active && ['match-name', 'match-code', 'stop-code'].includes(active.id)) return;            // do not redraw while the name is being typed
    lastSig = sig;
    const ready1 = steps.every((st) => st.done) && check.done;
    const g2 = group2(state, ready1);
    const g3 = group3(state, g2.done);
    let current = steps.findIndex((st) => !st.done);
    const list = el('ol', { class: 'steps' });
    steps.forEach((st, i) => {
      const cls = st.problem ? 'problem' : st.done ? 'done' : i === current ? 'now' : 'later';
      const open = ui.open[st.id] ?? (i === current || st.problem);
      const details = el('details', { class: 'step ' + cls, open: open },
        el('summary', {}, el('span', { class: 'num', 'aria-hidden': 'true' }, st.done ? '✓' : String(i + 1)),
          el('span', { class: 'title' }, st.title, el('span', { class: 'sub' }, st.sub || ''))),
        el('div', { class: 'body' }, st.body()));
      details.addEventListener('toggle', () => { const want = details.open; if (want !== (i === current || st.problem)) ui.open[st.id] = want; else delete ui.open[st.id]; });
      list.append(el('li', {}, details));
    });
    const g1content = [list, check.node];
    if (ready1) g1content.push(el('div', { class: 'card done' }, p('준비 끝. 킥오프 직전에 아래 묶음을 한 번 더 확인하세요.', 'strong')));
    const g1hint = ready1 ? '준비 끝' : current >= 0 ? `지금 할 일: ${steps[current].title}` : '지금 할 일: 우리 팀 인원 확인';
    const kicked = state.clock.marks.includes('start_h1');
    const root = $('groups');
    root.textContent = '';
    root.append(
      groupCard(1, '킥오프 30분 전 (워밍업 중)', ready1, g1hint, g1content, 'g1'),
      groupCard(2, '킥오프 직전 (양 팀이 경기 옷으로 섰을 때)', g2.done, g2.done ? '확인 끝' : '지금 할 일: 팀 색과 공격 방향 확인', g2.nodes, 'g2'),
      groupCard(3, '킥오프', g3.done, g3.done ? '전반이 시작됨' : '지금 할 일: 휘슬이 울리면 "전반 시작"', g3.nodes, 'g3'),
      trouble(state));
  }

  function liveUpdate() {
    const c = state.check || {}, m = state.memory;
    const set = (cls, text) => { for (const node of document.querySelectorAll('.' + cls)) node.textContent = text; };
    set('own-now', c.own_now ?? '-');
    set('own-mean', c.own_mean ?? '-');
    set('job-elapsed', state.job && state.job.elapsed != null ? state.job.elapsed : 0);
    set('own-secs', `최근 ${c.seconds || 0}초 평균`);
    set('mem-line', memText(m) + (m.state === 'ok' ? '' : ' · ' + m.text));
  }

  async function refresh(force) {
    try {
      const r = await fetch('/api/v1/setup', { cache: 'no-store' });
      if (!r.ok) throw new Error();
      const next = await r.json();
      const finished = state && state.colours.state !== 'ok' && next.colours.state === 'ok';
      state = next;
      if (finished || (state && next.colours.created !== state.colours.created)) { ui.pick = null; ui.opp = null; ui.reader = null; ui.sentence = null; }
      restartView();
      render(force);
      liveUpdate();
    } catch (e) { /* the next poll tries again */ }
  }
  refresh(true);
  setInterval(() => refresh(false), 3000);
})();
