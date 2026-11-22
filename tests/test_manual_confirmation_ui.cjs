const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
class Element {
  constructor(tag='div'){this.tag=tag;this.children=[];this.listeners={};this.attributes={};this.dataset={};this.style={};this.value='';this.disabled=false;this.hidden=false;this.textContent='';}
  addEventListener(n,f){this.listeners[n]=f} async emit(n,e={}){return this.listeners[n]?.(e)}
  replaceChildren(...c){this.children=c} append(...c){this.children.push(...c)} setAttribute(k,v){this.attributes[k]=v} removeAttribute(k){delete this.attributes[k]}
  set src(v){this.attributes.src=v} querySelectorAll(tag){return this.children.filter(c=>c.tag===tag)}
}
const ids=['manual-message','manual-stage','manual-image','manual-boxes','manual-list','manual-selected','manual-save','manual-role','manual-team','manual-refresh','manual-form'];
const e=Object.fromEntries(ids.map(id=>[id,new Element()]));let now=0,posts=[],conflict=false;
const frame={image_jpeg_base64:'/9j/abc=',snapshot_token:'snapshot_1',expires_in_s:10,players:[{id:'42',annotation_token:'token_42',bbox_image_norm:[.1,.2,.3,.8],suggested_color_group:0}]};
const fetch=async (url,options={})=>{if(url.endsWith('manual-snapshot'))return {ok:true,json:async()=>frame};posts.push(JSON.parse(options.body));return conflict?{status:409,ok:false}:{ok:true}};
const ctx={document:{getElementById:id=>e[id],createElement:tag=>new Element(tag)},fetch,performance:{now:()=>now},setTimeout:()=>1,clearTimeout:()=>{},AbortController,Number,Array,Map,Math,String,JSON};
vm.runInNewContext(fs.readFileSync('web/manual-confirmation.js','utf8'),ctx);
(async()=>{
 await e['manual-refresh'].emit('click');assert.equal(e['manual-image'].attributes.src,'data:image/jpeg;base64,/9j/abc=');assert.equal(e['manual-boxes'].children[0].style.left,'10%');
 assert.match(e['manual-list'].children[0].textContent,/색상 후보 A \(미확인\)/);
 await e['manual-list'].children[0].emit('click');assert.equal(e['manual-role'].value,'');assert.equal(e['manual-team'].disabled,true);
 await e['manual-form'].emit('submit',{preventDefault(){}});assert.equal(posts.length,0);
 e['manual-role'].value='player';await e['manual-role'].emit('change');await e['manual-form'].emit('submit',{preventDefault(){}});assert.equal(posts.length,0);
 e['manual-team'].value='home';await e['manual-form'].emit('submit',{preventDefault(){}});assert.deepEqual(posts[0],{snapshot_token:'snapshot_1',id:'42',token:'token_42',role:'player',team:'home'});
 conflict=true;await e['manual-form'].emit('submit',{preventDefault(){}});assert.equal(e['manual-stage'].hidden,true);assert.match(e['manual-message'].textContent,/만료/);
 conflict=false;await e['manual-refresh'].emit('click');await e['manual-list'].children[0].emit('click');e['manual-role'].value='referee';await e['manual-role'].emit('change');await e['manual-form'].emit('submit',{preventDefault(){}});assert.equal(posts[2].team,'unknown');
 now=11000;await e['manual-form'].emit('submit',{preventDefault(){}});assert.equal(posts.length,3);assert.equal(e['manual-stage'].hidden,true);
 console.log('manual confirmation UI: ok');
})().catch(e=>{console.error(e);process.exitCode=1});
