// Read-only replay adapter; production dashboard code remains unchanged.
window.localVideoActive=true;
const previewVideo=document.getElementById('video-player');
previewVideo.hidden=false; previewVideo.src='/recording.mp4'; previewVideo.loop=true;
document.querySelector('#video-box .placeholder').hidden=true;
const nativeFetch=window.fetch.bind(window);
let previewGeneration=0;
previewVideo.addEventListener('seeking',()=>{previewGeneration++;});
window.fetch=async function(input,options){
  const url=typeof input==='string'?input:'';
  if(url.includes('/api/v1/analysis')){
    const response=await nativeFetch('/api/v1/analysis?t='+previewVideo.currentTime,options);
    const value=await response.json();value.stream_generation='preview-'+previewGeneration;
    document.getElementById('preview-time').textContent='녹화 구간 '+previewVideo.currentTime.toFixed(1)+'초 / 원본 경기 '+(1950+previewVideo.currentTime).toFixed(1)+'초';
    return new Response(JSON.stringify(value),{status:response.status,headers:{'Content-Type':'application/json'}});
  }
  return nativeFetch(input,options);
};
previewVideo.play().catch(()=>{});

document.addEventListener('DOMContentLoaded',()=>{
 document.getElementById('video-info').textContent='녹화 원본 연속 재생 · 저장 관측값 5fps';
 document.getElementById('video-state').textContent='녹화 프리뷰';
});
