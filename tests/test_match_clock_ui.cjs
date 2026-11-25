// The words of the match clock (web/match-clock.js): five states, seconds counted up from the server time.
const assert = require('node:assert/strict');
const { text, gate } = require('../web/match-clock.js');
assert.equal(text(null, 100), '경기 전');
assert.equal(text({ state: 'before', since: null }, 100), '경기 전');
assert.equal(text({ state: 'h1', since: 1000 }, 1754), '전반 12:34');
assert.equal(text({ state: 'h1', since: 1000 }, 1000), '전반 00:00');
assert.equal(text({ state: 'h1', since: 1000 }, 999), '전반 00:00');          // a clock a little ahead never shows minus
assert.equal(text({ state: 'h1', since: 1000 }, 1000 + 23 * 60 + 80), '전반 24:20');   // no length of a half is built in: it just goes on
assert.equal(text({ state: 'h1', since: 1000 }, 1000 + 70 * 60), '전반 70:00');
assert.equal(text({ state: 'break', since: null }, 5000), '하프타임');
assert.equal(text({ state: 'h2', since: 5000 }, 5190), '후반 03:10');
assert.equal(text({ state: 'over', since: null }, 9000), '경기 끝');
assert.equal(text({ state: 'h1', since: null }, 9000), '경기 전');               // a damaged answer
// Alerts: nothing before the first half, from the half's start only the alerts written after it (age_s is seconds since the server first saw the alert).
const snap = { session: 's', current: { number: 5, age_s: 20 }, recent: [{ number: 4, age_s: 400 }, { number: 3, age_s: 900 }] };
const before = gate({ state: 'before', since: null }, 1000, snap);
assert.equal(before.current, null); assert.deepEqual(before.recent, []); assert.match(before.quiet, /^경기 전입니다\. 알림은 전반 시작 뒤부터/);
assert.equal(gate({ state: 'break', since: null }, 1000, snap).current, null);
assert.equal(gate({ state: 'over', since: null }, 1000, snap).current, null);
const early = gate({ state: 'h1', since: 970 }, 1000, snap);                        // the half started 30 s ago: the alert of 20 s ago is after it
assert.equal(early.current.number, 5); assert.deepEqual(early.recent, []); assert.equal(early.quiet, null);
const late = gate({ state: 'h1', since: 990 }, 1000, snap);                         // the half started 10 s ago: the alert of 20 s ago is from the warm-up
assert.equal(late.current, null); assert.deepEqual(late.recent, []);
const mixed = gate({ state: 'h2', since: 500 }, 1000, snap);                        // 500 s into the half: the alerts of 20 s and 400 s ago count, 900 s ago does not
assert.deepEqual([mixed.current.number, mixed.recent.map(a => a.number)], [5, [4]]);
assert.equal(gate(null, 1000, snap), snap); assert.equal(gate({ state: 'h1', since: 1 }, 1000, null), null);
console.log('ok');
