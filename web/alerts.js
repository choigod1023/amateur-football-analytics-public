(() => {
  const el = id => document.getElementById(id);
  const VERDICTS = [['ok', '맞음'], ['wrong', '틀림'], ['useless', '맞지만 쓸모없음']];
  // The order of app/live_feedback.py PRIORITY: the most urgent kind first; kinds that are not coaching alerts come last.
  const PRIORITY = ['box_attack', 'conceded_run', 'run', 'isolated', 'line_drop', 'gap_wide'];
  const URGENCY = {box_attack: '급함', conceded_run: '급함', run: '주의', isolated: '참고', line_drop: '참고', gap_wide: '꺼 둔 알림'};
  const rank = kind => { const i = PRIORITY.indexOf(kind); return i < 0 ? PRIORITY.length : i; };
  // Judging sessions made for the person (`label-*`) are work the user has to do first: they go above every coaching alert, in this order, then by name.
  const LABEL_ORDER = ['label-1123-switch', 'label-1123-role2', 'label-1121-role', 'label-1121-missed', 'label-1121-newbox', 'label-1121-team'];
  const labelRank = s => { const i = LABEL_ORDER.indexOf(s); return i < 0 ? LABEL_ORDER.length : i; };
  const isLabel = s => s.startsWith('label-');
  const labelCompare = (a, b) => labelRank(a) - labelRank(b) || (a < b ? -1 : a > b ? 1 : 0);
  const number = a => parseInt(a.id.slice(a.session.length + 1), 10) || 0;
  // A name a person can read for a session folder: "label-1121-role" -> "확인 요청 11-21 역할", "match-1120" -> "경기 11-20". Only the text shown changes.
  const TOPIC = {role: '역할', role2: '역할 2', missed: '놓친 선수', newbox: '새 상자', team: '팀', switch: '팀 바뀜'};
  const sessionName = s => {
    let m = /^label-(\d{2})(\d{2})-(.+)$/.exec(s);
    if (m) return `확인 요청 ${m[1]}-${m[2]} ${TOPIC[m[3]] || m[3]}`;
    m = /^match-(\d{2})(\d{2})(.*)$/.exec(s);
    if (m) return `경기 ${m[1]}-${m[2]}${m[3] ? ' ' + m[3].replace(/^-/, '') : ''}`;
    return s;
  };
  let data = {alerts: [], stats: [], sessions: []};
  let timer = 0;

  const text = (tag, value, cls) => { const node = document.createElement(tag); node.textContent = value; if (cls) node.className = cls; return node; };
  const clock = seconds => { const s = Math.round(seconds || 0); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`; };

  async function api(path, body) {
    const response = await fetch(path, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body || {})});
    if (!response.ok) throw new Error(`요청이 실패했습니다 (${response.status})`);
    return response.json();
  }

  function renderStats() {
    const rows = data.stats;
    const total = rows.reduce((n, r) => n + r.total, 0), done = rows.reduce((n, r) => n + r.labelled, 0), good = rows.reduce((n, r) => n + r.ok, 0);
    el('chip-total').textContent = `알림 ${total}개`;
    el('chip-done').textContent = `평가 ${done}개`;
    el('chip-useful').textContent = `도움이 된 비율 ${done ? Math.round(100 * good / done) + '%' : '-'}`;
    const body = el('stats').querySelector('tbody');
    body.replaceChildren(...rows.map(r => {
      const tr = document.createElement('tr');
      for (const value of [r.title || r.kind, r.total, r.labelled, r.ok, r.wrong, r.useless, r.useful_share === null ? '-' : Math.round(100 * r.useful_share) + '%']) tr.append(text('td', String(value)));
      return tr;
    }));
    const kind = el('kind'), keep = kind.value;
    kind.replaceChildren(new Option('전체', ''), ...rows.map(r => new Option(r.title || r.kind, r.kind)));
    kind.value = keep;
    const session = el('session'), keepSession = session.value;
    const ordered = [...data.sessions.filter(s => isLabel(s.session)).sort((a, b) => labelCompare(a.session, b.session)), ...data.sessions.filter(s => !isLabel(s.session))];
    session.replaceChildren(new Option('전체', ''), ...ordered.map(s => new Option(`${sessionName(s.session)} (${s.count})`, s.session)));
    session.value = keepSession;
  }

  async function mark(alert, label, note, saved) {
    try {
      await api('/api/v1/alerts/label', {id: alert.id, label, note});
      alert.label = label || null;
      alert.note = note || '';
      saved.textContent = label ? '저장했습니다.' : '평가를 지웠습니다.';
      const card = document.querySelector(`[data-id="${alert.id}"]`);
      if (card) card.querySelectorAll('.verdict button').forEach((b, i) => { const on = VERDICTS[i][0] === alert.label; b.classList.toggle('on', on); b.setAttribute('aria-pressed', on ? 'true' : 'false'); });
      await refresh(true);
    } catch (error) { saved.textContent = error.message; }
  }

  function card(alert) {
    const root = document.createElement('article');
    root.className = 'alert';
    root.dataset.id = alert.id;
    if (alert.video) {
      // a short clip of the scene (5 s before to 3 s after the alert); muted and playsinline so that phones play it in the page
      const media = document.createElement('div'); media.className = 'media';
      const v = document.createElement('video'); v.src = alert.video; v.muted = true; v.loop = true; v.autoplay = true; v.controls = true; v.preload = 'metadata';
      v.setAttribute('playsinline', ''); v.setAttribute('muted', '');
      media.append(v);
      if (alert.image) { const img = document.createElement('img'); img.src = alert.image; img.loading = 'lazy'; img.alt = `${alert.title} 장면의 패스길`; img.addEventListener('click', () => window.open(alert.image, '_blank')); media.append(img); }
      root.append(media);
    } else if (alert.image) { const img = document.createElement('img'); img.src = alert.image; img.loading = 'lazy'; img.addEventListener('click', () => window.open(alert.image, '_blank')); img.alt = `${alert.title} 장면의 패스길`; root.append(img); }
    else root.append(text('div', '이 알림에는 장면 사진이 없습니다.', 'noimg'));
    const side = document.createElement('div');
    const head = text('h3', alert.title || alert.kind);
    if (URGENCY[alert.kind]) head.prepend(text('span', URGENCY[alert.kind], 'urgency u-' + rank(alert.kind)), ' ');
    else if (isLabel(alert.session)) head.prepend(text('span', '먼저', 'urgency u-1'), ' ');
    side.append(head, text('div', `${sessionName(alert.session)} · ${clock(alert.time)}`, 'when'), text('p', alert.text || ''));
    if (alert.line) side.append(text('p', alert.line, 'lane'));
    if (alert.scene.length || alert.space.length || alert.advice.length) {
      const more = document.createElement('details');
      more.append(text('summary', '장면, 공간, 이렇게 움직이세요'));
      for (const [name, rows] of [['장면', alert.scene], ['공간', alert.space], ['이렇게 움직이세요', alert.advice]]) {
        if (!rows.length) continue;
        more.append(text('strong', name));
        const list = document.createElement('ul'); rows.forEach(r => list.append(text('li', r))); more.append(list);
      }
      side.append(more);
    }
    const noteInput = document.createElement('input'); noteInput.maxLength = 200; noteInput.placeholder = '메모(선택)'; noteInput.value = alert.note || ''; noteInput.setAttribute('aria-label', '메모');
    const saved = text('div', '', 'saved');
    const verdict = document.createElement('div'); verdict.className = 'verdict';
    for (const [value, label] of VERDICTS) {
      const b = text('button', label, (alert.label === value ? 'on ' : '') + value); b.type = 'button';
      b.setAttribute('aria-pressed', alert.label === value ? 'true' : 'false');
      b.addEventListener('click', () => mark(alert, alert.label === value ? '' : value, noteInput.value, saved));
      verdict.append(b);
    }
    const note = document.createElement('div'); note.className = 'note'; note.append(noteInput);
    const saveNote = text('button', '메모 저장', 'ghost'); saveNote.type = 'button';
    saveNote.addEventListener('click', () => alert.label ? mark(alert, alert.label, noteInput.value, saved) : saved.textContent = '먼저 맞음, 틀림, 쓸모없음 중 하나를 누릅니다.');
    note.append(saveNote);
    side.append(verdict, note, saved);
    root.append(side);
    return root;
  }

  function renderCards() {
    const filter = el('filter').value, kind = el('kind').value, session = el('session').value;
    const shown = data.alerts.filter(a => (!kind || a.kind === kind) && (!session || a.session === session)
      && (filter === 'all' || (filter === 'open' ? !a.label : a.label === filter)));
    // most urgent kind first; within a kind the server order stays (newest session first, then newest alert)
    // alerts with a clip or a picture first (they can be judged), then the most urgent kind
    const seen = a => (a.video ? 0 : a.image ? 1 : 2);
    const first = a => isLabel(a.session) && !a.label;          // unjudged items of label- sessions on top
    shown.sort((a, b) => first(b) - first(a) || (first(a) ? labelCompare(a.session, b.session) || number(a) - number(b) : seen(a) - seen(b) || rank(a.kind) - rank(b.kind)));
    el('cards').replaceChildren(...shown.map(card));
    el('empty').hidden = shown.length > 0;
  }

  async function refresh(keepCards) {
    clearTimeout(timer);
    try {
      data = await api('/api/v1/alerts/list');
      renderStats();
      if (!keepCards) renderCards();
    } catch (_) { /* keep the last screen */ }
    timer = setTimeout(() => { if (!document.activeElement || document.activeElement.tagName !== 'INPUT') refresh(); else refresh(true); }, 10000);
  }
  for (const id of ['filter', 'kind', 'session']) el(id).addEventListener('change', renderCards);
  refresh();
})();
