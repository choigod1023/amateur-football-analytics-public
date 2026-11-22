// Red band with sound for a stop of the live run, a prompt for the half-time report, and a small "전반 끝" button.
// Loaded by /watch and by the bench screen. It only reads /api/v1/service and /api/v1/halftime and posts to the small service routes (app/service_routes.py).
(() => {
  if (window.__watchBanner) return;
  window.__watchBanner = true;
  const LOST_AFTER = 6000;        // ms without an answer of the server before the band says that the server does not answer
  let state = null, halftime = null, lastOk = Date.now(), failed = false, sound = false, notify = false, ctx = null, beeped = new Set(), lastOutage = null, serverDownAt = null, recovered = null;
  try { sound = localStorage.getItem('watch-sound') === '1'; notify = localStorage.getItem('watch-notify') === '1'; } catch (e) { /* storage may be blocked */ }

  const style = document.createElement('style');
  style.textContent = `
    #wb { position: sticky; top: 0; z-index: 50; font-family: system-ui, "Noto Sans KR", "Malgun Gothic", sans-serif; }
    #wb .bar { display: none; align-items: center; gap: 16px; flex-wrap: wrap; padding: 14px 22px; color: #fff; font-size: 1.25rem; }
    #wb .bar.show { display: flex; }
    #wb .bar.down { background: #c0161b; animation: wbpulse 1s infinite alternate; }
    #wb .bar.back { background: #1f7a45; } #wb .bar.ask { background: #8a5a00; }
    #wb .bar b { font-size: 1.9rem; } #wb .bar .grow { flex: 1; min-width: 200px; }
    #wb button, .wb-half { font: inherit; font-size: 1.05rem; padding: 8px 16px; border-radius: 8px; border: 2px solid #fff; background: rgba(0,0,0,.25); color: #fff; cursor: pointer; }
    .wb-half { position: fixed; right: 16px; bottom: 16px; z-index: 40; background: #1b2a3a; border-color: #5b7a99; }
    body { padding-bottom: 84px; }
    @keyframes wbpulse { from { background: #c0161b; } to { background: #7d0d11; } }
    @media (prefers-reduced-motion: reduce) { #wb .bar.down { animation: none; } }`;
  document.head.append(style);
  const box = document.createElement('div');
  box.id = 'wb';
  const down = document.createElement('div'); down.className = 'bar down'; down.setAttribute('role', 'alert');
  const back = document.createElement('div'); back.className = 'bar back'; back.setAttribute('role', 'status');
  const ask = document.createElement('div'); ask.className = 'bar ask'; ask.setAttribute('role', 'status');
  const colour = document.createElement('div'); colour.className = 'bar ask'; colour.setAttribute('role', 'status');
  box.append(down, back, ask, colour);
  document.body.prepend(box);
  const halfButton = document.createElement('button');
  halfButton.className = 'wb-half'; halfButton.textContent = '전반 끝';
  const secondButton = document.createElement('button');
  secondButton.className = 'wb-half'; secondButton.textContent = '후반 시작'; secondButton.style.right = '120px';
  document.body.append(halfButton, secondButton);

  const text = (tag, value, cls) => { const e = document.createElement(tag); e.textContent = value; if (cls) e.className = cls; return e; };
  const button = (label, fn) => { const b = text('button', label); b.addEventListener('click', fn); return b; };
  const post = (url, body) => fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }).then(r => r.json());
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

  function controls(parent, ackable) {
    if (!sound) parent.append(button('소리 켜기', () => { sound = true; try { localStorage.setItem('watch-sound', '1'); } catch (e) {} beep(); render(); }));
    if (!notify && 'Notification' in window && Notification.permission !== 'denied') parent.append(button('브라우저 알림 켜기', async () => {
      const result = await Notification.requestPermission();
      notify = result === 'granted'; try { localStorage.setItem('watch-notify', notify ? '1' : '0'); } catch (e) {} render();
    }));
    if (ackable && state && state.session) {
      parent.append(button('소리 끄기', () => post('/api/v1/service/ack', { session: state.session }).then(poll)));
      parent.append(button('경기 끝, 감시 종료', () => { if (confirm('이 라이브 실행을 끝난 것으로 처리할까요? 멈춤 기록이 닫히고 경고가 사라집니다.')) post('/api/v1/service/finish', { session: state.session }).then(poll); }));
    }
  }

  function render() {
    down.replaceChildren(); back.replaceChildren(); ask.replaceChildren(); colour.replaceChildren();
    for (const bar of [down, back, ask, colour]) bar.classList.remove('show');
    const offline = failed && Date.now() - lastOk > LOST_AFTER;
    if (offline) {
      serverDownAt = serverDownAt || lastOk;
      down.classList.add('show');
      down.append(text('b', '서버 응답 없음'), text('span', `이 화면이 서버와 연결되지 않습니다 (${clockText(serverDownAt)}부터 ${secondsText((Date.now() - serverDownAt) / 1000)}). 라이브 분석이 도는지 알 수 없습니다.`, 'grow'));
      controls(down, false); beepOnce('server-' + serverDownAt); document.title = '⚠ 서버 응답 없음';
      return;
    }
    if (serverDownAt) { recovered = { text: `서버 연결이 돌아왔습니다 (끊긴 시간 ${secondsText((Date.now() - serverDownAt) / 1000)}).`, at: Date.now() }; serverDownAt = null; }
    if (state && state.state === 'down') {
      down.classList.add('show');
      down.append(text('b', state.headline), text('span', `${state.since_text}부터 ${state.duration_text} 동안 멈춤. ${state.detail}`, 'grow'));
      controls(down, true);
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
      const link = document.createElement('a'); link.href = halftime.link; link.target = '_blank'; link.rel = 'noopener'; link.textContent = '보고서 열기'; link.style.cssText = 'color:#fff;font-size:1.25rem;font-weight:700';
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
    if (!next) { alert(halftime && halftime.second_half ? '이미 후반으로 넘어갔습니다.' : '위치 기록이 아직 없어 후반으로 넘길 수 없습니다.'); return; }
    if (!confirm(`후반으로 넘어갑니다. ${next.team}팀이 ${next.attack_text}으로 공격합니다. 맞습니까?
(전반 기록은 그대로 보관되고, 분석이 처음부터 다시 시작됩니다.)`)) return;
    try { await post('/api/v1/halftime/second-half', { session: halftime.session }); } catch (e) { alert('후반으로 넘기지 못했습니다.'); }
    poll();
  });

  halfButton.addEventListener('click', async () => {
    if (!confirm('전반이 끝났습니까? 지금까지의 위치 기록으로 하프타임 보고서를 만듭니다.')) return;
    try { halftime = await post('/api/v1/halftime/start', { session: (state && state.session) || null }); } catch (e) { alert('보고서를 시작하지 못했습니다.'); }
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
