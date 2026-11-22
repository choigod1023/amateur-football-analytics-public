// Read-only playback of real observations through the production display class.
const fs=require('node:fs');
const Motion=require('../web/minimap-motion.js');
const rows=fs.readFileSync(process.argv[2],'utf8').trim().split(/\r?\n/).map(JSON.parse);
const motion=new Motion();
function counter(){return {previous:new Set(),seen:new Set(),disappearances:0,reappearances:0};}
function count(c,players){
  const ids=new Set(players.map(p=>p.id));
  for(const id of c.previous) if(!ids.has(id)) c.disappearances++;
  for(const id of ids) if(!c.previous.has(id)&&c.seen.has(id)) c.reappearances++;
  for(const id of ids)c.seen.add(id);
  c.previous=ids;
}
const before=counter(),after=counter();let heldSamples=0,maxHeld=0,addedOvercapacity=0;
for(const r of rows){
  const people=(r.display_players||r.players).filter(p=>p.x!==null&&p.y!==null);
  const now=r.time*1000;
  motion.push(people,now,now,'recorded-run',r.camera_ready);
  const shown=motion.at(now),held=shown.filter(p=>p.display_kind==='last_seen');
  count(before,people);count(after,shown);heldSamples+=held.length;maxHeld=Math.max(maxHeld,held.length);
  for(const team of ['home','away'])if(people.filter(p=>p.team===team).length<=11&&shown.filter(p=>p.team===team).length>11)addedOvercapacity++;
}
console.log(JSON.stringify({frames:rows.length,before:{disappearances:before.disappearances,reappearances:before.reappearances},after:{disappearances:after.disappearances,reappearances:after.reappearances},heldSamples,maxHeld,addedOvercapacity,limits:'Display-only 400ms last-location retention. No detector, ID or tactical accuracy claim.'},null,2));
