// The page /watch: state of the live run and the log of stops. The red band and the sound come from watch-banner.js; this file only draws what it announces.
(() => {
  const el = id => document.getElementById(id);
  window.addEventListener('watch-state', event => {
    const { state, halftime } = event.detail;
    const level = state.state === 'down' ? 'down' : state.state === 'ok' ? 'ok' : 'unknown';
    el('state').dataset.level = level;
    el('headline').textContent = state.headline;
    el('detail').textContent = state.state === 'down' ? `${state.since_text}부터 ${state.duration_text} 동안 멈춤. ${state.detail}` : state.detail;
    el('meta').textContent = [state.session ? `실행 이름 ${state.session}` : '', state.last_change_age_s == null ? '' : `알림 파일이 ${Math.round(state.last_change_age_s)}초 전에 바뀌었습니다`].filter(Boolean).join(' · ');
    const body = el('log');
    body.replaceChildren();
    for (const o of state.outages || []) {
      const row = document.createElement('tr');
      const cells = [o.since_text, o.causes.length > 1 ? o.causes.join(' → ') : o.cause_text, o.duration_text + (o.open ? ' (계속 중)' : ''), o.open ? '아직 복구되지 않음' : `${o.ended_text} (${o.end_reason})`];
      cells.forEach((value, i) => { const td = document.createElement('td'); td.textContent = value; if (o.open && i === 3) td.className = 'open'; row.append(td); });
      body.append(row);
    }
    if (!body.children.length) { const row = document.createElement('tr'), td = document.createElement('td'); td.colSpan = 4; td.textContent = '아직 기록이 없습니다'; row.append(td); body.append(row); }
    const half = el('half');
    half.replaceChildren();
    if (halftime && halftime.status === 'ready') {
      half.append(`준비되었습니다 (${halftime.end_text || ''}까지). `);
      const link = document.createElement('a'); link.href = halftime.link; link.textContent = '보고서 열기'; half.append(link);
    } else half.textContent = (halftime && halftime.text) || '아직 만들지 않았습니다.';
  });
})();
