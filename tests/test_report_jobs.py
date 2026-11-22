import json
import sys

import pytest
from fastapi.testclient import TestClient

import app.report_jobs as jobs
from app.report_jobs import ReportJobs
from app.review_public import create_app

OPTIONS = {'camera': 'cam3', 'team': 'B', 'direction': 1, 'start': 0, 'end': 600, 'half_name': '전반', 'title': '  시험   경기 '}
HEADERS = {'Origin': 'http://example.test', 'X-Report-Token': 'k' * 40}


def make(tmp_path, **kwargs):
    manager = ReportJobs(tmp_path, token='k' * 40, **kwargs)
    manager.start_worker = lambda: None                      # no background thread in these tests
    return manager


def add(manager, name='a.mp4', **override):
    job_id, target = manager.new_job({**OPTIONS, **override}, name)
    target.write_bytes(b'video')
    manager.queue(job_id)
    return job_id


def status(manager, job_id):
    return json.loads((manager.root / job_id / 'status.json').read_text(encoding='utf-8'))


def test_options_are_checked_and_goals_must_lie_inside_the_range(tmp_path):
    manager = make(tmp_path)
    good = manager.validate({**OPTIONS, 'goals': '300, 450 500'})
    assert good['goals'] == [300.0, 450.0, 500.0] and good['title'] == '시험 경기'
    for bad in ({'goals': '700'}, {'goals': ','.join(['1'] * 13)}, {'team': 'C'}, {'direction': 2}, {'end': 0}, {'camera': '../x'}):
        with pytest.raises(ValueError):
            manager.validate({**OPTIONS, **bad})
    with pytest.raises(ValueError):
        manager.new_job(OPTIONS, 'virus.exe')


def test_cancel_retry_and_delete_follow_the_state_of_the_job(tmp_path):
    manager = make(tmp_path)
    job = add(manager)
    assert status(manager, job)['state'] == 'queued' and manager.retry(job) is False and manager.delete(job) is True
    job = add(manager)
    assert manager.cancel(job) is True and status(manager, job)['state'] == 'cancelled'
    assert manager.cancel(job) is False                                                   # nothing left to cancel
    (manager.root / job / 'report.mp4').write_bytes(b'old')
    assert manager.retry(job) is True and status(manager, job)['state'] == 'queued' and not (manager.root / job / 'report.mp4').exists()
    manager._set_status(manager.root / job, 'running', 'detect', 10)
    assert manager.delete(job) is False                                                   # a running job stays
    with pytest.raises(ValueError):
        manager.cancel('r000000000000')


def test_a_restart_puts_running_jobs_back_in_the_queue_and_fails_broken_uploads(tmp_path):
    manager = make(tmp_path)
    running, uploading = add(manager), add(manager)
    manager._set_status(manager.root / running, 'running', 'detect', 40)
    manager._set_status(manager.root / uploading, 'uploading', 'upload', 10)
    manager.recover()
    assert status(manager, running)['state'] == 'queued' and '다시 시작' in status(manager, running)['message']
    assert status(manager, uploading)['state'] == 'failed'


def test_old_finished_jobs_are_pruned_but_active_ones_stay(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, 'KEEP_JOBS', 2)
    manager = make(tmp_path)
    ids = [add(manager) for _ in range(5)]
    for job in ids[:4]:
        manager._set_status(manager.root / job, 'done', 'done', 100)
    manager.prune()
    left = {p.name for p in manager.root.glob('r*')}
    assert ids[4] in left and len(left) == 3


def test_health_cameras_listing_and_log_paths(tmp_path):
    cameras = tmp_path / 'cameras.json'
    cameras.write_text(json.dumps({'cam1': {'label': '운동장 서쪽'}, 'cam3': {}}), encoding='utf-8')
    manager = make(tmp_path, cameras_file=str(cameras))
    job = add(manager, goals='10, 20')
    assert manager.cameras() == [{'id': 'cam1', 'label': '운동장 서쪽'}, {'id': 'cam3', 'label': 'cam3'}]
    health = manager.health()
    assert health['counts']['queued'] == 1 and health['upload_enabled'] and health['disk_free_gb'] > 0
    listed = manager.listing()['jobs'][0]
    assert listed['title'] == '시험 경기' and listed['goals'] == [10.0, 20.0] and listed['status']['step_name'] == '순서 대기' and listed['can_retry'] is False
    (manager.root / job / 'detect.log').write_text('error in D:\\secret\\folder\\video.mp4 failed', encoding='utf-8')
    assert 'secret' not in manager.log_tail(job, 'detect') and 'video.mp4' in manager.log_tail(job, 'detect')
    with pytest.raises(ValueError):
        manager.log_tail(job, '../../etc')


def test_the_worker_runs_one_job_and_a_failing_command_is_reported(tmp_path):
    ok = ReportJobs(tmp_path, token='k' * 40, worker_command=[sys.executable, '-c', 'import sys,json,pathlib;f=pathlib.Path(sys.argv[1]);(f/"status.json").write_text(json.dumps({"state":"done","step":"done","percent":100}));(f/"report.md").write_text("x")'])
    job_id, target = ok.new_job(OPTIONS, 'a.mp4')
    target.write_bytes(b'v')
    ok.queue(job_id)
    ok.thread.join(timeout=20)
    assert status(ok, job_id)['state'] == 'done' and (ok.root / job_id / 'report.md').exists()
    bad = ReportJobs(tmp_path / 'bad', token='k' * 40, worker_command=[sys.executable, '-c', 'import sys;sys.stderr.write("boom");sys.exit(3)'])
    (tmp_path / 'bad').mkdir()
    job_id, target = bad.new_job(OPTIONS, 'a.mp4')
    target.write_bytes(b'v')
    bad.queue(job_id)
    bad.thread.join(timeout=20)
    assert status(bad, job_id)['state'] == 'failed' and '작업기' in status(bad, job_id)['message']
    assert 'boom' in bad.log_tail(job_id, 'worker') and 'boom' not in status(bad, job_id)['message']      # the reason is kept for the administrator, not shown raw


def test_service_routes_need_the_token_for_every_change(tmp_path, monkeypatch):
    monkeypatch.setenv('FOOTBALL_REPORT_TOKEN', 'k' * 40)
    monkeypatch.setattr(ReportJobs, 'start_worker', lambda self: None)
    client = TestClient(create_app(tmp_path, 'http://example.test'), base_url='http://example.test')
    upload = client.post('/api/v1/report/upload?camera=cam3&team=B&direction=1&end=60&name=a.mp4&title=t&goals=10', content=b'abc', headers=HEADERS)
    job = upload.json()['job']
    anonymous = {'Origin': 'http://example.test'}
    for route in ('cancel', 'retry', 'delete'):
        assert client.post(f'/api/v1/report/{route}', json={'job': job}, headers=anonymous).status_code == 403
    assert client.post('/api/v1/report/log', json={'job': job, 'step': 'detect'}, headers=anonymous).status_code == 403
    assert client.post('/api/v1/report/cancel', json={'job': job}, headers=HEADERS).json() == {'done': True}
    assert client.post('/api/v1/report/retry', json={'job': job}, headers=HEADERS).json() == {'done': True}
    assert client.post('/api/v1/report/delete', json={'job': 'r000000000000'}, headers=HEADERS).status_code == 404
    assert client.post('/api/v1/report/cancel', json={'job': job, 'extra': 1}, headers=HEADERS).status_code == 422
    listing = client.post('/api/v1/report/list', headers=anonymous).json()
    assert 'health' in listing and 'cameras' in listing and listing['jobs'][0]['goals'] == [10.0]
    assert client.get('/report.css').status_code == 200 and client.get('/report').status_code == 200
    (tmp_path / 'reports' / job / 'report.mp4').write_bytes(b'0123456789')
    ranged = client.get(f'/report-files/{job}/report.mp4', headers={'Range': 'bytes=2-5'})
    assert ranged.status_code == 206 and ranged.content == b'2345'                       # the player can seek
