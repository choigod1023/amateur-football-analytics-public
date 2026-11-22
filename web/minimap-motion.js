/* Display-only interpolation. Raw coordinates always remain the analysis truth. */
(function(root) {
  class MinimapMotion {
    constructor({length=89,width=60}={}) {
      this.length=length; this.width=width; this.reset();
    }
    velocity(samples) {
      if(samples.length<3) return null;
      const speeds=samples.slice(1).map((p,i)=>{
        const a=samples[i],dt=(p.t-a.t)/1000;
        return {x:(p.x-a.x)/dt,y:(p.y-a.y)/dt};
      });
      const metres=v=>Math.hypot(v.x*this.length,v.y*this.width);
      if(speeds.some(v=>!Number.isFinite(metres(v)) || metres(v)>12)) return null;
      const a=speeds[0],b=speeds[1];
      if(metres({x:a.x-b.x,y:a.y-b.y})>4) return null;
      return {x:(a.x+b.x)/2,y:(a.y+b.y)/2};
    }
    forecast(row,now) {
      const age=Math.max(0,(now-row.seen)/1000);
      const v=row.velocity;
      if(!v) return {...row.target,display_kind:'last_seen',age_s:age};
      // Damped constant velocity, maximum 0.8 seconds. Not an observation.
      const dt=0.6*(1-Math.exp(-age/0.6));
      const x=row.target.x+v.x*dt,y=row.target.y+v.y*dt;
      if(x<0 || x>1 || y<0 || y>1) return {...row.target,display_kind:'last_seen',age_s:age};
      return {...row.target,x,y,display_kind:'predicted',age_s:age,
        uncertainty_m:0.5+3*age,display_opacity:Math.max(.3,1-age/.9)};
    }
    reset() { this.rows=[]; this.time=null; this.generation=null; this.start=0; this.duration=0; }
    hasData() { return this.rows.length > 0; }
    active(now) { return (this.duration > 0 && now < this.start + this.duration) || this.rows.some(r=>r.expires > now); }
    push(players, sampleTime, now, generation, allowHold = true, blockedIds = []) {
      if (sampleTime === this.time && generation === this.generation) return;
      const previous = new Map(this.at(now).map(p=>[p.id,p]));
      const gap = sampleTime - this.time;
      const continuous = this.time !== null && Number.isFinite(sampleTime) &&
        generation === this.generation && gap > 0 && gap <= 600;
      this.duration = continuous ? Math.min(200,gap) : 0;
      const oldRows = this.rows;
      const history = new Map(oldRows.map(r=>[r.target.id,r]));
      this.rows = players.map(p=>{
        const old = previous.get(p.id);
        const interpolate = continuous && old && old.team === p.team &&
          Math.hypot(old.x-p.x,old.y-p.y) <= 0.04;
        const prior = history.get(p.id);
        const stable = continuous && prior && prior.target.team === p.team &&
          !prior.expires && Math.hypot(prior.target.x-p.x,prior.target.y-p.y)<=0.04;
        const samples=stable ? [...(prior.samples || []),{x:p.x,y:p.y,t:sampleTime}].slice(-3) : [{x:p.x,y:p.y,t:sampleTime}];
        return {target:{...p}, from:interpolate ? old : {...p}, seen:now,
          samples,velocity:this.velocity(samples),streak:stable ? (prior.streak || 1)+1 : 1};
      });
      // Hollow points are bounded predictions or last-seen locations.
      // Never feed them to tactical metrics or renew age on missing updates.
      if (allowHold && continuous) {
        const ids = new Set([...players.map(p=>p.id), ...blockedIds]);
        const counts = {home:players.filter(p=>p.team==='home').length, away:players.filter(p=>p.team==='away').length};
        for (const row of oldRows) {
          const p=row.target, expires=row.seen+(row.streak>=3 ? 800 : 400);
          if (ids.has(p.id) || !(p.team in counts) || expires <= now || counts[p.team]>=11 || this.rows.length>=22) continue;
          // A nearby current detection may be the same person with a new ID.
          if (players.some(q=>Math.hypot(q.x-p.x,q.y-p.y)<0.025)) continue;
          this.rows.push({...row,target:{...p,display_kind:'last_seen'},from:{...p},expires});
          counts[p.team]++;
        }
      }
      this.time=sampleTime; this.generation=generation; this.start=now;
    }
    at(now) {
      const fraction=this.duration ? Math.max(0,Math.min(1,(now-this.start)/this.duration)) : 1;
      const observed=this.rows.filter(r=>!r.expires).map(({target,from})=>({...target,
        x:from.x+(target.x-from.x)*fraction,y:from.y+(target.y-from.y)*fraction}));
      const result=[...observed];
      for(const row of this.rows.filter(r=>r.expires && now<r.expires)) {
        const p=this.forecast(row,now);
        // Suppress collisions against both observed and already-added predictions.
        if(result.some(q=>Math.hypot(q.x-p.x,q.y-p.y)<.025)) continue;
        result.push(p);
      }
      return result;
    }
  }
  if (typeof module !== 'undefined' && module.exports) module.exports=MinimapMotion;
  else root.MinimapMotion=MinimapMotion;
})(typeof window !== 'undefined' ? window : globalThis);
