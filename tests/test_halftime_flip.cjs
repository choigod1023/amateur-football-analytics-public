// The picture's direction of /halftime maps 2, 4, 5, 6 (web/halftime.js, HalftimeFlip): run with node.
const assert = require('assert');
const F = require('../web/halftime.js');

// the direction of the half: -1 = we attack to the left of the video; no record = the fixed picture
assert.strictEqual(F.flipFor(-1), true);
assert.strictEqual(F.flipFor(1), false);
for (const none of [undefined, null, 0, 'x', NaN]) assert.strictEqual(F.flipFor(none), false);

// one point: the picture is turned by 180 degrees, twice is the identity
assert.deepStrictEqual(F.toPicture(false, 30, 10), [30, 10]);
assert.deepStrictEqual(F.toPicture(true, 30, 10), [70, 54]);
assert.deepStrictEqual(F.toPicture(true, ...F.toPicture(true, 30, 10)), [30, 10]);

// the arrow and the goal word
assert.deepStrictEqual(F.attack(false, '우리 공격'), { side: 'right', text: '우리 공격 →' });
assert.deepStrictEqual(F.attack(true, '우리 공격'), { side: 'left', text: '← 우리 공격' });
assert.strictEqual(F.goalSide(false), 'left');
assert.strictEqual(F.goalSide(true), 'right');

// the same player keeps the same code: LB is on our left (small v) and RB on our right, whatever the picture's direction.
// The lane "왼" (index 0) must be the lane that holds LB on the screen, in both directions.
const players = [{ role: 'LB', u: 20, v: -20 }, { role: 'RB', u: 20, v: 20 }, { role: 'ST', u: 60, v: 0 }];
const laneOf = v => (v < -62 / 6 ? 0 : v > 62 / 6 ? 2 : 1);                 // lane index of the server (왼 / 가운데 / 오른)
for (const flip of [false, true]) {
  const placed = players.map(p => ({ ...p, pic: F.toPicture(flip, (p.u + 44.5) / 89 * 100, (p.v + 31) / 62 * 64) }));
  const byRole = Object.fromEntries(placed.map(p => [p.role, p]));
  // order on the screen from the top: lanes follow laneOrder
  const order = F.laneOrder(flip);
  const laneTop = k => order.indexOf(k);                                     // 0 = top of the picture
  assert.ok(laneTop(laneOf(byRole.LB.v)) < laneTop(laneOf(byRole.RB.v)) === !flip, `LB above RB only when we attack to the right (flip=${flip})`);
  assert.ok((byRole.LB.pic[1] < byRole.RB.pic[1]) === !flip, 'dot positions agree with the lane order');
  // the striker is on the attacking side of the back line
  assert.ok(flip ? byRole.ST.pic[0] < byRole.LB.pic[0] : byRole.ST.pic[0] > byRole.LB.pic[0]);
}
assert.deepStrictEqual(F.laneOrder(false), [0, 1, 2]);
assert.deepStrictEqual(F.laneOrder(true), [2, 1, 0]);

// the note under map 2
assert.match(F.note(-1), /영상\(카메라\)과 같은 방향/);
assert.match(F.note(1), /영상\(카메라\)과 같은 방향/);
assert.match(F.note(undefined), /고정 방향/);
console.log('ok');
