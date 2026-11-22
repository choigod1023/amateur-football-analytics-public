from fastapi.testclient import TestClient

from app.review_public import create_app

HEADERS = {'Origin': 'http://example.test'}
QUERY = '?camera=cam3&team=B&direction=1&start=0&end=60&half_name=test&name=match.mp4'


def client_for(tmp_path):
    return TestClient(create_app(tmp_path, 'http://example.test'), base_url='http://example.test')


def test_report_upload_needs_the_token_and_serves_only_listed_outputs(tmp_path, monkeypatch):
    import app.report_jobs as jobs
    monkeypatch.setenv('FOOTBALL_REPORT_TOKEN', 'x' * 40)
    monkeypatch.setattr(jobs.ReportJobs, 'start_worker', lambda self: None)
    client = client_for(tmp_path)
    good = {**HEADERS, 'X-Report-Token': 'x' * 40}
    assert client.post('/api/v1/report/upload' + QUERY, content=b'abc', headers=HEADERS).status_code == 403
    assert client.post('/api/v1/report/upload' + QUERY, content=b'abc', headers={**HEADERS, 'X-Report-Token': 'wrong'}).status_code == 403
    assert client.post('/api/v1/report/upload?camera=cam3&team=C&direction=1&end=60&name=match.mp4', content=b'abc', headers=good).status_code == 422
    assert client.post('/api/v1/report/upload' + QUERY.replace('match.mp4', 'match.exe'), content=b'abc', headers=good).status_code == 422
    ok = client.post('/api/v1/report/upload' + QUERY, content=b'abc', headers=good)
    assert ok.status_code == 200
    job = ok.json()['job']
    listing = client.post('/api/v1/report/list', headers=HEADERS).json()
    assert listing['upload_enabled'] and listing['jobs'][0]['id'] == job and listing['jobs'][0]['status']['state'] == 'queued'
    assert (tmp_path / 'reports' / job / 'upload.mp4').read_bytes() == b'abc'
    assert client.get(f'/report-files/{job}/report.mp4').status_code == 404
    assert client.get(f'/report-files/{job}/upload.mp4').status_code == 404          # the upload itself is never served
    (tmp_path / 'reports' / job / 'report.md').write_text('hi', encoding='utf-8')
    assert client.get(f'/report-files/{job}/report.md').text == 'hi'
    assert client.get('/report-files/..%2F..%2Fx/report.md').status_code == 404
    assert client.get('/report').status_code == 200


def test_report_upload_is_off_without_a_token(tmp_path, monkeypatch):
    monkeypatch.delenv('FOOTBALL_REPORT_TOKEN', raising=False)
    client = client_for(tmp_path)
    assert client.post('/api/v1/report/upload' + QUERY, content=b'abc', headers={**HEADERS, 'X-Report-Token': ''}).status_code == 403
    assert client.post('/api/v1/report/list', headers=HEADERS).json()['upload_enabled'] is False
