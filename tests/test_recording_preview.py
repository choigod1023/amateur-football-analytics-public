import json
from fastapi.testclient import TestClient
from scripts.preview_recording import create_preview


def test_readonly_preview_time_range_and_assets(tmp_path):
    trace=tmp_path/'trace.jsonl'
    trace.write_text('\n'.join(json.dumps({'time':t,'raw_positions':{'home':[],'away':[]}}) for t in (0,.2,.4)),encoding='utf-8')
    video=tmp_path/'clip.mp4';video.write_bytes(b'0123456789')
    client=TestClient(create_preview(video,trace))
    html=client.get('/').text
    assert 'preview-recording.js' in html and 'live-video.js' not in html
    assert client.get('/api/v1/analysis?t=0.19').json()['source_time_s']==0
    assert client.get('/api/v1/analysis?t=-1').status_code==422
    assert client.get('/api/v1/analysis?t=nan').status_code==422
    assert client.post('/api/v1/live').status_code==405
    response=client.get('/recording.mp4',headers={'Range':'bytes=0-3'})
    assert response.status_code==206 and response.content==b'0123'
