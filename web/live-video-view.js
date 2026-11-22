// Shows /live-video.mjpg in every element that has the id live-img. When the picture ends (no stream, stream stopped) it asks again every 3 seconds.
(() => {
  const img = document.getElementById('live-img');
  if (!img) return;
  const empty = document.getElementById('live-empty');
  const state = document.getElementById('live-state');
  let timer = null, startedAt = 0, shown = false;
  const say = (text, ok) => { if (state) { state.textContent = text; state.dataset.ok = ok ? '1' : '0'; } if (empty) empty.hidden = !!ok; img.hidden = !ok; };
  function connect() {
    clearTimeout(timer);
    shown = false; startedAt = Date.now();
    say('연결 중', false);
    img.src = '/live-video.mjpg?t=' + Date.now();
  }
  img.addEventListener('load', () => { shown = true; say('실시간 영상', true); });
  img.addEventListener('error', () => { say('영상 없음 (3초 뒤 다시 시도)', false); timer = setTimeout(connect, 3000); });
  // a motion JPEG fires no further load events after the first picture, so a stalled picture cannot be noticed here; reconnect every 10 minutes to be safe
  setInterval(() => { if (shown) connect(); }, 600000);
  connect();
})();
