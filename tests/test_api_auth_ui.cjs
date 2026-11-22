const assert=require('node:assert/strict'), fs=require('node:fs'), vm=require('node:vm');
const script=fs.readFileSync('web/api-auth.js','utf8');
async function run(href){
 const ids=['access-form','access-token','access-clear','access-message','proxy-controls-upload','proxy-controls-sequence','proxy-controls-note','sequence-refresh','upload-warning'];
 const e=Object.fromEntries(ids.map(id=>[id,{value:'',listeners:{},addEventListener(n,f){this.listeners[n]=f}}]));
 const location=new URL(href), calls=[];
 const native=async (input,opts={})=>{calls.push({input,opts});return {ok:true,json:async()=>({manual_enabled:true,controls_enabled:false})}};
 const window={fetch:native}; const context={window,document:{getElementById:id=>e[id]},location,URL,Headers,AbortSignal};
 vm.runInNewContext(script,context);
 await window.fetch('/api/v1/status');assert.equal(calls[0].opts.headers,undefined);
 e['access-token'].value='x'.repeat(32);await e['access-form'].listeners.submit({preventDefault(){}});
 assert.equal(e['access-token'].value,'');
 if(location.hostname==='example.com' && location.protocol==='http:'){assert.equal(calls.length,1);assert.match(e['access-message'].textContent,/HTTPS/);return;}
 assert.equal(calls[1].opts.headers.get('Authorization'),'Bearer '+ 'x'.repeat(32));assert.equal(e['proxy-controls-upload'].disabled,true);
 await window.fetch('/api/v1/status');assert.equal(calls[2].opts.headers.get('authorization'),'Bearer '+ 'x'.repeat(32));assert.equal(calls[2].opts.redirect,'error');
 await window.fetch('https://elsewhere.example/api/v1/status');assert.equal(calls[3].opts.headers,undefined);
 await window.fetch('/not-api');assert.equal(calls[4].opts.headers,undefined);
 e['access-clear'].listeners.click();await window.fetch('/api/v1/status');assert.equal(calls[5].opts.headers,undefined);assert.equal(e['proxy-controls-upload'].disabled,false);
}
(async()=>{await run('https://example.com/');await run('http://localhost:8000/');await run('http://example.com/');console.log('memory-only API auth: ok')})().catch(e=>{console.error(e);process.exitCode=1});
