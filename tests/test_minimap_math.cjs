const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

class Element {
  constructor() { this.handlers = {}; this.children = []; this.style = {}; this.classList = {add(){}, remove(){}, toggle(){}}; this.hidden = false; this.value = ''; this.className = ''; this.dataset = {}; }
  addEventListener(n, fn) { (this.handlers[n] ||= []).push(fn); }
  append(...items) { this.children.push(...items); }
  replaceChildren() { this.children = []; }
  getBoundingClientRect() { return {left:0, top:0, width:1000, height:500}; }
}
const elements = {};
const getElement = id => (elements[id] ||= new Element());
const sandbox = {document:{getElementById:getElement, createElement:() => new Element()}, sessionStorage:{getItem:() => null}, fetch:async () => ({ok:false}), setTimeout, clearTimeout, JSON, Math, Object, Array, Number, isFinite};
sandbox.globalThis = sandbox; sandbox.localStorage = {getItem:() => null, setItem(){}};
vm.runInNewContext(fs.readFileSync('web/minimap.js', 'utf8'), sandbox);
const {solveH, applyH, invert, landmarks, pitchLines} = sandbox.__reviewHooks.minimapMath;

// a known perspective camera: pitch metres -> normalized image
const P = [[0.0105, 0.0021, 0.52], [0.0008, -0.0140, 0.62], [0.00006, 0.0019, 1]];
const project = (X, Y) => { const w = P[2][0]*X + P[2][1]*Y + P[2][2]; return [(P[0][0]*X + P[0][1]*Y + P[0][2])/w, (P[1][0]*X + P[1][1]*Y + P[1][2])/w]; };
const dims = {length:90, width:55, circle_r:9.15, goal_width:7.32, pa_depth:16.5, pa_width:40.3, ga_depth:5.5, ga_width:18.3};
const lm = landmarks(dims);
assert.equal(lm.length, 31);
const pairs = lm.filter(l => ['center','circle_left','circle_right','half_far','half_near','corner_l_far','corner_r_far','corner_l_near'].includes(l.id))
  .map(l => { const [u, v] = project(l.X, l.Y); return {u, v, X:l.X, Y:l.Y}; });
const H = solveH(pairs);
for (const q of lm) { const [u, v] = project(q.X, q.Y), r = applyH(H, u, v); assert.ok(Math.hypot(r[0] - q.X, r[1] - q.Y) < 1e-4, q.id); }
const inv = invert(H), back = applyH(inv, 10, -5);  // pitch metres -> image
assert.ok(Math.hypot(back[0] - project(10, -5)[0], back[1] - project(10, -5)[1]) < 1e-6);
assert.ok(pitchLines(dims).length >= 9);
assert.equal(solveH(pairs.slice(0, 3).concat(pairs.slice(0, 1))), null, 'degenerate points must not give a homography');
console.log('minimap math passed');

// length and width can be recovered from the clicks when the pitch is not the assumed standard size
{
  const hooks = sandbox.__reviewHooks.minimapMath;
  const real = {...dims, length:100, width:64};
  const ids = ['center','circle_left','circle_right','circle_near','circle_far','half_far','half_near','pa_l_near','pa_r_near','corner_l_far','corner_r_far'];
  const byId = Object.fromEntries(landmarks(real).map(l => [l.id, l]));
  const points = ids.map(id => { const [x, y] = project(byId[id].X, byId[id].Y); return {landmark:id, x, y}; });
  hooks.setPoints(points, {length:105, width:68});
  hooks.estimateSize();
  const f = hooks.fit({...dims, length:100, width:64});
  assert.ok(f.rms < 1e-3, 'the true size fits the synthetic clicks');
  assert.match(elements['minimap-status'].textContent, /길이 100m, 폭 64m/);
  hooks.setPoints(points.slice(0, 5), {});
  hooks.estimateSize();
  assert.match(elements['minimap-status'].textContent, /7개 이상/);
}
console.log('size estimate passed');

// a camera whose horizon crosses the image: the scale factor w of the fitted mapping must still come out positive
{
  const hooks = sandbox.__reviewHooks.minimapMath;
  const Hreal = [-19.6486, 2.9627, 8.0653, -1.3896, -73.3724, 56.8509, -0.0347, -1.5016, 1];   // image -> metres, made up like a real wide shot
  const inv = invert(Hreal), d = {...dims, length:89, width:62};
  const ids = ['half_near','half_far','circle_left','circle_right','circle_near','circle_far','corner_l_far','corner_r_far','post_l_near','post_r_far'];
  const byId = Object.fromEntries(landmarks(d).map(l => [l.id, l]));
  const clicks = ids.map(id => { const r = applyH(inv, byId[id].X, byId[id].Y); return {landmark:id, x:r[0], y:r[1]}; });
  hooks.setPoints(clicks, d);
  const f = hooks.fit(d);
  assert.ok(f && f.rms < 1e-3, 'the synthetic clicks fit');
  for (const c of clicks) assert.ok(applyH(f.H, c.x, c.y)[2] > 0, 'w is positive for every clicked point');
  const back = applyH(invert(f.H), 10, 5);
  assert.ok(back[2] > 0, 'the pitch lines can be drawn back into the image');
}
console.log('horizon sign passed');
