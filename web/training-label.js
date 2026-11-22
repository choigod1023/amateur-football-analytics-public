/* Human labels remain local and never become predictions automatically. */
(() => {
  const el=id=>document.getElementById(id);
  let snapshot=null, selected=null, queue=[], reviewed=new Set(), suggestions={};
  const message=text=>{el('label-message').textContent=text;};
  const storageKey=()=>`training-label-reviewed-${snapshot.token}`;
  function remember() { try {sessionStorage.setItem(storageKey(),JSON.stringify([...reviewed]));} catch (_) {} }
  // What the reviewer answered in this browser tab, so saved cards can show it (the server only reports "saved").
  let answers={};
  const answersKey=()=>`training-label-answers-${snapshot.token}`;
  function recordAnswer(id,role,team) {
    answers[id]={role,team};
    try {sessionStorage.setItem(answersKey(),JSON.stringify(answers));} catch (_) {}
    refreshScenesSoon();
  }
  const ROLE_NAMES={player:'선수',goalkeeper:'골키퍼',referee:'심판',spectator:'관중',shadow:'그림자',duplicate:'중복',unknown:'불명',skip:'건너뜀'};
  const answerText=a=>!a?'완료':a.role==='skip'?'건너뜀':`${ROLE_NAMES[a.role]||a.role}${a.team==='team_a'?' · 팀 A':a.team==='team_b'?' · 팀 B':''}`;
  // Mark the recommended <option> so the suggestion is visible inside the dropdown too.
  function markRecommended(select,value) {
    for(const option of (select&&select.options)||[]) {
      if(option._base===undefined) option._base=option.textContent;
      option.textContent=option._base+(value&&option.value===value?' · 추천':'');
    }
  }
  const hooks=()=>globalThis.__reviewHooks||{};
  // A drawn pitch region (when present) decides who is outside play; otherwise use the stored hint.
  const spectatorHint=p=>{const h=hooks(),inside=h.insidePitch?h.insidePitch(p):null;return inside==null?p.role_hint_unverified==='spectator':!inside;};
  // Upper-torso colour share (same rule as the offline candidate hints): a hint, never a saved answer.
  let teamPrefilled=false;
  el('label-team').addEventListener('change',()=>{teamPrefilled=false;});
  el('label-role').addEventListener('change',()=>{
    if(teamPrefilled&&['referee','unknown','spectator','shadow','duplicate'].includes(el('label-role').value)) el('label-team').value='unknown';
  });
  const profiles=new Map();
  function profile(p) {
    if(profiles.has(p.id)) return profiles.get(p.id);
    let result=null;
    try {
      const image=el('label-image');
      if(image.naturalWidth&&image.naturalHeight) {
        const w=image.naturalWidth,h=image.naturalHeight,[x1,y1,x2,y2]=p.bbox;
        const bx=x1*w,by=y1*h,bw=(x2-x1)*w,bh=(y2-y1)*h;
        const sx=Math.max(0,Math.floor(bx+.2*bw)),ex=Math.min(w,Math.ceil(bx+.8*bw)),sy=Math.max(0,Math.floor(by+.18*bh)),ey=Math.min(h,Math.ceil(by+.55*bh));
        const cw=ex-sx,ch=ey-sy;
        if(cw>0&&ch>0) {
          const canvas=document.createElement('canvas');canvas.width=cw;canvas.height=ch;
          const ctx=canvas.getContext('2d',{willReadFrequently:true});
          if(ctx&&ctx.getImageData) {
            ctx.drawImage(image,sx,sy,cw,ch,0,0,cw,ch);
            const d=ctx.getImageData(0,0,cw,ch).data;let neon=0,dark=0,white=0,pale=0,n=0;
            for(let i=0;i<d.length;i+=4) {
              const r=d[i],g=d[i+1],b=d[i+2],mx=Math.max(r,g,b),mn=Math.min(r,g,b),s=mx?255*(mx-mn)/mx:0;
              let hue=0;
              if(mx!==mn) {const dl=mx-mn;hue=mx===r?60*(((g-b)/dl)%6):mx===g?60*((b-r)/dl+2):60*((r-g)/dl+4);if(hue<0)hue+=360;}
              hue/=2;n++;
              if(hue>=22&&hue<=44&&s>90&&mx>110)neon++;
              if(mx<70)dark++;
              if(s<40&&mx>150)white++;
              if(s<60&&mx>130)pale++;
            }
            if(n>=6) result={neon:neon/n,dark:dark/n,white:white/n,pale:pale/n,n};
          }
        }
      }
    } catch (_) {result=null;}
    profiles.set(p.id,result);return result;
  }
  // Tiers (thresholds were read off one scene the reviewer labelled, so they are unverified elsewhere):
  //  spectator, team_a (neon bib), referee (very dark, e.g. the long coat; at most one per scene),
  //  pale (inside the pitch, light/washed-out clothes: may be a bib in glare, team unclear),
  //  team_b (inside the pitch, no neon, not pale or very dark: assumed other team), todo (no hint).
  function baseTier(p) {
    if(spectatorHint(p)) return 'spectator';
    const prof=profile(p), h=hooks();
    if(prof&&prof.neon>=.14) return 'team_a';
    if(!prof&&p.suggested_color_group===0) return 'team_a';
    if(!prof||!(h.insidePitch&&h.insidePitch(p)===true)) return 'todo';
    if(prof.dark>=.45) return 'referee_raw';
    return prof.pale>=.4?'pale':'team_b';
  }
  let refereeCache=null;
  function refereeTop() {
    if(refereeCache!==null) return refereeCache;
    let best=null,bestDark=-1;
    for(const q of queue) {
      if(q.annotation_origin==='human_drawn'||baseTier(q)!=='referee_raw') continue;
      const d=profile(q).dark;
      if(d>bestDark){bestDark=d;best=q.id;}
    }
    return refereeCache=best||'';
  }
  function tierOf(p) {
    const tier=baseTier(p);
    return tier==='referee_raw'?(refereeTop()===p.id?'referee':'todo'):tier;
  }
  function teamHint(p) {
    const tier=tierOf(p);
    return tier==='team_a'||tier==='team_b'?tier:null;
  }
  function shirtHint(p,team) {
    if(team==='team_a') return {color:'yellow',detail:'형광 노랑 조끼'};
    if(team==='team_b') return {color:'other',detail:'검정·어두운 계열(추정)'};
    return {color:'unknown',detail:''};
  }
  const teamName=t=>t==='team_a'?'팀 A':'팀 B';
  const bulkTargets=kind=>queue.filter(p=>!reviewed.has(p.id)&&p.annotation_origin!=='human_drawn'&&
    (kind==='spectator'?spectatorHint(p):teamHint(p)===kind));
  function updateBulk() {
    const spectators=bulkTargets('spectator').length, teamA=bulkTargets('team_a').length, teamB=bulkTargets('team_b').length;
    el('bulk-spectators').textContent=`관중 후보 ${spectators}명 한 번에 저장`;
    el('bulk-team-a').textContent=`형광 조끼 후보 ${teamA}명을 팀 A 선수로 한 번에 저장`;
    el('bulk-team-b').textContent=teamB?`경기장 안 나머지 후보 ${teamB}명을 팀 B 선수로 한 번에 저장`:'팀 B 후보 없음 (경기장 영역을 먼저 그려 주세요)';
    el('bulk-spectators').disabled=!snapshot||spectators===0;
    el('bulk-team-a').disabled=!snapshot||teamA===0;
    el('bulk-team-b').disabled=!snapshot||teamB===0;
  }
  function bulkAnswer(kind,p) {
    if(kind==='spectator') return {role:'spectator',team_group:'unknown',shirt_color:'unknown',shirt_detail:'일괄승인:관중후보'};
    if(kind==='team_a') return {role:'player',team_group:'team_a',shirt_color:'yellow',shirt_detail:'일괄승인:형광조끼후보'};
    const sh=shirtHint(p,'team_b');
    return {role:'player',team_group:'team_b',shirt_color:sh.color,shirt_detail:`일괄승인:팀B후보${sh.detail?' '+sh.detail:''}`};
  }
  async function bulkSave(kind) {
    if(!snapshot)return;
    const targets=bulkTargets(kind);
    if(!targets.length){message('일괄 저장할 후보가 없습니다.');return;}
    const what=kind==='spectator'?`관중 후보 ${targets.length}명을 모두 관중으로`:kind==='team_a'?`형광 조끼 후보 ${targets.length}명을 모두 이 경기 팀 A의 필드 선수로`:`경기장 안의 형광 아닌 후보 ${targets.length}명을 모두 이 경기 팀 B의 필드 선수로 (심판·골키퍼·교체 선수도 섞일 수 있음)`;
    if(!confirm(`${what} 저장합니다.\n자동으로 고른 후보이므로 틀린 사람이 있으면 목록에서 직접 다시 저장해 고칠 수 있습니다. 계속할까요?`))return;
    for(const id of ['bulk-spectators','bulk-team-a','bulk-team-b']) el(id).disabled=true;
    let done=0,failed=false;
    for(const p of targets) {
      try {
        const r=await fetch('/api/v1/training-labels',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:snapshot.token,track_id:p.id,...bulkAnswer(kind,p),only_if_new:true})});
        if(r.ok){const a=bulkAnswer(kind,p);reviewed.add(p.id);recordAnswer(p.id,a.role,a.team_group);done++;continue;}
        const detail=r.status===409?JSON.stringify(await r.json().catch(()=>({}))):'';
        if(detail.includes('이미 저장')){reviewed.add(p.id);continue;}
        failed=true;break;
      } catch (_) {failed=true;break;}
    }
    remember();await refreshSuggestions();renderList();next();
    message(failed?`${done}명을 저장한 뒤 중단했습니다. 서버 연결을 확인하고 다시 시도하세요.`:`${done}명을 일괄 저장했습니다. 틀린 사람은 상자를 눌러 직접 다시 저장하세요.`);
  }
  el('bulk-spectators').addEventListener('click',()=>bulkSave('spectator'));
  el('bulk-team-a').addEventListener('click',()=>bulkSave('team_a'));
  el('bulk-team-b').addEventListener('click',()=>bulkSave('team_b'));
  // The candidate list is grouped by what the reviewer has to do, and the boxes on the image
  // use the same group colours, so a card and its box are easy to match.
  const boxes=new Map();
  const shortId=p=>String(p.id).startsWith('manual-')?'직접':String(p.id).replace(/^cand-/,'#');
  function groupOf(p) {
    return reviewed.has(p.id)?'done':tierOf(p);
  }
  const GROUPS=[['todo','확인 필요','팀을 알 수 없는 후보'],['referee','심판 후보','경기장 안의 아주 어두운 옷 (장면당 1명)'],
    ['pale','밝은 옷','경기장 안, 형광 아님: 조명에 바랜 조끼일 수도 있음'],
    ['team_a','팀 A 후보','형광 조끼'],['team_b','팀 B 후보','경기장 안, 형광 아님 (다른 팀으로 가정)'],
    ['spectator','관중 후보','경기장 밖이거나 화면 앞쪽'],['done','확인 완료','저장했거나 건너뜀']];
  function cardNote(p,key) {
    if(key==='done') return answerText(answers[p.id]);
    if(key==='team_a') return '추천: 필드 선수 · 형광 조끼';
    if(key==='team_b') return `추천: 필드 선수 · ${shirtHint(p,'team_b').detail}`;
    if(key==='referee') return '추천: 심판';
    if(key==='pale') return '팀 직접 확인';
    if(key==='spectator') return '추천: 관중';
    const proposal=suggestions[p.id];
    return proposal?`추천 팀 ${proposal.team_group==='team_a'?'A':'B'}`:'직접 분류';
  }
  // Short tag shown next to the ID on cards and boxes: team for players, otherwise what it is expected to be.
  function tagOf(p,key) {
    if(key==='team_a') return '팀 A';
    if(key==='team_b') return '팀 B';
    if(key==='spectator') return '관중?';
    if(key==='referee') return '심판?';
    if(key==='pale') return '밝은 옷';
    if(key==='done') {const a=answers[p.id];return a&&a.team==='team_a'?'팀 A':a&&a.team==='team_b'?'팀 B':a&&a.role&&a.role!=='skip'?ROLE_NAMES[a.role]||'완료':'완료';}
    return '미분류';
  }
  const answerTeamClass=p=>{const a=answers[p.id];return a&&a.team==='team_a'?' ans-team_a':a&&a.team==='team_b'?' ans-team_b':'';};
  function renderList() {
    refereeCache=null;
    const list=el('label-list');list.replaceChildren();
    const members={};
    for(const p of queue) (members[groupOf(p)]||=[]).push(p);
    for(const p of queue) {
      const box=boxes.get(p.id);
      if(box) {
        const key=groupOf(p);
        box.className=`manual-box group-${key}${key==='done'?answerTeamClass(p):''}${selected&&selected.id===p.id?' is-selected':''}`;
        box.textContent=`${shortId(p)} ${tagOf(p,key)}`;
      }
    }
    for(const [key,title,desc] of GROUPS) {
      const people=(members[key]||[]).sort((a,b)=>a.bbox[0]-b.bbox[0]);
      if(!people.length) continue;
      const section=document.createElement('section');section.className=`person-group group-${key}`;
      const head=document.createElement('h4');head.textContent=`${title} ${people.length}명 · ${desc}`;section.append(head);
      const cards=document.createElement('div');cards.className='person-cards';
      for(const p of people) {
        const card=document.createElement('button');card.type='button';
        card.className=`person-card group-${key}${key==='done'?answerTeamClass(p):''}${selected&&selected.id===p.id?' is-selected':''}`;
        const dot=document.createElement('span');dot.className='dot';
        const name=document.createElement('strong');name.textContent=`${shortId(p)} · ${tagOf(p,key)}`;
        const note=document.createElement('small');note.textContent=cardNote(p,key);
        card.append(dot,name,note);card.addEventListener('click',()=>selectPerson(p,{reveal:true}));cards.append(card);
      }
      section.append(cards);list.append(section);
    }
    updateBulk();
    const h=hooks(); if(h.changed) h.changed();
  }
  function selectPerson(p, options) {
    selected=p;
    const team=teamHint(p), sh=shirtHint(p,team);
    const tier=tierOf(p);
    const hint=tier==='spectator'?'관중 후보: 경기장 밖이거나 화면 앞쪽 (미확정)':tier==='referee'?'심판 후보: 경기장 안의 아주 어두운 옷 (미확정)':tier==='pale'?'밝은 옷: 팀을 직접 확인하세요 (조명에 바랜 팀 A 조끼일 수도 있음)':team==='team_a'?'팀 A 후보: 형광 조끼 (미확정)':team==='team_b'?'팀 B 후보: 경기장 안, 형광 아님 (다른 팀으로 가정, 미확정)':'색상 미분류';
    el('label-selected').textContent=`추적 ID ${p.id} · ${hint}`;
    // Recommended role: spectator or referee hint, otherwise player when a team hint exists or the box was drawn by hand.
    const roleRec=tier==='spectator'?'spectator':tier==='referee'?'referee':(team||p.annotation_origin==='human_drawn')?'player':'';
    el('label-role').value=roleRec; el('label-team').value='unknown'; el('label-shirt').value='unknown';
    el('label-shirt-detail').value='';
    teamPrefilled=Boolean(team);
    if(team) {el('label-team').value=team;el('label-shirt').value=sh.color;el('label-shirt-detail').value=sh.detail;}
    markRecommended(el('label-role'),roleRec);
    markRecommended(el('label-team'),team||'');
    markRecommended(el('label-shirt'),team&&sh.color!=='unknown'?sh.color:'');
    const proposal=suggestions[p.id];
    el('label-quick-question').hidden=!proposal || reviewed.has(p.id);
    const askSpectator=spectatorHint(p) && !reviewed.has(p.id);
    const askTeam=(Boolean(team)||tier==='referee') && !askSpectator && !reviewed.has(p.id);
    el('label-spectator-question').hidden=!askSpectator;
    el('label-team-question').hidden=!askTeam;
    el('label-team-text').textContent=!askTeam?'':tier==='referee'?'자동 추천입니다: 심판 (경기장 안의 아주 어두운 옷). 맞으면 바로 저장합니다.':`자동 추천입니다: ${teamName(team)}${sh.detail?' · '+sh.detail:''} · 필드 선수. 맞으면 바로 저장합니다.`;
    if(askSpectator||askTeam) el('label-quick-question').hidden=true;
    el('label-quick-yes').disabled=!proposal || reviewed.has(p.id);
    el('label-quick-text').textContent=proposal?`이 사람은 기준과 같은 팀 ${proposal.team_group==='team_a'?'A':'B'}의 필드 선수인가요?`:'';
    el('label-apply-proposal').disabled=!proposal;
    el('label-proposal').textContent=proposal ? `비슷한 상의 후보: 이 경기 ${proposal.team_group==='team_a'?'팀 A':'팀 B'} (근거 ID ${proposal.reference_ids.join(', ')}). 심판·골키퍼도 비슷할 수 있습니다. 확대 화면 확인 후에만 추천을 적용하세요.` : '확인된 유니폼과 가까운 팀 후보가 없습니다.';
    el('label-save').disabled=false; el('label-skip').disabled=false;
    el('label-delete').hidden=p.annotation_origin!=='human_drawn';
    const [x1,y1,x2,y2]=p.bbox, image=el('label-image'), canvas=el('label-crop'),ctx=canvas.getContext('2d');
    ctx.clearRect(0,0,canvas.width,canvas.height);
    if(image.naturalWidth && image.naturalHeight) {
      const w=image.naturalWidth,h=image.naturalHeight,pad=.25,dx=(x2-x1)*pad,dy=(y2-y1)*pad;
      const sx=Math.max(0,(x1-dx)*w),sy=Math.max(0,(y1-dy)*h),ex=Math.min(w,(x2+dx)*w),ey=Math.min(h,(y2+dy)*h);
      const scale=Math.min(canvas.width/(ex-sx),canvas.height/(ey-sy));
      ctx.drawImage(image,sx,sy,ex-sx,ey-sy,(canvas.width-(ex-sx)*scale)/2,(canvas.height-(ey-sy)*scale)/2,(ex-sx)*scale,(ey-sy)*scale);
    }
    message(`확인한 항목 ${reviewed.size}/${queue.length} · 후보는 팀 확정이 아닙니다. 잘 안 보이면 건너뛰세요.`);
    renderList();
    const box=boxes.get(p.id);
    // Only an explicit click may bring the box into view, and only inside the image's own horizontal
    // scroller: never move the whole page (that made it jump on every scene change).
    if(box&&options&&options.reveal) revealBox(box);
  }
  function revealBox(box) {
    const holder=el('label-stage').parentElement;
    if(!holder||!holder.getBoundingClientRect||!box.getBoundingClientRect) return;
    const h=holder.getBoundingClientRect(), b=box.getBoundingClientRect();
    if(b.left<h.left||b.right>h.right) holder.scrollLeft+=(b.left+b.width/2)-(h.left+h.width/2);
  }
  function next() {
    const open=v=>!reviewed.has(v.id);
    const p=queue.find(v=>open(v)&&!spectatorHint(v)&&suggestions[v.id]) || queue.find(v=>open(v)&&!spectatorHint(v)) || queue.find(open);
    if(p) {selectPerson(p); return;}
    el('label-spectator-question').hidden=true;el('label-team-question').hidden=true;
    selected=null; el('label-save').disabled=true;el('label-skip').disabled=true;el('label-quick-question').hidden=true;el('label-delete').hidden=true;
    el('label-crop').getContext('2d').clearRect(0,0,el('label-crop').width,el('label-crop').height);
    if(!queue.length) {
      el('label-selected').textContent='이 장면에는 자동 후보 상자가 없습니다.';
      message('보이는 선수를 화면에서 직접 상자로 그려 추가해 주세요. 확인을 마치면 다음 장면으로 이동하세요.');
      return;
    }
    el('label-selected').textContent='이 화면의 확인을 마쳤습니다.';
    message('답변하지 못한 사람은 저장되지 않았습니다. 다음 장면으로 이동하거나 목록에서 다시 선택하세요.');
  }
  let scenes=[];
  function renderSceneNav() {
    const index=scenes.findIndex(s=>s.token===snapshot?.token);
    el('scene-prev').disabled=index<=0;
    el('scene-next').disabled=index<0||index>=scenes.length-1;
    const split=scenes[index]?.split, note=split==='eval'?' · 평가용: 빠진 선수까지 전부 라벨':split==='buffer_excluded'?' · 평가 인접: 학습 제외':'';
    el('scene-position').textContent=index<0?'':`장면 ${index+1} / ${scenes.length}${note}`;
    renderSceneGrid();
  }
  // ---- scene picker: thumbnail cards with number, time, split and saved-answer count ----
  const SPLIT_TAGS={eval:'평가',train:'학습',buffer_excluded:'인접'};
  const FILTERS=[['all','전체',()=>true],['eval','평가용',s=>s.split==='eval'],['train','학습용',s=>s.split==='train'],
    ['todo','라벨 없음',s=>!s.label_count],['done','라벨 있음',s=>s.label_count>0]];
  let sceneFilter='all';
  try {if(typeof localStorage!=='undefined'){const f=localStorage.getItem('scene-filter');if(FILTERS.some(x=>x[0]===f))sceneFilter=f;}} catch (_) {}
  const clock=sec=>typeof sec==='number'?`${Math.floor(sec/60)}:${String(Math.floor(sec%60)).padStart(2,'0')}`:'';
  function renderSceneGrid() {
    const grid=el('scene-grid'),bar=el('scene-filters');
    if(!grid||!bar) return;
    bar.replaceChildren();
    for(const [key,label,test] of FILTERS) {
      const b=document.createElement('button');b.type='button';b.className=`scene-filter${key===sceneFilter?' is-active':''}`;
      b.textContent=`${label} ${scenes.filter(test).length}`;
      b.addEventListener('click',()=>{sceneFilter=key;try{if(typeof localStorage!=='undefined')localStorage.setItem('scene-filter',key);}catch(_){}renderSceneGrid();});
      bar.append(b);
    }
    grid.replaceChildren();
    const test=(FILTERS.find(x=>x[0]===sceneFilter)||FILTERS[0])[2];
    let current=null;
    scenes.forEach((s,i)=>{
      if(!test(s)&&s.token!==snapshot?.token) return;
      const card=document.createElement('button');card.type='button';
      const isCurrent=s.token===snapshot?.token;
      card.className=`scene-card${isCurrent?' is-current':''}${s.label_count>0?' has-labels':''}${s.split?' split-'+s.split:''}`;
      card.title=`장면 ${i+1}${s.clip_time!=null?' · 경기 구간 '+clock(s.clip_time):''}${SPLIT_TAGS[s.split]?' · '+SPLIT_TAGS[s.split]:''}${s.label_count>0?' · 저장한 답 '+s.label_count+'개':' · 아직 저장한 답 없음'}`;
      const img=document.createElement('img');img.alt='';img.width=96;img.height=54;
      img.src=`/thumbs/${s.token}.jpg`;img.addEventListener('error',()=>{img.hidden=true;});
      const num=document.createElement('strong');num.textContent=String(i+1);
      const meta=document.createElement('small');
      meta.textContent=`${clock(s.clip_time)}${s.split&&SPLIT_TAGS[s.split]?' · '+SPLIT_TAGS[s.split]:''}${s.label_count>0?' · 라벨 '+s.label_count:''}`;
      card.append(img,num,meta);card.addEventListener('click',()=>goToScene(s.token));grid.append(card);
      if(isCurrent) current=card;
    });
    el('scene-picker-count').textContent=`(${scenes.length}장면)`;
    // keep the current card visible inside the picker only; never scroll the page
    if(current&&grid.clientHeight) {
      const top=current.offsetTop,h=grid.clientHeight;
      if(top<grid.scrollTop||top+current.offsetHeight>grid.scrollTop+h) grid.scrollTop=Math.max(0,top-h/2);
    }
  }
  let refreshTimer=null;
  function refreshScenesSoon() {
    if(typeof setTimeout!=='function') return;
    if(typeof clearTimeout==='function') clearTimeout(refreshTimer);
    refreshTimer=setTimeout(refreshScenes,1200);
  }
  async function refreshScenes() {
    try {
      const r=await fetch('/api/v1/training-labels/scenes',{method:'POST'});
      if(!r.ok)throw new Error();
      const data=await r.json();scenes=Array.isArray(data.scenes)?data.scenes:[];
    } catch (_) {scenes=[];}
    renderSceneNav();
  }
  async function goToScene(token) {
    if(!token||token===snapshot?.token) return;
    el('scene-prev').disabled=true;el('scene-next').disabled=true;
    try {
      const r=await fetch('/api/v1/training-labels/restore',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token})});
      if(!r.ok)throw new Error();show(await r.json());
    } catch (_) {message('장면을 불러오지 못했습니다. 잠시 후 다시 시도하세요.');renderSceneNav();}
  }
  function moveScene(step) {
    const index=scenes.findIndex(s=>s.token===snapshot?.token), target=scenes[index+step];
    if(index<0||!target) return;
    return goToScene(target.token);
  }
  el('scene-prev').addEventListener('click',()=>moveScene(-1));
  el('scene-next').addEventListener('click',()=>moveScene(1));
  el('scene-next-unlabeled').addEventListener('click',()=>{
    const index=scenes.findIndex(s=>s.token===snapshot?.token);
    const target=scenes.slice(index+1).find(s=>!s.label_count)||scenes.find(s=>!s.label_count&&s.token!==snapshot?.token);
    if(target) goToScene(target.token); else message('라벨이 없는 장면이 더 없습니다.');
  });
  // Left/Right arrow keys move between scenes (not while typing or choosing in a dropdown).
  if(document.addEventListener) document.addEventListener('keydown',event=>{
    if((event.key!=='ArrowLeft'&&event.key!=='ArrowRight')||event.altKey||event.ctrlKey||event.metaKey||event.shiftKey) return;
    if(['INPUT','SELECT','TEXTAREA'].includes(event.target&&event.target.tagName)) return;
    moveScene(event.key==='ArrowLeft'?-1:1);
  });
  function addBox(p) {
    const box=document.createElement('button'),[x1,y1,x2,y2]=p.bbox;
    box.type='button';box.className='manual-box';box.style.left=`${x1*100}%`;box.style.top=`${y1*100}%`;box.style.width=`${(x2-x1)*100}%`;box.style.height=`${(y2-y1)*100}%`;
    box.textContent=shortId(p);box.title=`추적 ID ${p.id}`;boxes.set(p.id,box);box.addEventListener('click',()=>selectPerson(p));el('label-boxes').append(box);
  }
  function show(data) {
    snapshot=data;selected=null;suggestions={};profiles.clear();sessionStorage.setItem('training-label-snapshot',snapshot.token);
    try {const saved=JSON.parse(sessionStorage.getItem(storageKey())||'[]');reviewed=new Set(Array.isArray(saved)?saved:[]);} catch (_) {reviewed=new Set();}
    try {const saved=JSON.parse(sessionStorage.getItem(answersKey())||'{}');answers=saved&&typeof saved==='object'&&!Array.isArray(saved)?saved:{};} catch (_) {answers={};}
    queue=[...snapshot.people].sort((a,b)=>(a.suggested_color_group==null?0:1)-(b.suggested_color_group==null?0:1));
    el('label-stage').hidden=false; el('label-boxes').replaceChildren();el('label-list').replaceChildren();boxes.clear();
    for(const p of queue) addBox(p);
    renderList();const image=el('label-image');image.onload=async()=>{profiles.clear();await refreshSuggestions();renderList();next();};image.src='data:image/jpeg;base64,'+snapshot.image;
    el('label-save').disabled=true;el('label-skip').disabled=true;
    refreshScenes();
    const h=hooks(); if(h.sceneShown) h.sceneShown(snapshot.token);
    if(h.minimapScene) h.minimapScene(snapshot.token);
  }
  globalThis.__reviewHooks=Object.assign(globalThis.__reviewHooks||{},{
    rerender(){if(!snapshot)return;renderList();if(selected)selectPerson(selected);},
    tierOf(p){return tierOf(p);},
    people(){return queue;},
    // A box the reviewer just drew: show it in place, select it and prefill role and colour hints.
    addPerson(person){if(!snapshot||!person||!Array.isArray(person.bbox))return;snapshot.people.push(person);queue.push(person);addBox(person);renderList();selectPerson(person);}
  });
  async function freeze() {
    message('화면을 가져오는 중입니다.');el('label-freeze').disabled=true;
    try {const response=await fetch('/api/v1/training-labels/snapshot',{method:'POST'});if(!response.ok)throw new Error();show(await response.json());}
    catch (_) {message('화면을 가져오지 못했습니다. 로컬 서버와 영상 분석 상태를 확인하세요.');}
    finally {el('label-freeze').disabled=false;}
  }
  async function save(event, onlyIfNew=false) {
    event.preventDefault();if(!snapshot||!selected)return;
    const role=el('label-role').value,shirt_color=el('label-shirt').value,shirt_detail=el('label-shirt-detail').value;
    let team_group=el('label-team').value;
    // A team that was only prefilled from a hint must not block roles that have no team.
    if(teamPrefilled&&['referee','unknown','spectator','shadow','duplicate'].includes(role)) team_group='unknown';
    if(!role){message('역할을 선택하세요.');return;}
    if(['referee','unknown'].includes(role)&&team_group!=='unknown'){message('심판과 확인 불가는 팀을 미확인으로 선택하세요.');return;}
    const id=selected.id;el('label-save').disabled=true;
    try {const r=await fetch('/api/v1/training-labels',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:snapshot.token,track_id:id,role,team_group,shirt_color,shirt_detail,only_if_new:onlyIfNew})});if(!r.ok)throw new Error();reviewed.add(id);recordAnswer(id,role,team_group);remember();await refreshSuggestions();next();}
    catch (_) {message('저장에 실패했습니다. 로컬 서버 연결을 확인하세요.');el('label-save').disabled=false;}
  }
  async function refreshSuggestions() {
    const token=snapshot?.token;
    if(!token) return;
    try {const r=await fetch('/api/v1/training-labels/suggestions',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token})});if(!r.ok)throw new Error();const data=await r.json();if(snapshot?.token===token){suggestions=data.suggestions||{};for(const id of data.confirmed_ids||[])reviewed.add(id);remember();renderList();}}
    catch (_) {suggestions={};}
  }
  el('label-apply-proposal').addEventListener('click',()=>{
    const proposal=selected && suggestions[selected.id];
    if(!proposal) return;
    el('label-team').value=proposal.team_group;
    el('label-proposal').textContent='추천을 선택했습니다. 역할과 팀을 직접 확인한 뒤 저장하세요.';
  });
  el('label-quick-yes').addEventListener('click',async()=>{
    const proposal=selected && suggestions[selected.id];
    if(!proposal || reviewed.has(selected.id) || !['team_a','team_b'].includes(proposal.team_group)) return;
    el('label-quick-yes').disabled=true;
    el('label-role').value='player';el('label-team').value=proposal.team_group;
    el('label-shirt').value='unknown';el('label-shirt-detail').value='';
    await save({preventDefault(){}},true);
  });
  el('label-spectator-yes').addEventListener('click',async()=>{
    if(!selected || !spectatorHint(selected) || reviewed.has(selected.id)) return;
    el('label-spectator-yes').disabled=true;
    el('label-role').value='spectator';el('label-team').value='unknown';
    el('label-shirt').value='unknown';el('label-shirt-detail').value='';
    try {await save({preventDefault(){}});} finally {el('label-spectator-yes').disabled=false;}
  });
  // A box drawn by hand can be removed again (the server refuses once an answer was saved for it).
  function removePerson(id) {
    queue=queue.filter(p=>p.id!==id);
    if(snapshot) snapshot.people=snapshot.people.filter(p=>p.id!==id);
    const box=boxes.get(id);if(box&&box.remove) box.remove();
    boxes.delete(id);reviewed.delete(id);delete answers[id];remember();
    if(selected&&selected.id===id) selected=null;
    renderList();next();
  }
  el('label-delete').addEventListener('click',async()=>{
    if(!snapshot||!selected||selected.annotation_origin!=='human_drawn') return;
    if(!confirm('이 상자를 삭제합니다. 직접 그린 상자만 지울 수 있고, 이미 답을 저장한 상자는 지워지지 않습니다. 계속할까요?')) return;
    const id=selected.id;
    try {
      const r=await fetch('/api/v1/training-labels/delete-box',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:snapshot.token,id})});
      if(!r.ok){const d=await r.json().catch(()=>({}));message(typeof d.detail==='string'?d.detail:'상자를 삭제하지 못했습니다.');return;}
    } catch (_) {message('상자를 삭제하지 못했습니다. 서버 연결을 확인하세요.');return;}
    removePerson(id);message('상자를 삭제했습니다.');
  });
  el('label-team-yes').addEventListener('click',async()=>{
    const isReferee=selected&&tierOf(selected)==='referee';
    if(!selected||reviewed.has(selected.id)||(!teamHint(selected)&&!isReferee)) return;
    el('label-team-yes').disabled=true;
    if(isReferee) {
      el('label-role').value='referee';el('label-team').value='unknown';el('label-shirt').value='unknown';el('label-shirt-detail').value='';
    } else {
      const team=teamHint(selected),sh=shirtHint(selected,team);
      el('label-role').value='player';el('label-team').value=team;el('label-shirt').value=sh.color;el('label-shirt-detail').value=sh.detail;
    }
    try {await save({preventDefault(){}});} finally {el('label-team-yes').disabled=false;}
  });
  el('label-team-no').addEventListener('click',()=>{el('label-team-question').hidden=true;message('역할과 팀을 아래에서 직접 선택해 주세요. 아직 저장되지 않았습니다.');});
  // Enter saves the selected person once a role is chosen (not while typing or on a focused control).
  if(document.addEventListener) document.addEventListener('keydown',event=>{
    if(event.key!=='Enter'||event.isComposing) return;
    if(['INPUT','SELECT','TEXTAREA','BUTTON'].includes(event.target&&event.target.tagName)) return;
    if(selected&&el('label-role').value) save(event);
  });
  el('label-spectator-no').addEventListener('click',()=>{el('label-spectator-question').hidden=true;message('역할과 팀을 아래에서 직접 선택해 주세요. 아직 저장되지 않았습니다.');});
  el('label-quick-no').addEventListener('click',()=>{el('label-quick-question').hidden=true;message('역할과 팀을 아래에서 직접 선택해 주세요. 아직 저장되지 않았습니다.');});
  el('label-quick-unknown').addEventListener('click',()=>{if(selected){reviewed.add(selected.id);recordAnswer(selected.id,'skip','unknown');remember();renderList();next();}});
  el('label-freeze').addEventListener('click',freeze);el('label-form').addEventListener('submit',save);
  el('label-next-source').addEventListener('click',async()=>{
    try {const r=await fetch('/api/v1/training-labels/next-sample',{method:'POST'});if(!r.ok)throw new Error();await freeze();}
    catch (_) {message('다른 학습 장면을 불러오지 못했습니다. 학습 자료 전용 화면을 확인하세요.');}
  });
  el('label-skip').addEventListener('click',()=>{if(selected){reviewed.add(selected.id);recordAnswer(selected.id,'skip','unknown');remember();renderList();next();}});
  const previous=sessionStorage.getItem('training-label-snapshot');
  const post=(path,body)=>fetch(`/api/v1/training-labels/${path}`,{method:'POST',headers:{'Content-Type':'application/json'},body:body&&JSON.stringify(body)});
  // First visit: open the first scene in the list order (not whichever file changed last); older servers
  // without a scene list fall back to the newest saved scene.
  async function firstScene() {
    try {
      const r=await post('scenes');
      if(r.ok){const first=((await r.json()).scenes||[])[0];if(first){const s=await post('restore',{token:first.token});if(s.ok)return s.json();}}
    } catch (_) {}
    const latest=await post('latest');
    if(!latest.ok) throw new Error();
    return latest.json();
  }
  (previous?post('restore',{token:previous}).then(r=>{if(!r.ok)throw new Error();return r.json();}):firstScene())
    .then(show).catch(()=>sessionStorage.removeItem('training-label-snapshot'));
})();
