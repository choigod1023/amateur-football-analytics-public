/* Eleven roster slots per team are a match assumption, not 22 measured positions. */
(function(root){
  class MatchRoster {
    constructor(){this.reset();}
    reset(){this.generation=null;this.time=null;this.slots={home:Array(11).fill(null),away:Array(11).fill(null)};}
    update(observed,shown,time,generation){
      if(generation!==this.generation || (this.time!==null && time<this.time))this.reset();
      this.generation=generation;this.time=time;
      const pending=observed.filter(p=>!['home','away'].includes(p.team)).map(p=>({...p,reason:'team_unresolved'}));
      const byId=new Map();
      for(const p of observed){if(!byId.has(p.id))byId.set(p.id,[]);byId.get(p.id).push(p);}
      for(const team of ['home','away']){
        const current=observed.filter(p=>p.team===team);
        const eligible=current.filter(p=>byId.get(p.id).length===1);
        const occupied=this.slots[team].filter(Boolean);
        // Missing old IDs and new IDs may refer to the same people. Do not guess.
        const allPresent=occupied.every(id=>eligible.some(p=>p.id===id));
        const other=team==='home'?'away':'home';
        for(const p of current){
          if(this.slots[team].includes(p.id))continue;
          const empty=this.slots[team].indexOf(null);
          if(current.length>11 || byId.get(p.id).length!==1 || this.slots[other].includes(p.id) || !allPresent || empty<0){pending.push({...p,reason:'identity_or_capacity_unresolved'});continue;}
          this.slots[team][empty]=p.id;
        }
      }
      const teams={};
      for(const team of ['home','away'])teams[team]=this.slots[team].map((id,i)=>{
        const source=id===null?[]:(byId.get(id)||[]);
        const conflict=source.length>1 || source.some(p=>p.team!==team);
        const p=!conflict && shown.find(p=>p.id===id && p.team===team && Number.isFinite(p.x) && Number.isFinite(p.y));
        return {slot:i+1,team,track_id:id,status:conflict?'identity_uncertain':p?(p.display_kind || 'observed'):'unlocated',
          x:p?p.x:null,y:p?p.y:null,identity_verified:false};
      });
      return {teams,pending,expected_per_team:11,assumption:'11v11_including_goalkeepers',identity_verified:false};
    }
  }
  if(typeof module!=='undefined' && module.exports)module.exports=MatchRoster;else root.MatchRoster=MatchRoster;
})(typeof window!=='undefined'?window:globalThis);
