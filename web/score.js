// Score board of the bench screen: shows "우리 N : M 상대", three buttons (우리 골, 상대 골, 방금 것 취소) and the lines "골로 보입니다 · 맞음 / 아님" for guesses that wait for a person.
// Reads GET /api/v1/score once a second and writes with POST /api/v1/score. It is separate from bench.js and bench-extra.js: when it fails, the rest of the page goes on as before.
(() => {
  const el = id => document.getElementById(id);
  const TEAM = { ours: '우리 골', opp: '상대 골', unknown: '누구의 골인지 모름' };
  let state = null, busy = false, lastOk = 0;
  try {
    const note = el('score-note');
    const say = text => { note.textContent = text; };

    function render() {
      if (!state) return;
      el('score-ours').textContent = state.ours;
      el('score-opp').textContent = state.opp;
      const ready = !!state.session && !busy;
      el('score-btn-ours').disabled = !ready;
      el('score-btn-opp').disabled = !ready;
      el('score-btn-undo').disabled = !(ready && state.can_undo);
      const holder = el('score-cand');
      holder.replaceChildren();
      for (const c of state.pending || []) {
        const row = document.createElement('div'); row.className = 'cand';
        const text = document.createElement('span');
        text.textContent = c.team === 'ours' || c.team === 'opp' ? `골로 보입니다 · ${TEAM[c.team]}` : '골로 보입니다 · 어느 팀입니까?';
        row.append(text);
        const add = (label, team) => {
          const b = document.createElement('button'); b.type = 'button'; b.textContent = label; b.disabled = busy;
          b.addEventListener('click', () => send(team ? { kind: 'goal', team, ref: c.id } : { kind: 'dismiss', ref: c.id }));
          row.append(b);
        };
        if (c.team === 'ours' || c.team === 'opp') add('맞음', c.team); else { add('우리 골', 'ours'); add('상대 골', 'opp'); }
        add('아님', null);
        holder.append(row);
      }
      if (!state.session) say('분석이 시작되면 누를 수 있습니다');
      else if (state.can_undo && state.last) say(`마지막: ${TEAM[state.last]}`);
      else say('');
    }

    async function poll() {
      if (busy) return;
      try {
        const r = await fetch('/api/v1/score', { cache: 'no-store' });
        if (r.ok) { state = await r.json(); lastOk = Date.now(); render(); }
      } catch (e) { /* keep the last answer */ }
      if (state && Date.now() - lastOk > 5000) say('연결 확인 중 (마지막 점수)');
    }

    async function send(body) {
      if (busy || !state || !state.session) return;
      busy = true; render();
      try {
        const r = await fetch('/api/v1/score', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ session: state.session, source: 'manual', ...body }) });
        if (r.ok) { state = await r.json(); lastOk = Date.now(); busy = false; render(); return; }
        const err = await r.json().catch(() => ({}));
        busy = false; render();
        say(typeof err.detail === 'string' ? err.detail : '저장하지 못했습니다. 다시 눌러 주세요.');
      } catch (e) { busy = false; render(); say('저장하지 못했습니다. 연결을 확인해 주세요.'); }
    }

    el('score-btn-ours').addEventListener('click', () => send({ kind: 'goal', team: 'ours' }));
    el('score-btn-opp').addEventListener('click', () => send({ kind: 'goal', team: 'opp' }));
    el('score-btn-undo').addEventListener('click', () => send({ kind: 'undo' }));
    poll(); setInterval(poll, 1000);
  } catch (e) { /* the score board is optional: the rest of the page does not depend on it */ }
})();
