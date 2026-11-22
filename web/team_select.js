(() => {
  const $ = (id) => document.getElementById(id);
  let candidates = null, picked = null;

  const post = (path, body) => fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) })
    .then(async (r) => { const data = await r.json().catch(() => ({})); if (!r.ok) throw new Error(data.detail || '요청이 실패했습니다.'); return data; });

  function render(state) {
    candidates = state.candidates;
    const profile = state.profile;
    const current = $('current');
    current.hidden = !profile;
    $('clear').hidden = !profile || !!profile.error;
    if (profile) {
      current.textContent = profile.error ? profile.error
        : `지금 저장된 선택: 우리 팀은 ${profile.own_colour} 옷, 상대 팀은 ${profile.opponent_colour} 옷입니다 (${profile.created.replace('T', ' ')}).`;
    }
    const status = $('status'), box = $('groups');
    box.textContent = '';
    $('confirm').style.display = 'none';
    if (!candidates || !candidates.groups || candidates.groups.length < 2) {
      status.textContent = candidates && candidates.reason ? candidates.reason : '팀 색 사진이 아직 없습니다. 경기가 시작되면 사진을 만든 뒤 이 화면을 다시 열어 주세요.';
      return;
    }
    status.className = 'note' + (candidates.weak || !candidates.ok ? ' warn' : '');
    status.textContent = candidates.ok
      ? (candidates.weak ? candidates.reason : `선수 ${candidates.people_read}명의 옷 색으로 나누었습니다.`) + (candidates.others_people ? ` (심판이나 골키퍼로 보이는 ${candidates.others_people}명은 따로 두었습니다.)` : '')
      : candidates.reason;
    if (!candidates.ok) return;
    candidates.groups.forEach((group, index) => {
      const card = document.createElement('div'); card.className = 'group';
      const title = document.createElement('h2'); title.textContent = `${index === 0 ? '왼쪽' : '오른쪽'}: ${group.colour_text} 옷 (${group.people}명)`;
      const pics = document.createElement('div'); pics.className = 'pics';
      group.urls.forEach((url) => { const img = document.createElement('img'); img.src = url; img.alt = '선수 사진'; pics.append(img); });
      const button = document.createElement('button'); button.textContent = index === 0 ? '왼쪽이 우리 팀입니다' : '오른쪽이 우리 팀입니다';
      button.addEventListener('click', () => choose(index));
      card.append(title, pics, button); box.append(card);
    });
  }

  async function choose(index) {
    try {
      const reply = await post('/api/v1/team-select/choose', { group: index, confirmed: false, created: candidates.created });
      picked = index;
      $('sentence').textContent = reply.sentence;
      $('confirm').style.display = 'block';
    } catch (error) { alert(error.message); }
  }

  $('yes').addEventListener('click', async () => {
    try {
      const reply = await post('/api/v1/team-select/choose', { group: picked, confirmed: true, created: candidates.created });
      $('confirm').style.display = 'none';
      $('status').className = 'note good';
      $('status').textContent = `저장했습니다. ${reply.sentence.replace(' 맞습니까?', '')} 다음 라이브 실행부터 이 선택을 따릅니다.`;
      load(false);
    } catch (error) { alert(error.message); }
  });
  $('no').addEventListener('click', () => { picked = null; $('confirm').style.display = 'none'; });
  $('clear').addEventListener('click', async () => {
    if (!confirm('저장된 팀 색을 지웁니다. 다음 라이브 실행은 예전 방식(어두운 옷이 우리 팀)으로 돌아갑니다. 지울까요?')) return;
    await post('/api/v1/team-select/clear'); load(true);
  });

  function load(redraw) {
    return fetch('/api/v1/team-select').then((r) => r.json()).then((state) => {
      if (redraw) render(state);
      else { $('current').hidden = !state.profile; $('clear').hidden = !state.profile; if (state.profile) $('current').textContent = `지금 저장된 선택: 우리 팀은 ${state.profile.own_colour} 옷, 상대 팀은 ${state.profile.opponent_colour} 옷입니다.`; }
    }).catch(() => { $('status').textContent = '서버에서 불러오지 못했습니다.'; });
  }
  load(true);
})();
