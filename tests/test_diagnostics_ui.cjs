const assert=require('node:assert/strict'), fs=require('node:fs'), vm=require('node:vm');
const PitchData=require('../web/pitch'), TeamColors=require('../web/teams');
class Element {
  constructor(){this.textContent='';this.children=[];this.style={};this.hidden=false;this.classList={add(){},remove(){}};this.files=[];}
  append(...xs){this.children.push(...xs)} replaceChildren(...xs){this.children=xs}
  addEventListener(){} removeAttribute(){} getContext(){return new Proxy({}, {get:(t,k)=>t[k]||(()=>{}),set:(t,k,v)=>(t[k]=v,true)})}
}
const elements={};const element=id=>elements[id] ||= new Element();
class TimestampWatch {check(){return 'updating'} reset(){}}
const status={status:'running',fps:20,latency_ms:12,input_mode:'live'};
const data={timestamp:'2026-01-01T00:00:00Z',players:[{id:'2',team:'unknown',x:null,y:null,suggested_color_group:0}],metrics:{team_width_m:null,team_length_m:null},feedback:[],calibration_status:'not_configured',coaching_diagnostics:{state:'blocked',reasons:['calibration_unavailable','insufficient_located_team_members']}};
data.experimental_feedback=[{observation:'색상 후보 A 관측',interpretation:'확정 아님',suggestion:'영상 확인',limitations:'실험 위치'}];
const fetch=async url=>url.endsWith('status')?{ok:true,json:async()=>status}:url.endsWith('analysis')?{ok:true,json:async()=>data}:{ok:false};
const context={MatchRoster:require('../web/match-roster'),MinimapMotion:require('../web/minimap-motion'),requestAnimationFrame:()=>1,cancelAnimationFrame(){},document:{getElementById:element,createElement:()=>new Element(),createTextNode:t=>({textContent:t}),querySelector:()=>element('placeholder')},PitchData,TeamColors,TimestampWatch,fetch,localStorage:{getItem:()=>null},setTimeout:()=>1,clearTimeout(){},AbortController,performance:{now:()=>1},URL:{},Date,console,XMLHttpRequest:function(){}};
vm.runInNewContext(fs.readFileSync('web/app.js','utf8'),context);
setImmediate(()=>{
 assert.match(element('pitch-detail').textContent,/보정이 설정되지/);
 assert.match(element('team-review-reason').textContent,/미분류 1명/);
 assert.equal(element('pitch-player-list').hidden,false);
 assert.match(element('team-review-reason').textContent,/심판도 포함/);
 assert.match(element('pitch-players').children[0].textContent,/미분류 · 색상 후보 A \(미확인\) · 위치 미확인/);
 const content=element('feedback').children[0];
 assert.match(content.children[0].textContent,/코칭이 없습니다/);
 const messages=content.children[1].children.map(x=>x.textContent).join(' ');
 assert.match(messages,/보정이 설정되지/);assert.match(messages,/최소 2명/);assert.match(messages,/소속이 미확인/);
 const experimental=element('experimental-feedback');assert.equal(experimental.hidden,false);
 assert.match(experimental.children[0].textContent,/실험 공간 관찰/);
 assert.equal(experimental.children[1].children[0].children[1].textContent,'색상 후보 A 관측');
 assert.equal(element('match-roster').children.filter(x=>x.className==='roster-grid').reduce((n,x)=>n+x.children.length,0),22);
 console.log('diagnostics UI: ok');
});
