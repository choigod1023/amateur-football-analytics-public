const assert=require('assert'), vm=require('vm'),fs=require('fs');
const elements={};
function element(id){return elements[id] ||= {id, value:'',disabled:false,hidden:false,style:{},listeners:{},children:[],width:280,height:220,naturalWidth:100,naturalHeight:100,textContent:'',replaceChildren(){this.children=[]},append(x){this.children.push(x)},addEventListener(n,fn){this.listeners[n]=fn},getContext(){return {clearRect(){},drawImage(){}}},set src(v){this._src=v;if(this.onload)this.onload()},get src(){return this._src}}}
const memory={};const sessionStorage={getItem(k){return memory[k]??null},setItem(k,v){memory[k]=v},removeItem(k){delete memory[k]}};
let writes=[];
const sample={token:'a'.repeat(32),image:'abc',people:[{id:'2',bbox:[.1,.1,.2,.4],suggested_color_group:0},{id:'1',bbox:[.4,.2,.5,.6],suggested_color_group:null}]};
const fetch=async (url,opts)=>{if(url.endsWith('/training-labels'))writes.push(JSON.parse(opts.body));return {ok:true,json:async()=>sample}};
const ctx={document:{getElementById:element,createElement:()=>element('created'+Math.random())},sessionStorage,fetch,console,JSON,Set};vm.runInNewContext(fs.readFileSync('web/training-label.js','utf8'),ctx);
const tick=()=>new Promise(r=>setImmediate(r));
(async()=>{await tick();await tick();assert.match(element('label-selected').textContent,/ID 1/);assert.equal(element('label-role').value,'');assert.equal(writes.length,0);element('label-skip').listeners.click();assert.match(element('label-selected').textContent,/ID 2/);element('label-role').value='referee';await element('label-form').listeners.submit({preventDefault(){}});assert.equal(writes.length,1);assert.equal(writes[0].track_id,'2');assert.match(element('label-selected').textContent,/마쳤습니다/);assert.equal(writes[0].team_group,'unknown');console.log('one-person crop question, skip and explicit save passed')})().catch(e=>{console.error(e);process.exitCode=1});
