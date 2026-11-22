const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

class Element {
  constructor() {
    this.handlers = {}; this.children = []; this.options = []; this.style = {};
    this.classList = {add(){}, remove(){}}; this.hidden = false; this.disabled = false;
    this.parentElement = {before(){}}; this.value = ''; this.naturalWidth = 1920; this.naturalHeight = 1080;
  }
  addEventListener(name, fn) { (this.handlers[name] ||= []).push(fn); }
  append(...items) { this.children.push(...items); this.options.push(...items); }
  emit(name, event = {}) { for (const fn of this.handlers[name] || []) fn(event); }
  getBoundingClientRect() { return {left:0, top:0, width:1000, height:500}; }
  setPointerCapture() {}
}

async function run() {
  const elements = Object.fromEntries(['label-stage','label-image','label-role','label-message','label-team','label-shirt'].map(id => [id, new Element()]));
  const square = [[.1, .5], [.9, .5], [.9, .95], [.1, .95]];
  const urls = [];
  const sandbox = {
    document:{getElementById:id => elements[id] || null, createElement:() => new Element()},
    sessionStorage:{getItem:()=>'bbb'},
    fetch:async url => {
      urls.push(url);
      if (url.endsWith('/scenes')) return {ok:true, json:async()=>({scenes:[{token:'aaa',clip_time:30},{token:'bbb',clip_time:60}]})};
      if (url.endsWith('/pitch-regions')) return {ok:true, json:async()=>({regions:{aaa:square}})};
      return {ok:false};
    },
    window:{location:{reload(){}}},
  };
  sandbox.globalThis = sandbox;
  vm.runInNewContext(fs.readFileSync('web/review-annotation.js','utf8'), sandbox);
  const hooks = sandbox.__reviewHooks;
  assert.equal(hooks.insidePitch({bbox:[.4,.6,.42,.66]}), null, 'no region known before a scene is shown');
  await hooks.sceneShown('bbb');
  assert.ok(urls.some(u => u.endsWith('/pitch-regions')));
  // scene bbb has no polygon of its own, so it reuses the earlier scene's polygon
  assert.equal(hooks.insidePitch({bbox:[.4,.6,.42,.66]}), true);
  assert.equal(hooks.insidePitch({bbox:[.4,.2,.42,.25]}), false);
  // a spectator standing in front of the pitch edge, feet below the polygon
  assert.equal(hooks.insidePitch({bbox:[.4,.9,.45,.99]}), false);
  // a region drawn for one camera setting must not carry over to a scene of another setting
  const scenesWithCameras = [{token:'aaa', clip_time:30, camera:'cam1'}, {token:'bbb', clip_time:60, camera:'cam2'},
    {token:'ccc', clip_time:90, camera:'cam1'}, {token:'ddd', clip_time:120, camera:null}];
  sandbox.fetch = async url => url.endsWith('/scenes') ? {ok:true, json:async()=>({scenes:scenesWithCameras})}
    : url.endsWith('/pitch-regions') ? {ok:true, json:async()=>({regions:{aaa:square}})} : {ok:false};
  sandbox.sessionStorage.getItem = () => 'bbb';
  await hooks.sceneShown('bbb');
  assert.equal(hooks.insidePitch({bbox:[.4,.6,.42,.66]}), null, 'cam2 scene must not use the cam1 region');
  sandbox.sessionStorage.getItem = () => 'ccc';
  await hooks.sceneShown('ccc');
  assert.equal(hooks.insidePitch({bbox:[.4,.6,.42,.66]}), true, 'a later cam1 scene still uses it');
  sandbox.sessionStorage.getItem = () => 'ddd';
  await hooks.sceneShown('ddd');
  assert.equal(hooks.insidePitch({bbox:[.4,.6,.42,.66]}), null, 'a scene without a camera gets no region');
  // a box taller than any player is a spectator even when its feet fall inside the polygon
  sandbox.sessionStorage.getItem = () => 'ccc';
  await hooks.sceneShown('ccc');
  assert.equal(hooks.insidePitch({bbox:[.4,.80,.45,.93]}), false, 'a 140 px tall person standing inside the polygon');
  assert.equal(hooks.insidePitch({bbox:[.4,.80,.42,.86]}), true, 'a 65 px person at the same place is a player');
  // a small player whose feet are hidden by a rail just below the polygon edge still counts as inside
  assert.equal(hooks.insidePitch({bbox:[.4,.90,.42,.955]}), true, 'small box: the point above the bottom is inside');
  assert.equal(hooks.insidePitch({bbox:[.4,.93,.42,.99]}), false, 'small box entirely below the edge');
  console.log('pitch region UI passed');
}
run().catch(error => { console.error(error); process.exitCode = 1; });
