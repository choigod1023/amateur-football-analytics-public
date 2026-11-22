import json
import os
import subprocess
import sys

import pytest
from fastapi import FastAPI
from app.cors import configure_cors


@pytest.mark.parametrize('value', ['*', 'null', 'https://*.example.com',
                                  'https://example.com/path', 'https://u:p@example.com',
                                  'https://example.com,', 'http://localhost:0'])
def test_unsafe_origins_fail_closed(monkeypatch, value):
    monkeypatch.setenv('FOOTBALL_CORS_ORIGINS', value)
    with pytest.raises(ValueError):
        configure_cors(FastAPI())


SCRIPT = r'''
import json,httpx
from fastapi.testclient import TestClient
from app.main import app
from app.plaintext_demo import create_app
def upstream(request): return httpx.Response(200,json={'status':'idle'})
def check(c):
 o='https://dashboard.example'; bad='https://evil.example'
 get=c.get('/api/v1/status',headers={'Origin':o})
 reject=c.get('/api/v1/status',headers={'Origin':bad})
 pre=c.options('/api/v1/status',headers={'Origin':o,'Access-Control-Request-Method':'GET'})
 wrong=c.options('/api/v1/status',headers={'Origin':bad,'Access-Control-Request-Method':'GET'})
 forbidden=c.options('/api/v1/status',headers={'Origin':o,'Access-Control-Request-Method':'DELETE'})
 post=c.options('/api/v1/upload',headers={'Origin':o,'Access-Control-Request-Method':'POST','Access-Control-Request-Headers':'content-type'})
 auth=c.options('/api/v1/status',headers={'Origin':o,'Access-Control-Request-Method':'GET','Access-Control-Request-Headers':'authorization'})
 return {'get':get.headers.get('access-control-allow-origin'),
         'credentials':get.headers.get('access-control-allow-credentials'),
         'rejected':reject.headers.get('access-control-allow-origin'),
         'pre_status':pre.status_code,'pre_origin':pre.headers.get('access-control-allow-origin'),
         'wrong_origin':wrong.headers.get('access-control-allow-origin'),
         'forbidden_status':forbidden.status_code,'post_status':post.status_code,
         'auth_status':auth.status_code}
g=create_app('127.0.0.1',httpx.MockTransport(upstream))
out={'direct':check(TestClient(app)),
     'gateway':check(TestClient(g,client=('127.0.0.1',1234))),
     'other_ip_preflight':TestClient(g,client=('127.0.0.2',1234)).options('/api/v1/status',headers={'Origin':'https://dashboard.example','Access-Control-Request-Method':'GET'}).status_code}
print(json.dumps(out))
'''


def run_probe(origins):
    env = os.environ.copy()
    env['FOOTBALL_CORS_ORIGINS'] = origins
    p = subprocess.run([sys.executable, '-c', SCRIPT], env=env, capture_output=True, text=True, check=True)
    return json.loads(p.stdout)


def test_default_disables_cross_origin():
    result = run_probe('')
    for channel in ('direct', 'gateway'):
        assert result[channel]['get'] is None
        assert result[channel]['pre_origin'] is None
        assert result[channel]['rejected'] is None
    assert result['other_ip_preflight'] == 403


def test_explicit_origin_supports_get_and_preflight_only():
    result = run_probe('https://dashboard.example')
    for channel in ('direct', 'gateway'):
        info = result[channel]
        assert info['get'] == info['pre_origin'] == 'https://dashboard.example'
        assert info['pre_status'] == 200
        assert info['rejected'] is None and info['wrong_origin'] is None
        assert info['credentials'] is None and info['forbidden_status'] == 400
        assert info['post_status'] == 200 and info['auth_status'] == 400
    assert result['other_ip_preflight'] == 403
