const assert = require('node:assert/strict'), fs=require('node:fs'), vm=require('node:vm');
const script=fs.readFileSync('web/live-video.js','utf8');
async function test(href) {
  let calls=[], handlers={}, peer;
  const video={hidden:true,srcObject:null,play(){this.onplaying?.();return Promise.resolve()},pause(){}};
  const toggle={hidden:true,addEventListener(_,f){this.onclick=f}};
  const els={'video-player':video,'video-mode-toggle':toggle,'video-state':{textContent:''},'frame-preview':{hidden:false}};
  class PC {constructor(){peer=this;this.iceGatheringState='complete';this.connectionState='new'} addTransceiver(){} async createOffer(){return {sdp:'offer'}} async setLocalDescription(v){this.localDescription=v} async setRemoteDescription(){this.ontrack({streams:[{}]})} close(){this.connectionState='closed'}}
  const window={RTCPeerConnection:PC,addEventListener(n,f){handlers[n]=f}};
  const ctx={window,document:{getElementById:id=>els[id],querySelector:()=>({hidden:false})},location:new URL(href),RTCPeerConnection:PC,URL,AbortSignal,
    fetch:async (url,opts)=>{calls.push({url,opts});return {ok:true,headers:{get:()=>'/player/whep/test'},text:async()=> 'answer'}},setTimeout:()=>1,clearTimeout(){}};
  vm.runInNewContext(script,ctx); await new Promise(resolve=>setImmediate(resolve));
  if(href.includes('127.0.0.1')) {
    assert.equal(calls[0].url,'http://127.0.0.1:18889/player/whep');
    assert.equal(calls[0].opts.method,'POST'); assert.equal(window.localVideoActive,true);
    toggle.onclick();assert.equal(window.localVideoActive,false);assert.equal(video.hidden,true);
    toggle.onclick();assert.equal(window.localVideoActive,true);handlers.pagehide();assert.equal(peer.connectionState,'closed');
  } else assert.equal(calls.length,0);
}
Promise.all([test('http://127.0.0.1:18081/'),test('https://dashboard.example/')]).then(()=>console.log('local WebRTC UI and fallback toggle passed')).catch(e=>{console.error(e);process.exitCode=1});
