import hashlib
import os
import pytest
from fastapi.testclient import TestClient
from app.transfer_once import create_app, validate_target


def headers(data):
    return {'content-type':'application/octet-stream', 'x-content-sha256':hashlib.sha256(data).hexdigest()}


def test_success_is_single_use_and_no_overwrite(tmp_path):
    stopped=[]
    app=create_app(tmp_path, 'migration.zip', '127.0.0.1', max_bytes=64, on_complete=lambda:stopped.append(True))
    client=TestClient(app,client=('127.0.0.1', 9000))
    data=b'archive bytes'
    assert client.post('/upload',content=data,headers=headers(data)).json()['stored'] is True
    assert (tmp_path/'migration.zip').read_bytes()==data
    assert stopped==[True]
    assert client.post('/upload',content=b'new',headers=headers(b'new')).status_code==409
    assert (tmp_path/'migration.zip').read_bytes()==data
    assert client.get('/api/v1/status').status_code==404


def test_rejects_bad_peer_hash_size_and_preserves_existing(tmp_path):
    app=create_app(tmp_path,'migration.zip','127.0.0.1',max_bytes=10)
    wrong=TestClient(app,client=('127.0.0.2',9000))
    assert wrong.post('/upload',content=b'a',headers={**headers(b'a'),'x-forwarded-for':'127.0.0.1'}).status_code==403
    c=TestClient(app,client=('127.0.0.1',9000))
    assert c.post('/upload',content=b'a',headers=headers(b'b')).status_code==422
    assert not list(tmp_path.iterdir())
    assert c.post('/upload',content=b'x'*11,headers=headers(b'x'*11)).status_code==413
    (tmp_path/'migration.zip').write_bytes(b'existing')
    assert c.post('/upload',content=b'a',headers=headers(b'a')).status_code==409
    assert (tmp_path/'migration.zip').read_bytes()==b'existing'


@pytest.mark.parametrize('name',['../escape.zip','/escape.zip','a/b.zip','CON.zip','.hidden.zip','C:evil.zip','file.'])
def test_invalid_filename(tmp_path,name):
    with pytest.raises(ValueError): validate_target(tmp_path,name)


def test_parent_symlink_not_followed(tmp_path):
    original=tmp_path/'real'; original.mkdir()
    link=tmp_path/'link'
    try: link.symlink_to(original, target_is_directory=True)
    except OSError: pytest.skip('Creating symlinks is unavailable')
    with pytest.raises(ValueError): validate_target(link,'file.zip')
