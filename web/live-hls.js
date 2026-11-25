// HLS video for /live, /bench and /setup. Loaded BEFORE live-video-view.js / setup.js.
// Order: the browser plays HLS itself (canPlayType: Safari, iOS) -> else hls.js (/vendor/hls.min.js, loaded only then, from this server) -> else the picture.
// ?hls=js in the address forces the hls.js way (test only, nothing is shown on the screen).
// The old picture (/live-video.mjpg in <img>) keeps running until the video has really played; then the <img> is emptied (so ffmpeg is not run twice)
// and the <video> is shown. The picture comes back when HLS is not playable, fails (fatal hls.js error, video error), or stalls (currentTime not moving for 5 s). HLS is tried again every 10 s.
(() => {
  const img = document.getElementById('live-img') || document.getElementById('video');
  const URL_M3U8 = '/live-hls/index.m3u8';
  const STALL_MS = 5000, RETRY_MS = 10000, FIRST_RETRY_MS = 3000, PROBE_MS = 4000;   // the first playlist after a quiet minute can take ~5 s (server answers 502 at 2 s): ask again after 3 s once
  const URL_HLSJS = '/vendor/hls.min.js';
  // hls.js settings: close to the live edge, catch up when behind, never wait for more than the pieces the server really has.
  //  liveSyncDurationCount 2 (default 3): start and stay 2 pieces behind the newest one (the server lists 5, see app/srt_path_ingest.py)
  //  liveMaxLatencyDurationCount 5: more than 5 pieces behind -> hls.js jumps back to the sync point
  //  maxLiveSyncPlaybackRate 1.1: when a little behind, play 10 % faster until the sync point (default 1 = never)
  //  lowLatencyMode false: the server makes plain fmp4 pieces, not LL-HLS parts
  //  enableWorker false: fmp4 needs no re-packaging, and the page's CSP does not allow blob: workers
  //  buffers kept short (10 s ahead, 10 s back) so a phone does not grow memory over a 90 minute match
  const HLSJS_CONFIG = { lowLatencyMode: false, liveSyncDurationCount: 2, liveMaxLatencyDurationCount: 5, maxLiveSyncPlaybackRate: 1.1,
                         maxBufferLength: 10, maxMaxBufferLength: 20, backBufferLength: 10, enableWorker: false };
  const forceJs = /[?&]hls=js(&|$)/.test(location.search);
  let tries = 0, video = null, active = false, checking = null, retryTimer = null, lastTime = 0, lastMoved = 0, supported = false, hls = null, mode = '';

  // read by the picture code: when true it must not (re)start /live-video.mjpg
  window.LiveHls = { active: () => active };
  if (!img) return;

  const ui = {
    state: document.getElementById('live-state'),
    empty: document.getElementById('live-empty'),
    none: document.getElementById('video-none'),
  };
  const emit = (name) => window.dispatchEvent(new Event(name));

  function makeVideo() {
    const v = document.createElement('video');
    v.muted = true; v.defaultMuted = true; v.autoplay = true; v.playsInline = true;
    v.setAttribute('muted', ''); v.setAttribute('autoplay', ''); v.setAttribute('playsinline', ''); v.setAttribute('webkit-playsinline', '');
    v.disablePictureInPicture = true;
    v.controls = false;
    v.hidden = true;
    v.style.cssText = 'width:100%;height:100%;object-fit:contain;display:block;background:#000';
    img.parentNode.insertBefore(v, img.nextSibling);
    return v;
  }

  function release() {
    if (hls) { try { hls.destroy(); } catch (e) { /* already gone */ } hls = null; window.LiveHls.hls = null; }
    if (!video) return;
    video.pause();
    video.removeAttribute('src');
    video.load();
    video.hidden = true;
  }

  // HLS is playing: show the video, empty the picture
  function takeOver() {
    active = true;
    video.hidden = false;
    img.removeAttribute('src');
    img.hidden = true;
    if (ui.empty) ui.empty.hidden = true;
    if (ui.none) ui.none.hidden = true;
    if (ui.state) { ui.state.textContent = '실시간 영상 (HLS)'; ui.state.dataset.ok = '1'; }
  }

  // HLS does not work (now): the picture code starts again, and HLS is tried again later
  function giveUp(why) {
    const was = active;
    clearInterval(checking); checking = null;
    active = false;
    release();
    window.LiveHls.lastFailure = why;
    if (was) { img.hidden = false; emit('livehls-off'); }
    clearTimeout(retryTimer);
    retryTimer = setTimeout(attempt, tries++ === 0 ? FIRST_RETRY_MS : RETRY_MS);
  }

  async function attempt() {
    clearTimeout(retryTimer);
    if (active || checking) return;
    const stop = new AbortController();
    const abortTimer = setTimeout(() => stop.abort(), PROBE_MS);
    let ok = false;
    try { ok = (await fetch(URL_M3U8, { cache: 'no-store', signal: stop.signal })).status === 200; } catch (e) { ok = false; }
    clearTimeout(abortTimer);
    if (!ok) { giveUp('playlist'); return; }
    const started = performance.now();
    if (mode === 'js') {
      const Hls = window.Hls;
      hls = new Hls(HLSJS_CONFIG);
      window.LiveHls.hls = hls;
      hls.on(Hls.Events.ERROR, (event, data) => { if (data && data.fatal) giveUp('hls.js ' + (data.details || data.type)); });
      hls.loadSource(URL_M3U8);
      hls.attachMedia(video);
    } else {
      video.src = URL_M3U8;
    }
    lastTime = 0; lastMoved = started;
    // hls.js seeks to the live position before the first picture, so 'played' means: 0.5 s past the first position it showed (native: past 0, as before)
    let base = mode === 'js' ? null : 0;
    // play() may stay pending until data arrives; a refusal by the phone (autoplay blocked) is a failure, anything else is judged by the clock below
    const playing = video.play();
    if (playing && playing.catch) playing.catch((e) => { window.LiveHls.lastPlayError = e && e.name; if (e && e.name === 'NotAllowedError') giveUp('play'); });
    checking = setInterval(() => {
      const now = performance.now();
      if (document.hidden) { lastMoved = now; return; }      // a hidden page may be paused by the phone: not a failure
      if (video.error) { giveUp('error'); return; }
      if (base === null && video.readyState >= 2) base = video.currentTime;
      if (video.currentTime > lastTime + 0.05) {
        lastTime = video.currentTime; lastMoved = now;
        if (!active && base !== null && lastTime - base > 0.5) { clearInterval(checking); checking = setInterval(watch, 1000); takeOver(); }
      } else if (now - lastMoved > STALL_MS) { giveUp(active ? 'stall' : 'no start'); }
    }, 500);
  }

  // after take over: the same test, slower
  function watch() {
    const now = performance.now();
    if (document.hidden) { lastMoved = now; return; }
    if (video.error) { giveUp('error'); return; }
    if (video.currentTime > lastTime + 0.05) { lastTime = video.currentTime; lastMoved = now; }
    else if (now - lastMoved > STALL_MS) giveUp('stall');
  }

  document.addEventListener('visibilitychange', () => {
    if (!document.hidden && video && active && video.paused) video.play().catch(() => giveUp('play'));
  });

  function start() {
    window.LiveHls.supported = supported = true;
    window.LiveHls.mode = mode;
    video = makeVideo();
    video.addEventListener('error', () => { if (active || checking) giveUp('error'); });
    attempt();
  }

  const native = !!document.createElement('video').canPlayType('application/vnd.apple.mpegurl');
  window.LiveHls.supported = false;
  if (native && !forceJs) { mode = 'native'; start(); return; }
  // hls.js: the file is loaded only now, only from this server; without it (or without MediaSource) the picture stays and nothing is tried again
  const script = document.createElement('script');
  script.src = URL_HLSJS;
  script.onload = () => { if (window.Hls && window.Hls.isSupported()) { mode = 'js'; start(); } else window.LiveHls.lastFailure = 'no MediaSource'; };
  script.onerror = () => { window.LiveHls.lastFailure = 'hls.js file'; };
  document.head.appendChild(script);
})();
