const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

class Element {
  constructor() {
    this.handlers = {}; this.children = []; this.options = []; this.style = {};
    this.classList = {add(){}, remove(){}}; this.hidden = false; this.disabled = false;
    this.parentElement = {before(){}}; this.value = ''; this.naturalWidth = 1920;
  }
  addEventListener(name, fn) { (this.handlers[name] ||= []).push(fn); }
  append(...items) { this.children.push(...items); this.options.push(...items); }
  emit(name, event = {}) { for (const fn of this.handlers[name] || []) fn(event); }
  getBoundingClientRect() { return {left:100, top:50, width:1000, height:500}; }
  setPointerCapture() {}
}

async function run() {
  const elements = Object.fromEntries(['label-stage','label-image','label-role','label-message','label-team','label-shirt'].map(id => [id, new Element()]));
  let tools;
  elements['label-stage'].parentElement.before = value => { tools=value; };
  let request, reloaded=false;
  const sandbox = {
    document:{getElementById:id => elements[id] || null, createElement:() => new Element()},
    sessionStorage:{getItem:()=>'snapshot123'},
    fetch:async (url, options) => { request={url, ...options}; return {ok:true,json:async()=>({token:'snapshot123',person:{id:'manual1'}})}; },
    window:{location:{reload(){reloaded=true;}}},
  };
  vm.runInNewContext(fs.readFileSync('web/review-annotation.js','utf8'), sandbox);
  assert.deepEqual(elements['label-role'].options.map(x=>x.value), ['spectator','shadow','duplicate']);
  elements['label-team'].value='team_a'; elements['label-role'].value='shadow'; elements['label-role'].emit('change');
  assert.equal(elements['label-team'].value,'unknown');
  const [toggle] = tools.children;
  toggle.emit('click');
  const event = (x,y) => ({button:0,clientX:x,clientY:y,pointerId:1,preventDefault(){},stopPropagation(){}});
  elements['label-stage'].emit('pointerdown',event(200,100));
  elements['label-stage'].emit('pointermove',event(300,250));
  elements['label-stage'].emit('pointerup',event(300,250));
  // releasing the drag adds the box at once, no confirm button
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(request.url,'/api/v1/training-labels/manual-box');
  assert.deepEqual(JSON.parse(request.body),{token:'snapshot123',bbox:[.1,.1,.2,.4]});
  assert.equal(reloaded,true);
  // with a host page that can show the box in place, the page is not reloaded
  let added=null; reloaded=false; request=null;
  sandbox.__reviewHooks.addPerson = person => { added = person; };
  elements['label-stage'].emit('pointerdown',event(200,100));
  elements['label-stage'].emit('pointerup',event(260,200));
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(added.id,'manual1');
  assert.equal(reloaded,false);
  // a tiny accidental drag is ignored
  request=null;
  elements['label-stage'].emit('pointerdown',event(500,300));
  elements['label-stage'].emit('pointerup',event(500,300));
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(request,null);
  console.log('review annotation UI passed');
}
run().catch(error => { console.error(error); process.exitCode=1; });
