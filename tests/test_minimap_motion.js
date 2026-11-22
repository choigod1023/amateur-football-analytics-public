const assert=require('node:assert/strict');
const Motion=require('../web/minimap-motion.js');
const p=(x,id='1',team='home')=>({id,team,x,y:.5});
const m=new Motion();
m.push([p(.2)],1000,0,'a');
assert.equal(m.at(0)[0].x,.2);
m.push([p(.22)],1200,200,'a');
assert.ok(Math.abs(m.at(300)[0].x-.21)<1e-9);
assert.equal(m.at(400)[0].x,.22);
assert.equal(m.active(400),false);
// No extrapolation after completing interpolation.
assert.equal(m.at(20000)[0].x,.22);
m.push([],1400,400,'a');
assert.equal(m.at(400)[0].display_kind,'last_seen');
assert.equal(m.at(600).length,0);
m.push([p(.3)],1600,600,'a');
assert.equal(m.at(600)[0].x,.3);
m.push([p(.7)],1800,800,'a');
assert.equal(m.at(800)[0].x,.7); // large jump: no invented connecting path
m.push([p(.71,'1','away')],2000,1000,'a');
assert.equal(m.at(1000)[0].x,.71); // team changed
m.push([p(.72,'1','away')],2200,1200,'b');
assert.equal(m.at(1200)[0].x,.72); // replay loop/new generation
m.push([p(.73,'1','away')],4000,1400,'b');
assert.equal(m.at(1400)[0].x,.73); // gap >600ms
m.push([p(.74,'1','away')],3900,1600,'b');
assert.equal(m.at(1600)[0].x,.74); // clock moves backward
m.reset(); assert.deepEqual(m.at(2000),[]);
// One missed observation remains explicitly last-seen, not an observed player.
m.push([p(.2),p(.7,'2')],1000,0,'a');
m.push([p(.71,'2')],1200,200,'a');
assert.equal(m.at(200).find(p=>p.id==='1').display_kind,'last_seen');
assert.equal(m.active(399),true);
assert.equal(m.at(400).some(p=>p.id==='1'),false);
m.push([p(.72,'2')],1400,400,'a');
assert.equal(m.at(400).length,1); // repeated updates never renew a missing ID
m.reset(); m.push([p(.2)],1000,0,'a');
m.push([p(.21,'3')],1200,200,'a');
assert.equal(m.at(200).length,1); // nearby replacement must not become two players
m.reset(); m.push([p(.2)],1000,0,'a');
m.push([p(.7,'2')],1200,200,'b');
assert.equal(m.at(200).length,1); // session change cannot carry old points
m.reset(); m.push([p(.2)],1000,0,'a');
m.push([p(.7,'2')],1200,200,'a',false);
assert.equal(m.at(200).length,1); // invalid calibration disables retention
m.reset(); m.push([p(.2)],1000,0,'a');
m.push(Array.from({length:11},(_,i)=>p(.7,String(i+2))),1200,200,'a');
assert.equal(m.at(200).length,11); // retention cannot exceed team capacity
console.log('Minimap motion edge cases passed');

// Invalid coordinates block only that ID, not unrelated players.
m.reset(); m.push([p(.2),p(.7,'2'),p(.9,'3')],1000,0,'a');
m.push([p(.71,'2')],1200,200,'a',true,['3']);
assert.equal(m.at(200).find(p=>p.id==='1').display_kind,'last_seen');
assert.equal(m.at(200).some(p=>p.id==='3'),false);
// Empty detection frame: bounded last-seen, never a new observation.
m.reset(); m.push([p(.2)],1000,0,'a');
m.push([],1200,200,'a',true);
assert.equal(m.at(200)[0].display_kind,'last_seen');
m.push([],1300,300,'a',true);
assert.equal(m.at(400).length,0);
m.reset(); m.push([p(.2)],1000,0,'a');
m.push([],1200,200,'a',false);
assert.equal(m.at(200).length,0);

// Extend only a repeatedly observed stable track; repeated misses do not renew age.
m.reset();
m.push([p(.2)],1000,0,'a');m.push([p(.201)],1200,200,'a');m.push([p(.202)],1400,400,'a');
m.push([],1600,600,'a');m.push([],1800,800,'a');
assert.equal(m.at(1000)[0].display_kind,'predicted');
assert.equal(m.at(1200).length,0);
// Duplicate source samples cannot refresh the observation age.
m.push([],1800,1000,'a');assert.equal(m.at(1200).length,0);
// Nearby replacement, even on the other team, never gets an extra retained dot.
m.reset();m.push([p(.2)],1000,0,'a');m.push([p(.201)],1200,200,'a');m.push([p(.202)],1400,400,'a');
m.push([p(.203,'2','away')],1600,600,'a');assert.equal(m.at(600).length,1);

// Constant motion is projected with damping and widening heuristic uncertainty.
m.reset();m.push([p(.2)],1000,0,'a');m.push([p(.21)],1200,200,'a');m.push([p(.22)],1400,400,'a');m.push([],1600,600,'a');
const a=m.at(600)[0], b=m.at(700)[0];
assert.equal(a.display_kind,'predicted');assert.ok(a.x>.22 && b.x>a.x);
assert.ok(b.uncertainty_m>a.uncertainty_m && b.display_opacity<a.display_opacity);
assert.ok((b.x-a.x)*89/.1<12);assert.equal(m.at(1200).length,0);
// Implausible velocity and direction reversal cannot seed a forecast.
assert.equal(m.velocity([{x:0,y:0,t:0},{x:.1,y:0,t:200},{x:.2,y:0,t:400}]),null);
assert.equal(m.velocity([{x:.2,y:0,t:0},{x:.22,y:0,t:200},{x:.2,y:0,t:400}]),null);
// Raw input objects remain untouched; all motion is presentation only.
const input=[p(.2)];m.reset();m.push(input,0,0,'a');assert.deepEqual(input,[p(.2)]);
