// The match clock ("경기 전", "전반 12:34", "하프타임", "후반 03:10", "경기 끝") for every element that has the attribute data-match-clock.
// The server works it out (GET /api/v1/clock, app/analyst_tags.py:match_clock) from the four half marks; this file only counts the seconds up from the server time of the answer,
// so a wrong clock of the phone does not matter. The same file fills data-match-score with the score of /api/v1/score. When the server does not answer the last state keeps counting. Used by /bench, /tag, /live and /watch.
(() => {
  const two = n => String(n).padStart(2, '0');
  const mmss = s => `${two(Math.floor(s / 60))}:${two(Math.floor(s % 60))}`;
  // clock = answer of the server, serverNow = server time now (seconds)
  function text(clock, serverNow) {
    if (!clock) return '경기 전';
    const running = (name) => `${name} ${mmss(Math.max(0, serverNow - clock.since))}`;
    if (clock.state === 'h1' && typeof clock.since === 'number') return running('전반');
    if (clock.state === 'h2' && typeof clock.since === 'number') return running('후반');
    if (clock.state === 'break') return '하프타임';
    if (clock.state === 'over') return '경기 끝';
    return '경기 전';
  }
  // Alerts are shown only while a half is running, and only those written after that half started (analysis records itself from the warm-up on, but the warm-up is not coaching).
  // snap = the answer of /api/v1/bench (alerts carry age_s, seconds since the server first saw them); the alert records themselves are not touched, only what is shown.
  const QUIET = { before: '경기 전입니다. 알림은 전반 시작 뒤부터 나옵니다', break: '하프타임입니다. 알림은 후반 시작 뒤부터 나옵니다', over: '경기가 끝났습니다. 새 알림은 나오지 않습니다' };
  function gate(clock, serverNow, snap) {
    if (!snap || !clock) return snap;
    if ((clock.state === 'h1' || clock.state === 'h2') && typeof clock.since === 'number') {
      const limit = serverNow - clock.since;                                  // an alert older than the half is from before it started
      const fresh = a => a && a.age_s <= limit;
      return { ...snap, current: fresh(snap.current) ? snap.current : null, recent: (snap.recent || []).filter(fresh), quiet: null };
    }
    return { ...snap, current: null, recent: [], quiet: QUIET[clock.state] || QUIET.before };
  }
  if (typeof module !== 'undefined' && module.exports) module.exports = { text, gate };
  if (typeof document === 'undefined') return;
  let clock = null, offset = 0;
  const serverNow = () => Date.now() / 1000 + offset;
  const loadedAt = Date.now();
  // The bench answer as it may be shown now. Until the clock has been read (4 seconds at most) nothing is shown; a clock that never answers does not hide alerts for good.
  function gateSnap(snap) {
    if (!clock) return Date.now() - loadedAt < 4000 && snap ? { ...snap, current: null, recent: [], quiet: null } : snap;
    return gate(clock, serverNow(), snap);
  }
  window.MatchClock = { text: () => text(clock, serverNow()), state: () => (clock ? clock.state : 'before'), marks: () => (clock ? clock.marks : []), refresh: poll, gate: gateSnap };

  function render() {
    const value = text(clock, serverNow());
    for (const node of document.querySelectorAll('[data-match-clock]')) {
      if (node.textContent !== value) node.textContent = value;
      node.dataset.state = clock ? clock.state : 'before';
    }
  }
  async function poll() {
    try {
      const response = await fetch('/api/v1/clock', { cache: 'no-store', signal: AbortSignal.timeout(4000) });
      if (!response.ok) throw new Error(String(response.status));
      const data = await response.json();
      clock = data; offset = data.now - Date.now() / 1000;
    } catch (e) { /* keep counting from the last answer */ }
    render();
  }
  // The score as one line in every element with data-match-score (/live and /watch show it beside the clock; /bench has its own board).
  async function pollScore() {
    try {
      const response = await fetch('/api/v1/score', { cache: 'no-store', signal: AbortSignal.timeout(4000) });
      if (!response.ok) return;
      const data = await response.json();
      const value = data.session ? `우리 ${data.ours} : ${data.opp} 상대` : '우리 - : - 상대';
      for (const node of document.querySelectorAll('[data-match-score]')) node.textContent = value;
    } catch (e) { /* keep the last score */ }
  }
  render(); poll();
  if (document.querySelector('[data-match-score]')) { pollScore(); setInterval(pollScore, 2000); }
  setInterval(poll, 2000);
  setInterval(render, 250);
})();
