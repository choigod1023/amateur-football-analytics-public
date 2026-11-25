// Shows /live-video.mjpg in every element that has the id live-img. When the picture ends (no stream, stream stopped) it asks again every 3 seconds.
(() => {
  const img = document.getElementById('live-img');
  if (!img) return;
  const empty = document.getElementById('live-empty');
  const state = document.getElementById('live-state');
  let timer = null, startedAt = 0, shown = false;
  const say = (text, ok) => { if (state) { state.textContent = text; state.dataset.ok = ok ? '1' : '0'; } if (empty) empty.hidden = !!ok; img.hidden = !ok; };
  // A button at the bottom right of the picture: one tap = full screen (the box on most browsers, the video itself on an iPhone). A refusal is ignored.
  try {
    const box = img.parentNode;
    const button = document.createElement('button');
    button.type = 'button'; button.className = 'live-fs'; button.textContent = '전체 화면'; button.setAttribute('aria-label', '전체 화면');
    button.addEventListener('click', () => {
      try {
        if (document.fullscreenElement || document.webkitFullscreenElement) { (document.exitFullscreen || document.webkitExitFullscreen).call(document); return; }
        const video = box.querySelector('video:not([hidden])');
        const enter = box.requestFullscreen || box.webkitRequestFullscreen;
        if (enter) { const done = enter.call(box); if (done && done.catch) done.catch(() => {}); }
        else if (video && video.webkitEnterFullscreen) video.webkitEnterFullscreen();
      } catch (e) { /* not allowed: nothing happens */ }
    });
    box.append(button);
  } catch (e) { /* the button is optional */ }
  const hlsOn = () => !!(window.LiveHls && window.LiveHls.active());   // web/live-hls.js is playing: no picture, no second ffmpeg
  function connect() {
    clearTimeout(timer);
    if (hlsOn()) return;
    shown = false; startedAt = Date.now();
    say('연결 중', false);
    img.src = '/live-video.mjpg?t=' + Date.now();
  }
  img.addEventListener('load', () => { if (hlsOn()) return; shown = true; say('실시간 영상', true); });
  img.addEventListener('error', () => { if (hlsOn()) return; say('영상 없음 (3초 뒤 다시 시도)', false); timer = setTimeout(connect, 3000); });
  // a motion JPEG fires no further load events after the first picture, so a stalled picture cannot be noticed here; reconnect every 10 minutes to be safe
  setInterval(() => { if (shown && !hlsOn()) connect(); }, 600000);
  window.addEventListener('livehls-off', connect);      // HLS stopped working: the picture again
  connect();
})();
