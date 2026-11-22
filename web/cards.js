(() => {
  const el = id => document.getElementById(id);
  let rows = [];
  let sortKey = 'number';

  function cell(tag, text) { const node = document.createElement(tag); node.textContent = text; return node; }
  function minutes(seconds) { return `${(seconds / 60).toFixed(1)}분`; }

  function render() {
    const sorted = [...rows].sort((a, b) => sortKey === 'number' ? (a.number ?? 999) - (b.number ?? 999) : (b[sortKey] ?? 0) - (a[sortKey] ?? 0));
    const body = el('sum').querySelector('tbody');
    body.replaceChildren(...sorted.map(r => {
      const tr = document.createElement('tr');
      tr.append(cell('td', `${r.number !== null && r.number !== undefined ? '#' + r.number + ' ' : ''}${r.player}`), cell('td', minutes(r.seconds)), cell('td', `${Math.round(r.distance)} m`), cell('td', `${r.top_kmh} km/h`), cell('td', `${r.sprints}회`));
      return tr;
    }));
    el('cards').replaceChildren(...sorted.map(r => {
      const figure = document.createElement('figure');
      const img = document.createElement('img');
      img.src = `/card-files/${encodeURIComponent(r.file)}`; img.alt = `${r.player} 카드`; img.loading = 'lazy';
      figure.append(img, cell('figcaption', `${r.player}: 추적 ${minutes(r.seconds)}, 달린 거리 ${Math.round(r.distance)} m`));
      return figure;
    }));
  }

  async function load() {
    const response = await fetch('/api/v1/cards/list', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: '{}'});
    const data = await response.json();
    rows = data.cards;
    el('chip-made').textContent = `카드 ${rows.length}장`;
    el('made').textContent = data.made ? `만든 시각: ${new Date(data.made * 1000).toLocaleString('ko-KR')}` : '';
    el('sum').hidden = rows.length === 0;
    el('empty').hidden = rows.length > 0;
    render();
  }

  el('sum').querySelectorAll('th').forEach(th => th.addEventListener('click', () => { sortKey = th.dataset.k; render(); }));
  load().catch(() => { el('empty').hidden = false; el('empty').textContent = '카드를 불러오지 못했습니다.'; });
})();
