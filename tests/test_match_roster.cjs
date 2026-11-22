const assert=require('node:assert/strict');const R=require('../web/match-roster');
const p=(id,team='home',kind)=>({id:String(id),team,x:.2,y:.3,...(kind?{display_kind:kind}:{})});
const r=new R();const check=v=>{for(const t of ['home','away']){assert.equal(v.teams[t].length,11);const ids=v.teams[t].map(x=>x.track_id).filter(x=>x!==null);assert.equal(new Set(ids).size,ids.length);for(const s of v.teams[t])if(['unlocated','identity_uncertain'].includes(s.status))assert.equal(s.x,null);}};
let v=r.update([p(1),p(2)],[p(1),p(2)],0,'a');check(v);assert.equal(v.teams.home[0].status,'observed');
v=r.update([p(2)],[p(1,'home','predicted'),p(2)],200,'a');check(v);assert.equal(v.teams.home[0].status,'predicted');
v=r.update([p(2)],[p(2)],1000,'a');assert.equal(v.teams.home[0].track_id,'1');assert.equal(v.teams.home[0].status,'unlocated');
v=r.update([p(2),p(3)],[p(2),p(3)],1200,'a');assert.equal(v.pending.length,1);assert.equal(v.teams.home[2].track_id,null);
v=r.update([p(1),p(2)],[p(1),p(2)],1400,'a');assert.equal(v.teams.home[0].status,'observed');
v=r.update([p(1,'away'),p(2)],[p(1,'away'),p(2)],1600,'a');assert.equal(v.teams.home[0].status,'identity_uncertain');assert.ok(v.teams.away.every(s=>s.track_id===null));
v=r.update([],[],0,'b');check(v);assert.ok(v.teams.home.every(s=>s.track_id===null));
const many=Array.from({length:12},(_,i)=>p(i));v=r.update(many,many,200,'b');assert.equal(v.pending.length,12);assert.ok(v.teams.home.every(s=>s.track_id===null));
r.reset();v=r.update([p(1),p(1)],[p(1)],0,'c');assert.equal(v.pending.length,2);check(v);
console.log('11v11 slots, expiry, ambiguous replacement, team conflict and capacity passed');

r.reset();v=r.update([{...p(1),x:null}],[{...p(1),x:null}],0,'d');assert.equal(v.teams.home[0].status,'unlocated');
