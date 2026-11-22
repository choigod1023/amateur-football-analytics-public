/* Live marks contain a single same-frame image, not a replay clip. */
(() => {
  const el = id => document.getElementById(id);
  const validId = id => typeof id === 'string' && /^[a-f0-9]{32}$/.test(id);
  async function refresh() {
    try {
      const res = await fetch('/api/v1/live-bookmarks', {cache:'no-store', signal:AbortSignal.timeout(5000)});
      if (!res.ok) throw new Error('unavailable');
      const data = await res.json();
      const list = el('live-mark-list'); list.replaceChildren();
      for (const item of (Array.isArray(data.items) ? data.items : []).slice(0, 20)) {
        if (!validId(item.id)) continue;
        const li = document.createElement('li'), button = document.createElement('button');
        button.type = 'button'; button.className = 'outline';
        button.textContent = `사용자 표시 · 서버 수신 ${typeof item.timestamp === 'string' ? item.timestamp : '시각 미확인'}`;
        button.addEventListener('click', () => show(item)); li.append(button); list.append(li);
      }
      el('live-mark-empty').hidden = !!list.children.length;
    } catch (_) { el('live-mark-message').textContent = '이 연결에서는 라이브 북마크를 사용할 수 없습니다.'; }
  }
  function show(item) {
    if (!validId(item.id)) return;
    el('live-mark-image').src = `/api/v1/live-bookmarks/${item.id}/frame.jpg`;
    el('live-mark-image').hidden = false;
    const count = Number.isInteger(item.people) && item.people >= 0 ? item.people : null;
    el('live-mark-detail').textContent = count === null ? '해당 시점의 인물 수를 확인할 수 없습니다.' : `해당 분석 프레임에서 ${count}명을 탐지했습니다. 선수·심판 구분은 확인된 경우에만 분석에 사용됩니다.`;
    const feedback = el('live-mark-feedback'); feedback.replaceChildren();
    for (const f of Array.isArray(item.feedback) ? item.feedback.slice(0,5) : []) {
      for (const [name,key] of [['관찰','observation'],['해석','interpretation'],['제안','suggestion'],['한계','limitations']]) {
        if (typeof f?.[key] !== 'string' || !f[key]) continue;
        const p=document.createElement('p'); p.textContent=`${name}: ${f[key]}`; feedback.append(p);
      }
    }
    if (!feedback.children.length) feedback.textContent = '이 프레임에서 검증된 코칭 결과가 없었습니다.';
  }
  el('live-mark-button').addEventListener('click', async () => {
    const button=el('live-mark-button'); button.disabled=true;
    try {
      const response=await fetch('/api/v1/live-bookmarks', {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}', signal:AbortSignal.timeout(5000)});
      if (response.status === 409) throw new Error('최근 라이브 분석 화면이 없거나 저장 한도에 도달했습니다.');
      if (!response.ok) throw new Error('이 연결에서는 라이브 북마크를 사용할 수 없습니다.');
      const item=await response.json(); if (!validId(item.id)) throw new Error('서버 응답을 확인할 수 없습니다.');
      el('live-mark-message').textContent='현재 분석 프레임을 표시했습니다.'; await refresh(); show(item);
    } catch (error) { el('live-mark-message').textContent=error?.message || '북마크를 표시하지 못했습니다.'; }
    finally { button.disabled=false; }
  });
  el('live-mark-refresh').addEventListener('click', refresh);
  refresh();
})();
