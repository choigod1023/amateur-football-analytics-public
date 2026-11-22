'use strict';
// No timer: a scene stays on screen until the reviewer explicitly saves or refreshes.
const labels={same:'같은 선수',different:'다른 선수',unclear:'판단 어려움',before:'이전 설명이 맞음',after:'변경 설명이 맞음',both_wrong:'둘 다 맞지 않음'};
const items=document.querySelector('#items'),message=document.querySelector('#message');
const reviewScope = location.pathname === '/train/reappearance' ? 'occlusion-reappearance' : '';
if (reviewScope) {
  document.title='재등장 선수 확인 — Touchline';
  document.querySelector('h1').textContent='가려졌다 다시 나타난 선수 확인';
  document.querySelector('#evaluation').hidden=true;
}
function el(tag,text,className){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(className)n.className=className;return n;}
function readable(value){if(value===null||value===undefined)return '자료 없음';return typeof value==='string'?value:JSON.stringify(value,null,2);}
function card(item){
  const root=el('article');root.id=item.id;
  root.append(el('p',`${item.kind==='tracking'?'선수 연결':'코칭 비교'} · ${item.id}`,'meta'),el('h2',item.title||'장면 확인'),el('p',item.reason||'영상에서 판단해 주세요.','reason'));
  if(item.video){const video=el('video');video.controls=true;video.playsInline=true;video.preload='metadata';video.src=item.video;video.setAttribute('aria-label','비교할 경기 장면');root.append(video);}
  else root.append(el('p','이 장면의 영상 파일이 아직 준비되지 않았습니다.','meta'));
  if(item.images.length){const pictures=el('div',undefined,'pictures');item.images.forEach((url,i)=>{const a=el('a');a.href=url;a.target='_blank';a.rel='noopener';const img=el('img');img.src=url;img.alt=`선수 확대 사진 ${i+1}`;img.loading='lazy';a.append(img,el('span','원본 크기로 열기'));pictures.append(a);});root.append(pictures);}
  const comparison=el('div',undefined,'comparison');[['이전',item.before],['변경',item.after]].forEach(([title,value])=>{const section=el('section');section.append(el('h3',title),el('pre',readable(value)));comparison.append(section);});root.append(comparison);
  if(item.retired_reason){root.append(el('p',`이전 버전 비교 기록: ${item.retired_reason}`,'saved'));if(!item.answer)return root;}
  if(item.answer){root.append(el('p',`저장한 답: ${labels[item.answer.verdict]||item.answer.verdict}${item.answer.note?' · '+item.answer.note:''}`,'saved'));if(!item.answer_is_current)root.append(el('p','저장 이후 장면 자료가 달라졌습니다. 기존 답은 보존되며, 관리자가 새 항목으로 분리해야 합니다.'));return root;}
  const form=el('form',undefined,'answer-form');const choices=el('div',undefined,'choices');choices.setAttribute('role','group');choices.setAttribute('aria-label','장면 판단');let chosen=null;
  item.verdicts.forEach(v=>{const b=el('button',labels[v]||v);b.type='button';b.setAttribute('aria-pressed','false');b.addEventListener('click',()=>{chosen=v;for(const other of choices.children)other.setAttribute('aria-pressed',String(other===b));});choices.append(b);});
  const label=el('label','메모 (선택)');const note=el('textarea');note.maxLength=500;note.id=`note-${item.id}`;label.htmlFor=note.id;const save=el('button','답 저장','save');save.type='submit';const status=el('p');status.setAttribute('role','status');
  form.append(choices,label,note,save,status);form.addEventListener('submit',async event=>{event.preventDefault();if(!chosen){status.textContent='판단을 먼저 선택해 주세요.';return;}save.disabled=true;try{const r=await fetch('/api/v1/differences',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:item.id,verdict:chosen,note:note.value})});if(!r.ok)throw new Error(r.status===409?'이미 저장한 답이 있거나 장면이 변경되었습니다. 기존 답은 그대로 보존됩니다.':`저장 실패 (${r.status})`);status.textContent='저장했습니다. 이 장면은 새로고침하면 대기 목록에서 제외됩니다.';for(const control of form.querySelectorAll('button,textarea'))control.disabled=true;}catch(e){status.textContent=e.message;save.disabled=false;}});root.append(form);return root;
}
async function load(){message.textContent='장면을 불러오는 중입니다.';try{const r=await fetch('/api/v1/differences?include_answered='+document.querySelector('#answered').checked+(reviewScope ? '&scope='+encodeURIComponent(reviewScope) : ''));if(!r.ok)throw new Error(`목록을 불러오지 못했습니다 (${r.status})`);const data=await r.json();const summary=data.review_summary;if(summary){const p=summary.preferences;document.querySelector('#evaluation').textContent=`저장한 코칭 평가: 변경 설명 ${p.after}개 · 이전 설명 ${p.before}개 · 둘 다 맞지 않음 ${p.both_wrong}개 · 판단 어려움 ${p.unclear}개. 이 값은 검토한 장면의 선호이며 전체 정확도가 아닙니다.`;}document.querySelector('#count').textContent=`확인 대기 ${data.remaining}개 · 저장 ${data.completed}개`;items.replaceChildren(...data.items.map(card));if(!data.items.length)items.append(el('p','지금 확인할 장면이 없습니다.','empty'));message.textContent='사진은 자동으로 사라지지 않습니다. 새로고침하면 저장하지 않은 선택과 메모는 지워집니다.';}catch(e){message.textContent=e.message;}}
document.querySelector('#refresh').addEventListener('click',load);document.querySelector('#answered').addEventListener('change',load);load();
