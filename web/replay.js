// Replay of recorded matches: the recorded parts of one match play one after another and one bar (own controls) covers the whole match.
// The time arithmetic (match time <-> part and time inside it, breaks, steps) is in replay-time.js (pure, tested).
(() => {
  const $ = id => document.getElementById(id);
  const seek = $('seek'), select = $('match'), stage = $('stage');
  const RT = window.ReplayTime;
  const PRELOAD_AT = 10;                                // seconds before the end of a part at which the next part is loaded into the hidden player
  const players = [$('video'), $('video2')];            // one is shown, the other one waits with the next part, so the change of part does not wait for a load
  let match = null, index = 0, rate = 1, dragging = false, shown = 0, waitingFor = -1;
  let pending = null, switching = false, wantPlay = false, muted = false;   // pending: the match time we are going to (the clock shows it until the player is there)
  const current = () => players[shown], spare = () => players[1 - shown];

  const fmt = s => {
    s = Math.max(0, Math.floor(s || 0));
    const h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60), r = s % 60;
    return (h ? h + ':' + String(m).padStart(2, '0') : m) + ':' + String(r).padStart(2, '0');
  };
  const span = s => {                                  // a length in words: "1시간 5분", "10분"
    const m = Math.round((s || 0) / 60), h = Math.floor(m / 60);
    return h ? h + '시간' + (m % 60 ? ' ' + m % 60 + '분' : '') : Math.max(1, m) + '분';
  };
  const problem = text => { const p = $('problem'); p.hidden = !text; p.textContent = text || ''; };
  const global = () => match ? RT.toGlobal(match.pieces, index, current().currentTime || 0) : 0;
  const shownTime = () => pending !== null ? pending : global();

  const urlOf = i => new URL(match.pieces[i].url, location.href).href;
  function setRate(v) { v.defaultPlaybackRate = v.playbackRate = rate; v.muted = muted; }
  function clear(v) { v.pause(); v.removeAttribute('src'); v.load(); }
  function swap() {                                       // the hidden player becomes the shown one (it stays inside the same full-screen box)
    const old = current();
    shown = 1 - shown;
    current().hidden = false;
    old.hidden = true;
    clear(old);
    waitingFor = -1;
  }
  function prepare(i) {                                   // load part i into the hidden player (the browser reads ahead by itself)
    if (!match || i >= match.pieces.length || waitingFor === i) return;
    const v = spare();
    v.preload = 'auto'; setRate(v);
    v.src = urlOf(i);
    v.load();
    waitingFor = i;
  }
  function paint() {                                      // bar, fill and clock
    if (!match) return;
    const t = Math.min(shownTime(), match.duration);
    if (!dragging) seek.value = Math.floor(t);
    $('fill').style.width = (match.duration ? 100 * t / match.duration : 0) + '%';
    $('now').textContent = fmt(t);
  }
  function labelPlay() { $('play').textContent = wantPlay ? '멈춤' : '재생'; }
  function load(i, local, play) {
    index = i;
    switching = true;
    if (play) wantPlay = true;
    labelPlay();
    if (waitingFor === i && spare().readyState >= 1) {    // this part is already loaded in the hidden player: no waiting
      swap();
      const v = current();
      setRate(v);
      if (local > 0) { try { v.currentTime = local; } catch (e) { /* the part is loaded: this does not fail */ } }
      if (play) v.play().catch(() => {});
      switching = false;
      return;
    }
    const video = current();
    const wanted = urlOf(i);
    const go = () => { try { video.currentTime = local; } catch (e) { /* set again on metadata */ } if (play) video.play().catch(() => {}); switching = false; };
    if (video.src === wanted && video.readyState >= 1) { go(); return; }
    video.addEventListener('loadedmetadata', go, { once: true });
    video.src = wanted;
    setRate(video);
    video.load();
  }
  function jump(t, play) {
    if (!match) return;
    t = RT.clamp(t, match.pieces);
    pending = t;
    const where = RT.locate(match.pieces, t);
    load(where.index, where.local, play);
    paint();
  }
  function toggle() {
    const v = current();
    if (!match) return;
    if (v.paused || v.ended) {
      wantPlay = true;
      if (v.ended && index + 1 >= match.pieces.length) jump(0, true); else v.play().catch(() => {});
    } else { wantPlay = false; v.pause(); }
    labelPlay();
  }

  for (const v of players) {
    v.addEventListener('ended', () => {                   // go on with the next part
      if (v !== current() || !match) return;
      if (index + 1 < match.pieces.length) load(index + 1, 0, true);
      else { wantPlay = false; labelPlay(); }
    });
    v.addEventListener('timeupdate', () => {
      if (v !== current() || !match) return;
      if (isFinite(v.duration) && v.duration - v.currentTime <= PRELOAD_AT) prepare(index + 1);
      if (pending !== null && !switching && v.readyState >= 2 && Math.abs(global() - pending) < 3) pending = null;
      paint();
    });
    v.addEventListener('seeked', () => { if (v === current() && pending !== null && Math.abs(global() - pending) < 3) { pending = null; paint(); } });
    v.addEventListener('play', () => { if (v === current()) { wantPlay = true; labelPlay(); } });
    v.addEventListener('pause', () => { if (v === current() && !v.ended && !switching) { wantPlay = false; labelPlay(); } });
    v.addEventListener('click', toggle);
    v.addEventListener('error', () => {
      if (v !== current() || !v.getAttribute('src')) return;
      const hevc = v.canPlayType('video/mp4; codecs="hvc1.1.6.L120.B0"');
      problem(hevc ? '이 영상을 불러오지 못했습니다. 잠시 뒤 다시 눌러 주세요.' : '이 기기에서는 이 영상을 재생할 수 없습니다. 아이폰이나 컴퓨터에서 열어 주세요.');
    });
    v.addEventListener('playing', () => { if (v === current()) { problem(''); switching = false; } });
  }
  seek.addEventListener('input', () => {
    dragging = true;
    $('now').textContent = fmt(+seek.value);
    $('fill').style.width = (match && match.duration ? 100 * +seek.value / match.duration : 0) + '%';
  });
  seek.addEventListener('change', () => { dragging = false; jump(+seek.value, wantPlay); });
  $('play').addEventListener('click', toggle);
  $('back10').addEventListener('click', () => match && jump(RT.step(match.pieces, shownTime(), -10), wantPlay));
  $('fwd10').addEventListener('click', () => match && jump(RT.step(match.pieces, shownTime(), 10), wantPlay));
  $('mute').addEventListener('click', () => {
    muted = !muted;
    players.forEach(setRate);
    $('mute').textContent = muted ? '소리 켜기' : '소리 끄기';
    $('mute').setAttribute('aria-pressed', String(muted));
  });
  const fullElement = () => document.fullscreenElement || document.webkitFullscreenElement;
  $('full').addEventListener('click', () => {
    if (fullElement()) { (document.exitFullscreen || document.webkitExitFullscreen).call(document); return; }
    const ask = stage.requestFullscreen || stage.webkitRequestFullscreen;
    if (ask) { ask.call(stage); return; }
    const v = current();                                   // iPhone: only the video itself can go full screen, with the browser's own controls
    if (v.webkitEnterFullscreen) v.webkitEnterFullscreen();
  });
  const fullChanged = () => { $('full').textContent = fullElement() ? '전체 화면 끝' : '전체 화면'; };
  document.addEventListener('fullscreenchange', fullChanged);
  document.addEventListener('webkitfullscreenchange', fullChanged);
  document.querySelectorAll('[data-rate]').forEach(b => b.addEventListener('click', () => {
    rate = +b.dataset.rate;
    players.forEach(setRate);
    document.querySelectorAll('[data-rate]').forEach(o => o.setAttribute('aria-pressed', String(o === b)));
  }));

  function drawTrack() {                                    // breaks of the recording and the marks on the bar
    const track = $('track');
    track.querySelectorAll('.gap, .tick').forEach(n => n.remove());
    const pct = t => (match.duration ? 100 * t / match.duration : 0) + '%';
    const holes = RT.gaps(match.pieces);
    for (const g of holes) {
      const d = document.createElement('div'); d.className = 'gap'; d.style.left = pct(g.at);
      d.title = '녹화가 끊긴 곳 ' + span(g.seconds); track.append(d);
    }
    for (const m of match.marks) {
      const d = document.createElement('div'); d.className = 'tick ' + m.kind; d.style.left = pct(m.position);
      d.title = (m.clock || m.time) + ' ' + m.label; track.append(d);
    }
    $('gapnote').textContent = holes.length ? '흐린 곳은 녹화가 끊긴 곳' : '';
  }
  function showMarks() {
    const list = $('marks'); list.textContent = '';
    $('marks-note').textContent = match.marks.length ? '' : '표시한 장면이 없습니다';
    for (const m of match.marks) {
      const li = document.createElement('li'), b = document.createElement('button');
      b.type = 'button';
      const t = document.createElement('span'); t.className = 't'; t.textContent = m.clock || m.time;
      const l = document.createElement('span'); l.textContent = m.label + (m.note ? ' · ' + m.note : '');
      b.append(t, l);
      b.addEventListener('click', () => jump(m.seek, true));
      li.append(b); list.append(li);
    }
  }
  async function open(name) {
    problem('');
    players.forEach(clear); waitingFor = -1;
    const r = await fetch('/api/v1/replay/' + encodeURIComponent(name));
    if (!r.ok) { $('info').textContent = '이 경기를 불러오지 못했습니다.'; return; }
    match = await r.json();
    seek.max = Math.floor(match.duration); seek.value = 0;
    $('total').textContent = fmt(match.duration); $('now').textContent = fmt(0);
    $('info').textContent = match.label + ' · ' + span(match.duration);
    pending = null; wantPlay = false; labelPlay();
    drawTrack();
    showMarks();
    load(0, 0, false);
    paint();
  }
  const mark = name => document.querySelectorAll('#test-list button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.name === name)));
  async function start() {
    try {
      const data = await (await fetch('/api/v1/replay')).json();
      const tests = data.tests || [];
      for (const m of data.matches) {
        const o = document.createElement('option'); o.value = m.name;
        o.textContent = m.label + ' · ' + span(m.duration); select.append(o);
      }
      if (tests.length) {                                  // recordings made to try the system: folded away under the real matches
        $('tests').hidden = false;
        $('tests-title').textContent = '시험 녹화 (' + tests.length + ')';
        for (const m of tests) {
          const li = document.createElement('li'), b = document.createElement('button');
          b.type = 'button'; b.dataset.name = m.name; b.setAttribute('aria-pressed', 'false');
          b.textContent = m.label + ' · ' + span(m.duration);
          b.addEventListener('click', () => { select.selectedIndex = -1; mark(m.name); open(m.name); });
          li.append(b); $('test-list').append(li);
        }
      }
      select.addEventListener('change', () => { mark(''); open(select.value); });
      if (!data.matches.length) { $('info').textContent = tests.length ? '녹화한 경기가 없습니다. 시험 녹화만 있습니다.' : '녹화한 경기가 없습니다.'; return; }
      open(select.value);
    } catch (e) { $('info').textContent = '경기 목록을 불러오지 못했습니다.'; }
  }
  start();
})();
