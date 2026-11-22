// The page /halftime?session=NAME[&half=2]: the report of app/halftime_report.py in a coach's words, drawn with textContent and SVG only.
(() => {
  const el = id => document.getElementById(id);
  const params = new URLSearchParams(location.search);
  const session = params.get('session') || '', half = params.get('half') === '2' ? 2 : 1;
  const NS = 'http://www.w3.org/2000/svg';
  const fill = (id, items, empty) => {
    const list = el(id); list.replaceChildren();
    for (const value of items.length ? items : [empty]) { const li = document.createElement('li'); li.textContent = value; list.append(li); }
  };
  const node = (tag, attrs) => { const e = document.createElementNS(NS, tag); for (const k in attrs) e.setAttribute(k, attrs[k]); return e; };

  function pitch(picture) {                       // 89 m x 62 m, 8 pixels per metre; ours attacks to the right
    const X = u => (u + 44.5) * 8, Y = v => (v + 31) * 8;
    const svg = node('svg', { viewBox: '0 0 712 496', role: 'img', 'aria-label': picture.name + ' 선수들이 주로 선 자리' });
    svg.append(node('rect', { x: 0, y: 0, width: 712, height: 496, rx: 10, fill: '#1d4d2b' }));
    const line = { fill: 'none', stroke: '#9fd0a8', 'stroke-width': 2 };
    svg.append(node('rect', { x: 6, y: 6, width: 700, height: 484, ...line }));
    svg.append(node('line', { x1: 356, y1: 6, x2: 356, y2: 490, ...line }));
    svg.append(node('circle', { cx: 356, cy: 248, r: 73, ...line }));
    for (const side of [0, 1]) {
      const x0 = side ? 706 - 132 : 6, x1 = side ? 706 : 138;
      svg.append(node('rect', { x: Math.min(x0, x1), y: 248 - 161, width: 132, height: 322, ...line }));
    }
    for (const p of picture.theirs) svg.append(node('circle', { cx: X(p[0]), cy: Y(p[1]), r: 11, fill: '#12301b', stroke: '#ff8a6b', 'stroke-width': 4, opacity: 0.95 }));
    for (const p of picture.ours) svg.append(node('circle', { cx: X(p[0]), cy: Y(p[1]), r: 11, fill: '#4aa3ff', stroke: '#e8f3ff', 'stroke-width': 2 }));
    const arrow = node('text', { x: 356, y: 480, 'text-anchor': 'middle', fill: '#cfe8d4', 'font-size': 16 });
    arrow.textContent = '우리 팀 공격 방향 →';
    svg.append(arrow);
    return svg;
  }

  async function load() {
    const response = await fetch(`/api/v1/halftime/report?session=${encodeURIComponent(session)}&half=${half}`, { cache: 'no-store' });
    if (!response.ok) { el('summary').textContent = '아직 보고서가 없습니다. 전반이 끝나면 만들어집니다.'; return; }
    const r = await response.json();
    el('title').textContent = half === 2 ? '후반 중간 보고서' : '하프타임 보고서';
    el('meta').textContent = `${r.source_text}. 만든 시각 ${r.generated_text}. 영상 시각 ${r.end_text}까지.`;
    el('summary').replaceChildren(...r.summary.map(text => { const p = document.createElement('p'); p.textContent = text; return p; }));
    el('missing').hidden = !r.missing.ranges.length;
    el('missing-text').textContent = `영상이 끊겨 선수 위치와 알림이 없는 시간이 ${r.missing.share_word} 있습니다 (합계 ${r.missing.total_text}). 이 시간은 요약에 들어 있지 않습니다.`;
    fill('missing-list', r.missing.ranges.map(x => `${x.from_text} ~ ${x.to_text} (${x.length_text})`), '');
    const pictures = el('pictures'); pictures.replaceChildren();
    for (const picture of r.pictures) {
      const figure = document.createElement('figure'), caption = document.createElement('figcaption');
      caption.textContent = picture.name; figure.append(pitch(picture), caption); pictures.append(figure);
    }
    if (!r.pictures.length) pictures.textContent = '선수들이 충분히 보인 시간이 짧아 그림을 그리지 못했습니다.';
    fill('problems', r.problems, '');
    fill('opponent', r.opponent || [], '');
    el('lineup').hidden = !r.lineup;
    if (r.lineup) {
      el('formation').textContent = r.lineup.formation ? `계획한 모양 ${r.lineup.formation} (경기 전에 사람이 입력한 내용입니다)` : '경기 전에 사람이 입력한 내용입니다';
      const cards = el('cards'); cards.replaceChildren();
      for (const p of r.lineup.players) {
        const card = document.createElement('div'); card.className = 'card';
        const role = document.createElement('b'); role.textContent = p.role;
        const name = document.createElement('span'); name.textContent = p.name;
        card.append(role, name);
        if (p.note) { const note = document.createElement('small'); note.textContent = p.note; card.append(note); }
        cards.append(card);
      }
    }
    fill('box', r.box_attacks.map(x => `${x.time_text} ${x.text}`), '해당 장면이 없었습니다');
    fill('conceded', r.conceded.map(x => `${x.time_text} ${x.text}`), '해당 장면이 없었습니다');
    fill('alerts', r.alerts.map(x => `${x.title} ${x.count}번`), '나온 알림이 없습니다');
    fill('second', r.second_half, '');
  }
  load();
  setInterval(load, 10000);
})();
