const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const PitchData = require('../web/pitch');
const source = fs.readFileSync(require.resolve('../web/app.js'), 'utf8');
const start = source.indexOf('function renderNoFeedback(data) {');
const end = source.indexOf('\nasync function read(kind)', start);
function element() {
  return {textContent:'', children:[], append(...rows) {this.children.push(...rows);}, replaceChildren() {this.children=[];}};
}
const box = element();
const context = vm.createContext({PitchData, $: () => box, document:{createElement:element}});
vm.runInContext(source.slice(start, end), context);
function render(data) {
  context.renderNoFeedback(data);
  const text = node => [node.textContent, ...node.children.map(text)].join(' ');
  return text(box);
}
const waiting = render({coaching_diagnostics:{state:'observing',reasons:[],warnings:['위치 오차 미검증']},calibration_status:'estimated_reference'});
assert.match(waiting, /최근 표시할 전술 알림이 없습니다/);
assert.match(waiting, /위치 오차 미검증/);
assert.match(waiting, /저장된 기준점/);
assert.doesNotMatch(waiting, /상세 보류 사유를 제공하지/);
const blocked = render({coaching_diagnostics:{state:'blocked',reasons:['team_capacity_exceeded']}});
assert.match(blocked, /11명을 초과/);
assert.doesNotMatch(blocked, /최근 표시할 전술 알림/);
assert.match(render({}), /상세 보류 사유를 제공하지/);
assert.match(render({coaching_diagnostics:{state:'observing'}}), /상세 보류 사유를 제공하지/);
const raw = '<img src=x onerror=alert(1)> 검증 필요';
assert.match(render({coaching_diagnostics:{reasons:[raw]}}), /<img src=x/); // textContent, never HTML.
console.log('coaching diagnostics rendering passed');
