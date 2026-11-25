// Red band with sound for a stop of the live run, a prompt for the half-time report, and a small "전반 끝" button.
// Loaded by /watch and by the bench screen. It only reads /api/v1/service and /api/v1/halftime and posts to the small service routes (app/service_routes.py).
(() => {
  if (window.__watchBanner) return;
  window.__watchBanner = true;
  const LOST_AFTER = 6000;        // ms without an answer of the server before the band says that the server does not answer
  let openMore = false, state = null, halftime = null, lastOk = Date.now(), failed = false, sound = false, notify = false, ctx = null, beeped = new Set(), lastOutage = null, serverDownAt = null, recovered = null;
  try { sound = localStorage.getItem('watch-sound') === '1'; notify = localStorage.getItem('watch-notify') === '1'; } catch (e) { /* storage may be blocked */ }

  const style = document.createElement('style');
  style.textContent = `
    #wb { position: sticky; top: 0; z-index: 50; font-family: var(--font, system-ui, "Noto Sans KR", "Malgun Gothic", sans-serif); }
    #wb .bar { display: none; align-items: center; gap: 16px; flex-wrap: wrap; padding: 14px 22px; color: #fff; font-size: 1.25rem; font-weight: 700; line-height: 1.4; }
    #wb .bar.show { display: flex; }
    #wb .bar.down { background: var(--c-alarm, #c0161b); animation: wbpulse 1s infinite alternate; border-bottom: 3px solid #fff; }
    #wb .bar.down b::before { content: "⚠ "; }
    #wb .bar { position: relative; }
    #wb .bar.back { background: var(--c-pitch-soft, #163a27); color: var(--c-text, #eef3ee); border-bottom: 2px solid var(--c-pitch, #40d678); }
    #wb .bar.ask { background: var(--c-lamp-soft, #3a3313); color: var(--c-text, #eef3ee); border-bottom: 2px solid var(--c-lamp, #ffcd28); }
    #wb .bar.ask a { color: var(--c-lamp, #ffcd28) !important; }
    #wb .bar b { font-size: 1.9rem; font-weight: 900; } #wb .bar .grow { flex: 1; min-width: 200px; }
    #wb button, .wb-half { font: inherit; font-size: 1.05rem; font-weight: 700; min-height: 44px; padding: 8px 16px; border-radius: var(--r-sm, 9px); border: 2px solid #fff; background: rgba(0,0,0,.25); color: #fff; cursor: pointer; touch-action: manipulation; }
    #wb .bar.ask button, #wb .bar.back button { border: 1px solid var(--c-line-2, #3b5a47); background: var(--c-card-2, #18291f); color: var(--c-text, #eef3ee); }
    .wb-halfbar { position: fixed; left: 0; right: 0; bottom: 0; z-index: 40; display: flex; gap: 8px; justify-content: flex-end; padding: 8px 16px; background: var(--c-card, #122019); border-top: 1px solid var(--c-line, #24392c); box-shadow: var(--sh-float, 0 -8px 24px rgba(0,0,0,.45)); }
    .wb-half { background: var(--c-card-2, #18291f); border: 1px solid var(--c-line-2, #3b5a47); color: var(--c-text, #eef3ee); border-radius: var(--r-md, 14px); }
    #wb .wbrow { display: flex; flex-wrap: nowrap; gap: 8px; align-items: center; }
    #wb .wbrow button.wbbig { font-weight: 900; min-height: 48px; font-size: 1.2rem; background: #fff; color: var(--c-alarm-2, #7d0d11); }
    #wb details.wbmore > summary { list-style: none; cursor: pointer; font: inherit; font-size: 1.05rem; padding: 8px 16px; border-radius: var(--r-sm, 9px); border: 2px solid #fff; background: rgba(0,0,0,.25); color: #fff; white-space: nowrap; min-height: 44px; display: flex; align-items: center; }
    #wb details.wbmore > summary::-webkit-details-marker { display: none; }
    #wb details.wbmore .items { display: flex; flex-wrap: wrap; gap: 8px; position: absolute; left: 0; right: 0; top: 100%; padding: 10px 12px; background: #3a0a0c; border-bottom: 2px solid #fff; z-index: 2; }
    body { padding-bottom: 84px; }
    @keyframes wbpulse { from { background: var(--c-alarm, #c0161b); } to { background: var(--c-alarm-2, #7d0d11); } }
    @media (prefers-reduced-motion: reduce) { #wb .bar.down { animation: none; } }
    @media (max-width: 640px) {
      #wb .bar { padding: 8px 12px; gap: 4px 8px; font-size: .95rem; }
      #wb .bar.down .grow { flex: 1 1 100%; }
      #wb .bar.down .wbrow { flex: 1 1 100%; }
      #wb .wbrow button.wbbig { flex: 1 1 auto; font-size: 1rem; min-height: 44px; }
      #wb details.wbmore > summary { font-size: .9rem; padding: 6px 10px; min-height: 44px; border-width: 1px; }
      #wb .bar b { font-size: 1.15rem; }
      #wb .bar .grow { min-width: 0; flex: 1 1 auto; }
      #wb .bar .more { display: none; }
      #wb button { font-size: .9rem; padding: 6px 10px; border-width: 1px; }
      .wb-halfbar { padding: 6px 12px; }
      .wb-half { flex: 1 1 0; min-height: 44px; font-size: .88rem; padding: 6px 8px; }
      body { padding-bottom: 64px; }
    }`;
  document.head.append(style);
  const box = document.createElement('div');
  box.id = 'wb';
  const down = document.createElement('div'); down.className = 'bar down'; down.setAttribute('role', 'alert');
  const back = document.createElement('div'); back.className = 'bar back'; back.setAttribute('role', 'status');
  const ask = document.createElement('div'); ask.className = 'bar ask'; ask.setAttribute('role', 'status');
  const colour = document.createElement('div'); colour.className = 'bar ask'; colour.setAttribute('role', 'status');
  box.append(down, back, ask, colour);
  document.body.prepend(box);
  // The two half buttons sit in one bar above the bottom tabs, so they never cover the page.
  const halfBar = document.createElement('div'); halfBar.className = 'wb-halfbar';
  const halfButton = document.createElement('button');
  halfButton.className = 'wb-half'; halfButton.textContent = '전반 끝 · 보고서 만들기';
  const secondButton = document.createElement('button');
  secondButton.className = 'wb-half'; secondButton.textContent = '후반 시작 · 공격 방향 바꿈';
  halfBar.append(halfButton, secondButton);
  document.body.append(halfBar);

  const text = (tag, value, cls) => { const e = document.createElement(tag); e.textContent = value; if (cls) e.className = cls; return e; };
  const button = (label, fn) => { const b = text('button', label); b.addEventListener('click', fn); return b; };
  // Short part always shown; the longer explanation (class "more") is hidden on phones by the style above.
  const two = (short, more) => { const s = text('span', short, 'grow'); if (more) s.append(text('span', ' ' + more, 'more')); return s; };
  const post = (url, body) => fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }).then(r => r.json());
  // The half buttons also write the clock mark of the tag page (once), so one press does both jobs.
  async function markOnce(kind) {
    try {
      const clock = await fetch('/api/v1/clock', { cache: 'no-store' }).then(r => r.json());     // the marks of THIS match (not of the whole day)
      if ((clock.marks || []).includes(kind)) return;
      await post('/api/v1/analyst-tags', { kind, note: '' });
      if (window.MatchClock) window.MatchClock.refresh();
    } catch (e) { /* the mark can still be pressed by hand on the tag page */ }
  }
  const secondsText = s => { s = Math.max(0, Math.floor(s)); return s < 60 ? `${s}초` : s < 3600 ? `${Math.floor(s / 60)}분 ${s % 60}초` : `${Math.floor(s / 3600)}시간 ${Math.floor(s % 3600 / 60)}분`; };
  const clockText = ms => new Date(ms).toLocaleTimeString('ko-KR', { hour12: false });

  // The sound is played once when a red band first appears (one key per stop, 'server' for the screen losing the server), never repeated while the band stays.
  function beepOnce(key) { if (beeped.has(key)) return; beeped.add(key); beep(); }
  window.__watchBeeps = beeped;
  function beep() {
    if (!sound) return;
    try {
      ctx = ctx || new (window.AudioContext || window.webkitAudioContext)();
      if (ctx.state === 'suspended') ctx.resume();
      for (const [offset, freq] of [[0, 880], [0.28, 660]]) {
        const osc = ctx.createOscillator(), gain = ctx.createGain();
        osc.type = 'square'; osc.frequency.value = freq; gain.gain.value = 0.12;
        osc.connect(gain); gain.connect(ctx.destination);
        osc.start(ctx.currentTime + offset); osc.stop(ctx.currentTime + offset + 0.22);
      }
    } catch (e) { /* no audio: the red band stays */ }
  }

  function systemNotice(title, body) {
    if (!notify || !('Notification' in window) || Notification.permission !== 'granted') return;
    try { new Notification(title, { body, tag: 'live-stop' }); } catch (e) { /* not allowed on this page */ }
  }

  // One row of buttons: the one that matters (set by the caller, big) and "더 보기" with the rest (sound, notice, 확인함, 경기 끝).
  function controls(parent, ackable, primary) {
    const row = document.createElement('div'); row.className = 'wbrow';
    if (primary) row.append(primary);
    const more = document.createElement('details'); more.className = 'wbmore';
    more.append(text('summary', '더 보기'));
    const items = document.createElement('div'); items.className = 'items';
    if (!sound) items.append(button('경고음 켜기',() => { sound = true; try { localStorage.setItem('watch-sound', '1'); } catch (e) {} beep(); render(); }));
    if (!notify && 'Notification' in window && Notification.permission !== 'denied') items.append(button('알림 켜기', async () => {
      const result = await Notification.requestPermission();
      notify = result === 'granted'; try { localStorage.setItem('watch-notify', notify ? '1' : '0'); } catch (e) {} render();
    }));
    if (ackable && state && state.session) {
      items.append(button('확인함', () => post('/api/v1/service/ack', { session: state.session }).then(poll)));
      items.append(button('경기 끝', () => { if (confirm('이 라이브 실행을 끝난 것으로 처리할까요? 멈춤 기록이 닫히고 경고가 사라집니다.')) post('/api/v1/service/finish', { session: state.session }).then(poll); }));
    }
    more.append(items);
    // the list is rebuilt twice a second: an opened "더 보기" stays open
    if (openMore) more.open = true;
    more.addEventListener('toggle', () => { openMore = more.open; });
    row.append(more);
    parent.append(row);
  }

  function render() {
    down.replaceChildren(); back.replaceChildren(); ask.replaceChildren(); colour.replaceChildren();
    for (const bar of [down, back, ask, colour]) bar.classList.remove('show');
    const offline = failed && Date.now() - lastOk > LOST_AFTER;
    if (offline) {
      serverDownAt = serverDownAt || lastOk;
      down.classList.add('show');
      down.append(text('b', '서버 응답 없음'), two(`${clockText(serverDownAt)}부터 ${secondsText((Date.now() - serverDownAt) / 1000)}`, '이 화면이 서버와 연결되지 않습니다. 라이브 분석이 도는지 알 수 없습니다.'));
      controls(down, false, null); beepOnce('server-' + serverDownAt); document.title = '⚠ 서버 응답 없음';
      return;
    }
    if (serverDownAt) { recovered = { text: `서버 연결이 돌아왔습니다 (끊긴 시간 ${secondsText((Date.now() - serverDownAt) / 1000)}).`, at: Date.now() }; serverDownAt = null; }
    if (state && state.state === 'down') {
      down.classList.add('show');
      down.append(text('b', state.headline), two(`${state.since_text}부터 ${state.duration_text} 멈춤`, state.detail));
      let primary = null;
      if (state.cause === 'process_dead') {
        // The run ended (stopped by a person or by itself): one press starts it again for the same match (app/setup_routes.py, /api/v1/setup/restart).
        primary = button('분석 다시 시작', async (ev) => {
          ev.target.disabled = true;
          try {
            const r = await fetch('/api/v1/setup/restart', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
            const data = await r.json().catch(() => ({}));
            alert(r.ok ? '분석을 다시 시작했습니다. 10초쯤 뒤에 화면이 돌아옵니다.' : (data.detail || '다시 시작하지 못했습니다.') + ' 경기 준비 화면(/setup)을 여세요.');
          } catch (e) { alert('다시 시작하지 못했습니다. 경기 준비 화면(/setup)을 여세요.'); }
          ev.target.disabled = false; poll();
        });
        primary.classList.add('wbbig');
      }
      controls(down, true, primary);
      beepOnce('outage-' + state.outage_id);
      document.title = '⚠ ' + state.headline;
      if (!lastOutage || lastOutage !== state.outage_id) { lastOutage = state.outage_id; systemNotice('라이브 분석 중단', `${state.headline} (${state.since_text}부터)`); }
    } else {
      document.title = document.title.replace(/^⚠ /, '');
      if (recovered && Date.now() - recovered.at < 30000) { back.classList.add('show'); back.append(text('b', '복구'), text('span', recovered.text, 'grow')); }
    }
    if (halftime && halftime.status === 'suggested') {
      ask.classList.add('show');
      ask.append(text('span', halftime.text, 'grow'),
        button('맞음, 보고서 만들기', () => post('/api/v1/halftime/start', { session: halftime.session, end_s: halftime.end_s, confirmed: true }).then(poll)),
        button('아님', () => post('/api/v1/halftime/dismiss', { session: halftime.session, end_s: halftime.end_s }).then(poll)));
    } else if (halftime && halftime.status === 'making') {
      ask.classList.add('show'); ask.append(text('span', '하프타임 보고서를 만드는 중입니다…', 'grow'));
    } else if (halftime && halftime.status === 'ready') {
      ask.classList.add('show');
      const link = document.createElement('a'); link.href = halftime.link; link.target = '_blank'; link.rel = 'noopener'; link.textContent = '보고서 열기'; link.style.cssText = 'color:var(--c-lamp,#ffcd28);font-size:1.25rem;font-weight:900';
      if (halftime.source === 'auto') {
        ask.append(text('span', '영상이 끊겨서 하프타임 보고서를 자동으로 만들었습니다. 전반이 끝난 것이 맞습니까?', 'grow'), link,
          button('맞음', () => post('/api/v1/halftime/confirm', { session: halftime.session }).then(poll)),
          button('아님', () => post('/api/v1/halftime/dismiss', { session: halftime.session }).then(poll)));
      } else ask.append(text('span', `하프타임 보고서가 준비되었습니다 (영상 시각 ${halftime.end_text || ''}까지).`, 'grow'), link);
    }
    const sh = halftime && halftime.second_half;
    if (sh && !sh.colour_checked) {
      colour.classList.add('show');
      colour.append(text('span', `후반으로 넘어갔습니다 (${sh.at_text}). 팀 색 재확인: 두 팀이 옷 색대로 나뉘어 표시되는지 화면에서 확인해 주세요. 지금 우리 팀은 ${sh.attack_text}으로 공격합니다.`, 'grow'),
        button('확인했음', () => post('/api/v1/halftime/colour-checked', { session: halftime.session }).then(poll)));
    }
  }

  secondButton.addEventListener('click', async () => {
    const next = halftime && halftime.next_second_half;
    if (!next) {
      if (halftime && halftime.second_half) { alert('이미 후반으로 넘어갔습니다.'); markOnce('start_h2'); return; }      // the clock follows the switch even when its mark was lost the first time
      // No positions: the analysis cannot be switched, but the match clock must not stay at half time. Only the clock, and only after a question.
      if (confirm('위치 기록이 아직 없어 분석은 후반으로 넘길 수 없습니다. 시계만 후반으로 바꿀까요?')) { await markOnce('start_h2'); }
      return;
    }
    if (!confirm(`후반으로 넘어갑니다. ${next.team}팀이 ${next.attack_text}으로 공격합니다. 맞습니까?
(전반 기록은 그대로 보관됩니다.)`)) return;
    try { await post('/api/v1/halftime/second-half', { session: halftime.session }); markOnce('start_h2'); } catch (e) { alert('후반으로 넘기지 못했습니다.'); }
    poll();
  });

  halfButton.addEventListener('click', async () => {
    if (!confirm('전반이 끝났습니까? 지금까지의 위치 기록으로 하프타임 보고서를 만듭니다.')) return;
    try { halftime = await post('/api/v1/halftime/start', { session: (state && state.session) || null }); markOnce('end_h1'); } catch (e) { alert('보고서를 시작하지 못했습니다.'); }
    render(); poll();
  });

  async function poll() {
    try {
      const [s, h] = await Promise.all([fetch('/api/v1/service', { cache: 'no-store' }), fetch('/api/v1/halftime', { cache: 'no-store' })]);
      if (!s.ok) throw new Error(String(s.status));
      const before = state && state.state;
      state = await s.json(); halftime = h.ok ? await h.json() : null;
      if (before === 'down' && state.state !== 'down') {
        const o = (state.outages || []).find(x => x.id === lastOutage && !x.open);
        recovered = { at: Date.now(), text: o ? `${o.since_text}에 멈췄다가 ${o.ended_text}에 돌아왔습니다 (${o.duration_text}). 이 구간은 알림과 위치 기록이 없습니다.` : '라이브 분석이 돌아왔습니다.' };
      }
      lastOk = Date.now(); failed = false;
      window.dispatchEvent(new CustomEvent('watch-state', { detail: { state, halftime } }));
    } catch (e) { failed = true; }
    render();
  }
  poll();
  setInterval(poll, 2000);
  setInterval(render, 500);
})();
