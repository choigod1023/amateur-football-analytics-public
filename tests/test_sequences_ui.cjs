const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

class Element {
  constructor(tag='div') { this.tag=tag; this.children=[]; this.listeners={}; this.attributes={}; this.hidden=false; this.value=''; this.textContent=''; this.dataset={}; this.width=720; this.height=470; }
  addEventListener(name, fn) { this.listeners[name]=fn; }
  async emit(name, event={}) { if (this.listeners[name]) return this.listeners[name](event); }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children=children; this.textContent=''; }
  setAttribute(name,value) { this.attributes[name]=value; }
  getAttribute(name) { return this.attributes[name] || null; }
  removeAttribute(name) { delete this.attributes[name]; }
  set src(value) { this.attributes.src=value; }
  querySelectorAll(tag) { return this.children.flatMap(c => [...(c.tag===tag ? [c] : []), ...c.querySelectorAll(tag)]); }
  pause() {} load() {}
  getContext() { return new Proxy({}, {get(target,key) { if (!(key in target)) target[key]=()=>{}; return target[key]; }}); }
}
const ids = ['sequence-start','sequence-end','sequence-form','sequence-save','sequence-message','sequence-refresh','sequence-empty','sequence-list','sequence-detail','sequence-detail-title','sequence-video','sequence-snapshot','sequence-snapshot-note','sequence-pitch','sequence-pitch-note','sequence-metrics','sequence-feedback','sequence-limitations'];
const elements=Object.fromEntries(ids.map(id=>[id,new Element()]));
let items=[], posts=0;
const id='1234567890abcdef1234567890abcdef';
const fetch=async (url, options={}) => {
  assert.equal(url,'/api/v1/sequences');
  if (options.method === 'POST') {
    posts++;
    const body=JSON.parse(options.body); assert.deepEqual(body,{start_s:1,end_s:3});
    const item={id,start_s:1,end_s:3,status:'ready',players:[],metrics:{team_width_m:null,team_length_m:null},feedback:[],limitations:'동기화된 분석 없음'};
    items=[item]; return {ok:true,json:async()=>item};
  }
  return {ok:true,json:async()=>({items:[...items,{id:'../malicious',start_s:0,end_s:1}]})};
};
const context={document:{getElementById:id=>elements[id],createElement:tag=>new Element(tag),createTextNode:s=>s},fetch,AbortSignal,Number,JSON,Math,Array,String,encodeURIComponent,
  PitchData:{prepare:players=>({players:players||[],located:[],missing:0})},teamSettings:{mode:'auto'},TeamColors:{foreground:()=> '#000',resolveColors:()=>({home:'#abcdef',away:'#123456'})}};
vm.runInNewContext(fs.readFileSync('web/sequences.js','utf8'),context);
(async()=>{
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(elements['sequence-list'].children.length,0); // Invalid server ID rejected.
  elements['sequence-start'].value='0';elements['sequence-end'].value='21';
  await elements['sequence-form'].emit('submit',{preventDefault(){}});
  assert.equal(posts,0);
  assert.match(elements['sequence-message'].textContent,/최대 20초/);
  elements['sequence-start'].value='1';elements['sequence-end'].value='3';
  await elements['sequence-form'].emit('submit',{preventDefault(){}});
  assert.equal(posts,1);
  assert.equal(elements['sequence-detail'].hidden,false);
  assert.equal(elements['sequence-video'].getAttribute('src'),`/api/v1/sequences/${id}/video`);
  assert.equal(elements['sequence-snapshot'].hidden,true);
  assert.match(elements['sequence-pitch-note'].textContent,/위치가 없어/);
  assert.match(elements['sequence-feedback'].textContent,/저장된 코칭 결과가 없습니다/);
  assert.equal(elements['sequence-limitations'].textContent,'동기화된 분석 없음');
  items[0].snapshot_available=true;items[0].snapshot_source_time_s=2;items[0].snapshot_offset_s=1;
  await elements['sequence-refresh'].emit('click');
  assert.equal(elements['sequence-snapshot'].getAttribute('src'),`/api/v1/sequences/${id}/snapshot.jpg`);
  assert.match(elements['sequence-snapshot-note'].textContent,/실제 프레임 한 장/);
  console.log('sequence UI validation, safe IDs and empty analysis passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
