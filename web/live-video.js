/* Optional loopback-only WebRTC preview. The original JPEG path is fallback. */
(() => {
  const video = document.getElementById('video-player');
  const toggle = document.getElementById('video-mode-toggle');
  if (!video || location.protocol !== 'http:' || location.hostname !== '127.0.0.1' || !window.RTCPeerConnection) return;
  const endpoint = 'http://127.0.0.1:18889/player/whep';
  let peer = null, timer = null, stalledTimer = null, session = null, generation = 0, preferVideo = true;
  const status = text => { document.getElementById('video-state').textContent = text; };
  function close() {
    ++generation;
    clearTimeout(stalledTimer); stalledTimer = null;
    window.localVideoActive = false;
    video.hidden = true; video.srcObject = null;
    if (toggle) toggle.hidden = true;
    if (peer) { peer.onconnectionstatechange = null; peer.close(); peer = null; }
    if (session) { fetch(session, {method:'DELETE', cache:'no-store', redirect:'error'}).catch(() => {}); session = null; }
  }
  function retry() { close(); clearTimeout(timer); timer = setTimeout(connect, 5000); }
  async function connect() {
    close(); const current = generation;
    try {
      peer = new RTCPeerConnection({iceServers: []});
      const connection = peer;
      connection.addTransceiver('video', {direction:'recvonly'});
      connection.ontrack = event => {
        if (current !== generation || !event.streams[0]) return;
        video.srcObject = event.streams[0];
        if (toggle) { toggle.hidden = false; toggle.textContent = preferVideo ? '탐지 상자 미리보기' : '연속 동영상 보기'; }
        if (preferVideo) video.play().catch(retry);
      };
      connection.onconnectionstatechange = () => {
        if (current === generation && ['failed','closed','disconnected'].includes(connection.connectionState)) retry();
      };
      video.onplaying = () => {
        if (current !== generation || !preferVideo) return;
        clearTimeout(stalledTimer); stalledTimer = null;
        window.localVideoActive = true; video.hidden = false;
        if (toggle) { toggle.hidden = false; toggle.textContent = '탐지 상자 미리보기'; }
        document.getElementById('frame-preview').hidden = true;
        document.querySelector('.placeholder').hidden = true;
        status('실시간 동영상');
      };
      video.onwaiting = () => {
        if (current !== generation || !preferVideo || !window.localVideoActive) return;
        clearTimeout(stalledTimer);
        stalledTimer = setTimeout(() => { if (current === generation && preferVideo) retry(); }, 4000);
      };
      await connection.setLocalDescription(await connection.createOffer());
      if (connection.iceGatheringState !== 'complete') await new Promise((resolve, reject) => {
        const timeout = setTimeout(() => reject(new Error('ICE timeout')), 3000);
        connection.addEventListener('icegatheringstatechange', () => {
          if (connection.iceGatheringState === 'complete') { clearTimeout(timeout); resolve(); }
        });
      });
      const response = await fetch(endpoint, {method:'POST', headers:{'Content-Type':'application/sdp'}, body:connection.localDescription.sdp, cache:'no-store', redirect:'error', signal:AbortSignal.timeout(5000)});
      if (!response.ok || current !== generation) throw new Error('WHEP unavailable');
      const resource = response.headers.get('Location');
      if (resource) {
        const url = new URL(resource, endpoint);
        if (url.origin === 'http://127.0.0.1:18889' && url.pathname.startsWith('/player/whep/')) session = url.href;
      }
      await connection.setRemoteDescription({type:'answer', sdp:await response.text()});
      // A signalling response alone does not prove that frames are flowing.
      setTimeout(() => { if (current === generation && preferVideo && !window.localVideoActive) retry(); }, 8000);
    } catch (_) { if (current === generation) retry(); }
  }
  if (toggle) toggle.addEventListener('click', () => {
    preferVideo = !preferVideo;
    if (!preferVideo) {
      window.localVideoActive = false; video.hidden = true; video.pause();
      toggle.textContent = '연속 동영상 보기'; status('탐지 미리보기');
    } else {
      toggle.textContent = '탐지 상자 미리보기';
      video.play().catch(retry);
    }
  });
  window.addEventListener('pagehide', () => { clearTimeout(timer); close(); });
  connect();
})();
