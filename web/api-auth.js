/* Credentials live only in this page's closure; never put them into URLs or storage. */
(() => {
  const nativeFetch = window.fetch.bind(window);
  const el = id => document.getElementById(id);
  const safeOrigin = location.protocol === 'https:' || (location.protocol === 'http:' && ['localhost','127.0.0.1','[::1]'].includes(location.hostname));
  let credential = '';
  let check = 0;
  function controls(restricted) {
    el('proxy-controls-upload').disabled = restricted;
    el('proxy-controls-sequence').disabled = restricted;
    el('sequence-refresh').disabled = restricted;
    el('proxy-controls-note').hidden = !restricted;
    el('upload-warning').hidden = restricted;
  }
  window.fetch = (input, options = {}) => {
    let url;
    try { url = new URL(typeof input === 'string' ? input : input.url, location.href); } catch (_) { return nativeFetch(input, options); }
    if (!credential || !safeOrigin || url.origin !== location.origin || !url.pathname.startsWith('/api/')) return nativeFetch(input, options);
    const headers = new Headers(options.headers || (typeof input === 'string' ? undefined : input.headers));
    headers.set('Authorization', 'Bearer ' + credential);
    return nativeFetch(input, {...options, headers, redirect:'error'});
  };
  el('access-form').addEventListener('submit', async event => {
    event.preventDefault();
    const field=el('access-token'), value=field.value; field.value='';
    if (!safeOrigin) { credential=''; controls(false); el('access-message').textContent='HTTPS 또는 이 컴퓨터의 localhost에서만 토큰을 사용할 수 있습니다.'; return; }
    if (!/^[\x21-\x7e]{32,512}$/.test(value)) { el('access-message').textContent='유효한 접속 토큰을 입력하세요.'; return; }
    credential=value; controls(true); const mine=++check;
    el('access-message').textContent='보안 연결을 확인하고 있습니다.';
    try {
      const response=await window.fetch('/api/v1/proxy-capabilities', {cache:'no-store',signal:AbortSignal.timeout(5000)});
      if (mine !== check) return;
      if (!response.ok) throw new Error('unavailable');
      const capability=await response.json();
      if (mine !== check) return;
      controls(capability.controls_enabled !== true);
      el('access-message').textContent=capability.manual_enabled === true ? '보안 연결을 확인했습니다. 선수 확인을 사용할 수 있습니다.' : '보안 연결을 확인했습니다. 선수 확인은 서버에서 비활성화되어 있습니다.';
    } catch (_) { if (mine === check) el('access-message').textContent='보안 연결을 확인하지 못했습니다. 주소와 토큰을 확인하세요.'; }
  });
  el('access-clear').addEventListener('click', () => { ++check; credential=''; el('access-token').value=''; controls(false); el('access-message').textContent='토큰을 지웠습니다.'; });
})();
