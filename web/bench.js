// Coach's bench screen: polls /api/v1/bench once a second (read only), keeps the last answer when the request fails and says so in the band.
(() => {
  const el = id => document.getElementById(id);
  const STALE_AFTER = 15;       // seconds after which the big alert is dimmed (wiki/live-operations-research.md R3: an old alert is no longer an instruction)
  const LOST_AFTER = 5;         // seconds without any answer of the server before the band says the screen itself lost its connection
  let last = null, receivedAt = 0, lastOk = 0, failed = false;

  const clock = seconds => {
    const s = Math.max(0, Math.floor(seconds));
    return s < 60 ? `${s}초 전` : `${Math.floor(s / 60)}분 ${s % 60}초 전`;
  };
  const ageOf = alert => alert.age_s + (Date.now() - receivedAt) / 1000;

  function renderBand() {
    const band = el('band'), state = el('band-state'), detail = el('band-detail'), link = el('band-link');
    const offline = failed && (Date.now() - lastOk) / 1000 > LOST_AFTER;
    link.textContent = '';
    if (offline) {
      band.className = 'band lost';
      state.textContent = '화면 연결 끊김';
      detail.textContent = `서버 응답 없음 (마지막 확인 ${clock((Date.now() - lastOk) / 1000)}). 아래 내용은 마지막으로 받은 값입니다`;
      return;
    }
    if (!last) { band.className = 'band unknown'; state.textContent = '연결 중'; detail.textContent = ''; return; }
    const s = last.state || {};
    if (s.state === 'ok') { band.className = 'band ok'; state.textContent = '입력 정상'; detail.textContent = s.reason + (s.since_s == null ? '' : ` (마지막 하트비트 ${clock(s.since_s + (Date.now() - receivedAt) / 1000)})`); }
    else if (s.state === 'no_input') { band.className = 'band lost'; state.textContent = '입력 없음'; detail.textContent = `${s.reason}. 이 동안에는 새 알림이 나오지 않습니다`; }
    else { band.className = 'band unknown'; state.textContent = '입력 상태 모름'; detail.textContent = s.reason + (last.file_age_s == null ? '' : ` (알림 파일 마지막 변경 ${clock(last.file_age_s + (Date.now() - receivedAt) / 1000)})`); }
    link.textContent = last.session ? `세션 ${last.session}` : '';
  }

  function renderAlert() {
    const current = last && last.current;
    el('empty').hidden = !!current; el('alert').hidden = !current;
    el('empty').textContent = (last && last.quiet) || '아직 알림이 없습니다';
    const box = el('current');
    box.dataset.priority = current ? current.priority : '';
    if (!current) { box.classList.remove('stale'); return; }
    el('badge').textContent = current.priority_text;
    const age = ageOf(current);
    el('age').textContent = clock(age) + (current.age_estimated ? ' (이전에 나온 알림, 시간 추정)' : '');
    el('title').textContent = current.line || current.title;                // the short line; the full words stay under "자세히"
    el('full-title').textContent = current.line && current.line !== current.title ? current.title : '';
    el('line').textContent = current.text;
    el('more').hidden = !current.text && !el('full-title').textContent;
    const proof = el('proof');
    proof.textContent = current.accuracy ? `이 종류의 알림: ${current.accuracy.text}` : '';
    proof.className = 'proof' + (current.accuracy && current.accuracy.low_sample ? ' low' : '');
    box.classList.toggle('stale', age > STALE_AFTER);
  }

  function renderRecent() {
    const list = el('recent');
    el('recent-title').textContent = `이전 알림 ${((last && last.recent) || []).length}개`;
    list.replaceChildren();
    for (const alert of (last && last.recent) || []) {
      const item = document.createElement('li');
      item.dataset.priority = alert.priority;
      const title = document.createElement('b'); title.textContent = `${alert.priority_text} · ${alert.line || alert.title}`;     // one line per alert
      const small = document.createElement('small'); small.textContent = clock(ageOf(alert));
      item.append(title, small);
      list.append(item);
    }
  }

  const render = () => { renderBand(); renderAlert(); renderRecent(); };

  async function poll() {
    try {
      const response = await fetch('/api/v1/bench', { cache: 'no-store' });
      if (!response.ok) throw new Error(String(response.status));
      last = await response.json();
      if (window.MatchClock) last = window.MatchClock.gate(last);                 // before the first half, at half time and after the match no alert is shown; in a half only those written after it started
      receivedAt = Date.now(); lastOk = receivedAt; failed = false;
    } catch (error) { failed = true; }
    render();
  }
  poll();
  setInterval(poll, 1000);
  setInterval(render, 250);     // the ages count up between two answers of the server
})();
