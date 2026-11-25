const fs=require('fs'),vm=require('vm'),cp=require('child_process');
const context={module:{exports:{}}};vm.runInNewContext(cp.execFileSync('git',['show','88f63ad:web/minimap-motion.js'],{encoding:'utf8'}),context);
const Old=context.module.exports,New=require('../web/minimap-motion.js');
const out=process.argv[2],input=process.argv[3];
const frames=JSON.parse(fs.readFileSync(input));
const before=new Old(),after=new New(),output=[];let pending=new Map(),errors=[],metrics={predictedSamples:0,disappearBefore:0,disappearAfter:0,excessBefore:0,excessAfter:0};let prevB=new Set(),prevA=new Set();
const distance=(a,b)=>Math.hypot((a.x-b.x)*89,(a.y-b.y)*60);
for(let i=0;i<frames.length;i++){
 const f=frames[i],now=Math.round(f.time*1000),oldRows=after.rows.slice();
 // Evaluate return location before admitting this observation. Same raw ID is only a proxy.
 for(const p of f.players){const r=oldRows.find(r=>r.target.id===p.id && r.target.team===p.team && r.expires>now);if(r && r.velocity){const q=after.forecast(r,now);if(q.display_kind==='predicted')errors.push({time:f.time,id:p.id,hold:distance(r.target,p),predict:distance(q,p),age:(now-r.seen)/1000});}}
 before.push(f.players,now,now,'replay',f.ready);after.push(f.players,now,now,'replay',f.ready);
 const b=before.at(now),a=after.at(now);const bs=new Set(b.map(p=>p.id)),as=new Set(a.map(p=>p.id));
 metrics.disappearBefore += [...prevB].filter(id=>!bs.has(id)).length;metrics.disappearAfter += [...prevA].filter(id=>!as.has(id)).length;prevB=bs;prevA=as;
 metrics.excessBefore += ['home','away'].some(t=>b.filter(p=>p.team===t).length>11)?1:0;metrics.excessAfter += ['home','away'].some(t=>a.filter(p=>p.team===t).length>11)?1:0;
 metrics.predictedSamples+=a.filter(p=>p.display_kind==='predicted').length;
 for(let j=0;j<3;j++)output.push({time:f.time+j/15,before:before.at(now+j*1000/15),after:after.at(now+j*1000/15)});
}
const mean=k=>errors.length?errors.reduce((s,e)=>s+e[k],0)/errors.length:null;
metrics.returnProxy={n:errors.length,holdMeanM:mean('hold'),predictionMeanM:mean('predict'),improved:errors.filter(e=>e.predict<e.hold).length,worse:errors.filter(e=>e.predict>e.hold).length,groundTruthVerified:false};
fs.writeFileSync(out+'.json',JSON.stringify(output));fs.writeFileSync(out+'-metrics.json',JSON.stringify({metrics,errors},null,2));console.log(metrics);
