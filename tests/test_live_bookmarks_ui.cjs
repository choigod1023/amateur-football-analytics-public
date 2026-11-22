const assert = require('node:assert/strict'), fs=require('node:fs'), vm=require('node:vm');
class Element {
  constructor(){this.children=[];this.listeners={};this.textContent='';this.hidden=false;this.disabled=false;}
  addEventListener(k,v){this.listeners[k]=v} replaceChildren(...v){this.children=v} append(...v){this.children.push(...v)}
  async emit(k){return this.listeners[k]?.()}
}
const names=['live-mark-list','live-mark-empty','live-mark-image','live-mark-detail','live-mark-feedback','live-mark-button','live-mark-message','live-mark-refresh'];
const elements=Object.fromEntries(names.map(x=>[x,new Element()]));
const item={id:'a'.repeat(32),timestamp:'2026-11-11T00:00:00Z',people:3,feedback:[]};
let saved=false;
const fetch=async(_url,options={})=> options.method==='POST' ? (saved=true,{ok:true,json:async()=>item}) : ({ok:true,json:async()=>({items:saved?[item]:[]})});
const ctx={document:{getElementById:id=>elements[id],createElement:()=>new Element()},fetch,AbortSignal,Number,Array,String};
vm.runInNewContext(fs.readFileSync('web/live-bookmarks.js','utf8'),ctx);
(async()=>{await elements['live-mark-button'].emit('click');assert.equal(elements['live-mark-list'].children.length,1);assert.equal(elements['live-mark-image'].src,`/api/v1/live-bookmarks/${item.id}/frame.jpg`);assert.match(elements['live-mark-feedback'].textContent,/결과가 없었습니다/);assert.match(elements['live-mark-detail'].textContent,/3명/); console.log('live bookmark UI: ok')})().catch(e=>{console.error(e);process.exitCode=1});
