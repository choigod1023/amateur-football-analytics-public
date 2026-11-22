const fs=require('fs'),assert=require('node:assert/strict'),R=require('../web/match-roster');
const [observations,motion,output]=process.argv.slice(2);
const raw=JSON.parse(fs.readFileSync(observations)),frames=JSON.parse(fs.readFileSync(motion));
const roster=new R();let index=0;
for(const f of frames){
 while(index+1<raw.length && raw[index+1].time<=f.time+1e-8)index++;
 f.after=f.after.filter(p=>Number.isFinite(p.x)&&Number.isFinite(p.y));
 f.roster=roster.update(raw[index].players,f.after,raw[index].time*1000,'replay');
 for(const slots of Object.values(f.roster.teams)){
  assert.equal(slots.length,11);
  const ids=slots.filter(s=>s.track_id!==null).map(s=>s.track_id);assert.equal(new Set(ids).size,ids.length);
  for(const s of slots)if(['unlocated','identity_uncertain'].includes(s.status))assert.equal(s.x,null);
 }
}
fs.writeFileSync(output,JSON.stringify(frames));console.log('Verified '+frames.length+' frames with 22 slots and null unknown positions');
