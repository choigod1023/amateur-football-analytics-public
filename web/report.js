(() => {
  const el = id => document.getElementById(id);
  const STATES = {uploading: '업로드 중', queued: '대기 중', running: '처리 중', done: '완료', failed: '실패', cancelled: '취소됨'};
  const STEP_LABEL = {detect: '선수 탐지', track: '선수 추적', report: '영상 제작', worker: '작업기'};
  let jobs = [];
  let timer = 0;

  const text = (tag, value, cls) => { const node = document.createElement(tag); node.textContent = value; if (cls) node.className = cls; return node; };
  const token = () => el('token').value;
  const say = (message, kind) => { const node = el('message'); node.textContent = message; node.className = 'message ' + (kind || ''); };

  function parseTime(value) {
    const part = String(value).trim().split(':').map(Number);
    if (!part.length || part.some(n => !Number.isFinite(n) || n < 0)) return null;
    return part.length === 1 ? part[0] : part.length === 2 ? part[0] * 60 + part[1] : part[0] * 3600 + part[1] * 60 + part[2];
  }
  const clock = seconds => { const s = Math.round(seconds); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`; };
  const remaining = seconds => seconds >= 3600 ? `약 ${Math.round(seconds / 360) / 10}시간` : seconds >= 90 ? `약 ${Math.round(seconds / 60)}분` : '1분 안팎';

  async function api(path, body, withToken, options = {}) {
    const headers = {'Content-Type': 'application/json'};
    if (withToken) headers['X-Report-Token'] = token();
    const response = await fetch(path, {method: 'POST', headers, body: JSON.stringify(body || {}), ...options});
    let data = {};
    try { data = await response.json(); } catch (_) { /* no body */ }
    if (!response.ok) throw new Error(response.status === 403 ? '접속 토큰이 없거나 맞지 않습니다.' : (typeof data.detail === 'string' ? data.detail : `요청이 실패했습니다 (${response.status})`));
    return data;
  }

  function renderHealth(health, uploadEnabled) {
    const worker = el('chip-worker');
    const busy = health.counts.running + health.counts.queued > 0;
    worker.textContent = !uploadEnabled ? '업로드 꺼짐(토큰 미설정)' : busy ? (health.worker_alive ? '작업기 동작 중' : '작업기 시작 대기') : '작업기 대기';
    worker.className = 'chip ' + (!uploadEnabled ? 'bad' : 'ok');
    el('chip-queue').textContent = `대기 ${health.counts.queued} · 진행 ${health.counts.running}`;
    el('chip-disk').textContent = `저장공간 ${health.disk_free_gb}GB`;
    el('chip-disk').className = 'chip ' + (health.disk_free_gb < 20 ? 'bad' : '');
  }

  function renderCameras(cameras) {
    const select = el('camera');
    if (select.options.length === cameras.length && cameras.every((c, i) => select.options[i].value === c.id)) return;
    select.replaceChildren(...cameras.map(c => { const o = document.createElement('option'); o.value = c.id; o.textContent = c.label; return o; }));
  }

  function jobCard(job) {
    const card = document.createElement('div');
    card.className = 'job';
    const top = document.createElement('div'); top.className = 'job-top';
    const left = document.createElement('div');
    left.append(text('div', job.title, 'job-title'), text('div', `${job.half_name} · 팀 ${job.team} · ${job.camera} · ${clock(job.range[0])}~${clock(job.range[1])}${job.goals.length ? ` · 득점 ${job.goals.length}개` : ''} · ${job.created}`, 'job-meta'));
    top.append(left, text('span', STATES[job.status.state] || job.status.state, 'badge ' + job.status.state));
    card.append(top);
    const state = job.status.state;
    if (state === 'running' || state === 'queued' || state === 'uploading') {
      const bar = document.createElement('div'); bar.className = 'bar';
      const fill = document.createElement('i'); fill.style.width = (job.status.percent || 0) + '%'; bar.append(fill);
      card.append(bar);
      const step = job.status.step_name || '';
      const eta = job.status.eta_seconds ? ` · 남은 시간 ${remaining(job.status.eta_seconds)}` : '';
      card.append(text('div', `${step}${state === 'running' ? ` · ${job.status.percent || 0}%` : ''}${eta}`, 'job-step'));
    }
    if (job.status.message) card.append(text('div', job.status.message, state === 'failed' ? 'job-message' : 'job-step'));
    const actions = document.createElement('div'); actions.className = 'actions';
    const button = (label, handler, cls) => { const b = text('button', label, cls); b.type = 'button'; b.addEventListener('click', handler); actions.append(b); };
    if (state === 'done') button('열기', () => openDetail(job));
    if (state === 'failed' || state === 'cancelled') button('상세', () => openDetail(job), 'ghost');
    if (state === 'queued' || state === 'running') button('취소', () => act('cancel', job, '이 작업을 취소할까요?'), 'danger');
    if (job.can_retry) button('다시 시도', () => act('retry', job));
    if (state !== 'running' && state !== 'uploading') button('삭제', () => act('delete', job, '리포트와 업로드한 영상을 삭제합니다. 되돌릴 수 없습니다. 계속할까요?'), 'danger');
    card.append(actions);
    return card;
  }

  async function act(name, job, confirmation) {
    if (confirmation && !window.confirm(confirmation)) return;
    try {
      const result = await api('/api/v1/report/' + name, {job: job.id}, true);
      if (!result.done) say('지금은 이 작업을 할 수 없는 상태입니다.', 'bad');
      refresh();
    } catch (error) { say(error.message, 'bad'); }
  }

  async function refresh() {
    clearTimeout(timer);
    try {
      const data = await api('/api/v1/report/list');
      jobs = data.jobs;
      renderHealth(data.health, data.upload_enabled);
      renderCameras(data.cameras);
      el('send').disabled = !data.upload_enabled;
      const list = el('jobs');
      list.replaceChildren(...jobs.map(jobCard));
      el('empty').hidden = jobs.length > 0;
      el('jobs-count').textContent = jobs.length ? `${jobs.length}개` : '';
    } catch (_) { /* keep the last screen */ }
    timer = setTimeout(refresh, jobs.some(j => ['running', 'queued', 'uploading'].includes(j.status.state)) ? 4000 : 15000);
  }

  // ---- detail dialog -------------------------------------------------------------------------------------------------------------
  function renderMarkdown(source) {
    const box = document.createDocumentFragment();
    let list = null;
    for (const raw of source.split('\n')) {
      const line = raw.trimEnd();
      if (!line) { list = null; continue; }
      const inline = (node, value) => value.split(/(\*\*[^*]+\*\*)/).forEach(part => node.append(part.startsWith('**') ? text('strong', part.slice(2, -2)) : document.createTextNode(part)));
      if (line.startsWith('## ') || line.startsWith('# ')) { list = null; box.append(text('h3', line.replace(/^#+\s*/, ''))); }
      else if (line.startsWith('- ')) { if (!list) { list = document.createElement('ul'); box.append(list); } const li = document.createElement('li'); inline(li, line.slice(2)); list.append(li); }
      else { list = null; const p = document.createElement('p'); inline(p, line); box.append(p); }
    }
    return box;
  }

  async function openDetail(job) {
    const dialog = el('detail');
    el('detail-title').textContent = job.title;
    el('detail-meta').textContent = `${job.half_name} · 팀 ${job.team} · ${job.camera} · ${job.created}`;
    const video = el('detail-video');
    const links = el('detail-links'); links.replaceChildren();
    const movie = job.files.includes('review.mp4') ? 'review.mp4' : 'report.mp4';
    const paper = job.files.includes('review.md') ? 'review.md' : 'report.md';
    if (job.files.includes(movie)) { video.hidden = false; video.src = `/report-files/${job.id}/${movie}`; } else { video.hidden = true; video.removeAttribute('src'); }
    for (const [file, label] of [[movie, '영상 내려받기'], [paper, '문서 보기'], ['events.json', '장면 데이터'], ['scenes.json', '장면 데이터']]) {
      if (!job.files.includes(file)) continue;
      const a = text('a', label); a.href = `/report-files/${job.id}/${file}`; a.target = '_blank'; a.rel = 'noopener'; if (file === movie) a.download = ''; links.append(a);
    }
    const body = el('detail-text'); body.replaceChildren();
    if (job.files.includes(paper)) {
      try { body.append(renderMarkdown(await (await fetch(`/report-files/${job.id}/${paper}`)).text())); } catch (_) { body.append(text('p', '문서를 불러오지 못했습니다.')); }
    } else if (job.status.message) body.append(text('p', job.status.message));
    const log = el('detail-log'); log.hidden = false;
    const tabs = el('log-tabs'); tabs.replaceChildren();
    for (const step of ['detect', 'track', 'report', 'worker']) {
      const b = text('button', STEP_LABEL[step], 'ghost'); b.type = 'button';
      b.addEventListener('click', async () => { try { el('log-body').textContent = (await api('/api/v1/report/log', {job: job.id, step}, true)).text || '(로그가 비어 있습니다)'; } catch (error) { el('log-body').textContent = error.message; } });
      tabs.append(b);
    }
    el('log-body').textContent = '접속 토큰을 입력한 뒤 단계를 고르면 로그가 보입니다.';
    dialog.showModal();
  }
  el('detail-close').addEventListener('click', () => { el('detail').close(); el('detail-video').pause(); });
  el('detail').addEventListener('close', () => el('detail-video').pause());

  // ---- upload ----------------------------------------------------------------------------------------------------------------------
  el('new-form').addEventListener('submit', event => {
    event.preventDefault();
    const file = el('file').files[0];
    const start = parseTime(el('start').value), end = parseTime(el('end').value);
    if (!file) return say('영상 파일을 고르세요.', 'bad');
    if (!token()) return say('접속 토큰을 입력하세요.', 'bad');
    if (start === null || end === null || end <= start) return say('분석 시작과 끝을 확인하세요(끝이 시작보다 뒤여야 합니다).', 'bad');
    const goalTimes = el('goals').value.split(/[,\s]+/).filter(Boolean).map(parseTime);
    if (goalTimes.some(g => g === null || g < start || g > end)) return say('득점 시각은 분석 구간 안의 시각이어야 합니다.', 'bad');
    const query = new URLSearchParams({camera: el('camera').value, team: el('team').value, direction: el('direction').value, start, end, half_name: el('half').value,
                                        title: el('title').value, goals: goalTimes.join(','), name: file.name});
    const request = new XMLHttpRequest();
    request.open('POST', '/api/v1/report/upload?' + query.toString());
    request.setRequestHeader('X-Report-Token', token());
    request.setRequestHeader('Content-Type', 'application/octet-stream');
    el('bar').hidden = false; el('bar').value = 0; el('send').disabled = true; say('업로드 중입니다. 창을 닫지 마세요.');
    request.upload.onprogress = e => { if (e.lengthComputable) el('bar').value = Math.round(100 * e.loaded / e.total); };
    request.onload = () => {
      el('send').disabled = false; el('bar').hidden = true;
      if (request.status === 200) { say('업로드가 끝났습니다. 오른쪽 목록에서 진행 상황을 볼 수 있습니다.', 'good'); el('file').value = ''; refresh(); return; }
      let detail = ''; try { detail = JSON.parse(request.responseText).detail; } catch (_) { /* none */ }
      say(request.status === 403 ? '접속 토큰이 맞지 않습니다.' : request.status === 413 ? '파일이 너무 큽니다(최대 4GB).' : `업로드에 실패했습니다 (${request.status}) ${typeof detail === 'string' ? detail : ''}`, 'bad');
    };
    request.onerror = () => { el('send').disabled = false; el('bar').hidden = true; say('연결이 끊겼습니다. 네트워크를 확인하고 다시 시도해 주세요.', 'bad'); };
    request.send(file);
  });
  refresh();
})();
