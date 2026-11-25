// Bottom tab bar: one tap between pages on a phone.
// Match-day pages (bench, tag, live, watch, half-time, team colour, start) get the match-day tabs;
// after-match pages (alerts, shots, report, train and the other review pages) get the after-match tabs. Both end with "전체" (/start).
// It only adds links. When it fails, the page works as before.
(() => {
  try {
    if (document.getElementById('site-nav')) return;
    const LIVE = [['/setup', '준비'], ['/bench', '벤치'], ['/tag', '표시'], ['/live', '영상'], ['/watch', '상태'], ['/start', '전체']];
    const AFTER = [['/alerts', '알림'], ['/shots', '슛'], ['/report', '보고서'], ['/train', '학습'], ['/start', '전체']];
    const AFTER_PAGES = ['/alerts', '/shots', '/report', '/train', '/train/reappearance', '/review-differences',
      '/cards', '/players', '/events', '/ball', '/dashboard', '/replay'];
    const TABS = AFTER_PAGES.includes(location.pathname) ? AFTER : LIVE;
    const style = document.createElement('style');
    style.textContent = `
      #site-nav { position: fixed; left: 0; right: 0; bottom: 0; z-index: 45; display: grid; grid-template-columns: repeat(${TABS.length}, minmax(0, 1fr));
        background: var(--c-bg, #0b1310); border-top: 1px solid var(--c-line, #24392c); padding-bottom: env(safe-area-inset-bottom, 0px); font-family: var(--font, system-ui, "Noto Sans KR", "Malgun Gothic", sans-serif); }
      #site-nav a { display: flex; align-items: center; justify-content: center; min-height: 52px; color: var(--c-mute, #93a89a); text-decoration: none; font-size: 1rem; font-weight: 700; }
      #site-nav a[aria-current="page"] { color: var(--c-text, #eef3ee); font-weight: 900; box-shadow: inset 0 3px 0 var(--c-lamp, #ffcd28); background: var(--c-card, #122019); }
      #site-nav a:focus-visible { outline: 2px solid var(--c-lamp, #ffcd28); outline-offset: -2px; }
      body.has-nav { padding-bottom: calc(64px + env(safe-area-inset-bottom, 0px)) !important; }
      body.has-nav .wb-halfbar { bottom: calc(52px + env(safe-area-inset-bottom, 0px)); }
      body.has-nav:has(.wb-halfbar) { padding-bottom: calc(128px + env(safe-area-inset-bottom, 0px)) !important; }`;
    document.head.append(style);
    const nav = document.createElement('nav');
    nav.id = 'site-nav'; nav.setAttribute('aria-label', '화면 이동');
    const here = location.pathname === '/' ? '/start' : location.pathname;
    for (const [href, label] of TABS) {
      const a = document.createElement('a'); a.href = href; a.textContent = label;
      if (here === href || (href === '/train' && here === '/train/reappearance')) a.setAttribute('aria-current', 'page');
      nav.append(a);
    }
    document.body.append(nav);
    document.body.classList.add('has-nav');
  } catch (e) { /* optional */ }
})();
