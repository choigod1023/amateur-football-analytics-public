import app.main as main


def test_live_stall_is_reported_before_stream_error(monkeypatch):
    monkeypatch.setattr(main, 'status', {'status': 'running', 'source': 'rtsp://127.0.0.1:1234/test',
                                      'fps': 2, 'latency_ms': 400, 'message': 'Processing'})
    monkeypatch.setattr(main, 'live_input', {'last_decoded_monotonic': 10.0})
    monkeypatch.setattr(main.time, 'monotonic', lambda: 14.0)
    state = main.get_status()
    assert state['status'] == 'running'
    assert state['input_stalled'] is True
    assert state['decoded_frame_age_ms'] == 4000
    assert '입력 지연' in state['message']
    assert main.status['message'] == 'Processing'  # GET must not mutate state


def test_fresh_live_file_and_error_do_not_inherit_stall(monkeypatch):
    monkeypatch.setattr(main, 'status', {'status': 'running', 'source': 'rtsp://127.0.0.1:1234/test',
                                      'fps': None, 'latency_ms': None, 'message': 'Starting'})
    monkeypatch.setattr(main, 'live_input', {'last_decoded_monotonic': None})
    monkeypatch.setattr(main.time, 'monotonic', lambda: 14.0)
    assert main.get_status()['input_stalled'] is False
    main.live_input['last_decoded_monotonic'] = 13.0
    assert main.get_status()['decoded_frame_age_ms'] == 1000
    assert main.get_status()['input_stalled'] is False
    main.status['source'] = 'recorded.mp4'
    assert main.get_status()['decoded_frame_age_ms'] is None
    main.status.update(source='rtsp://127.0.0.1:1234/test', status='error', message='Stream disconnected')
    state = main.get_status()
    assert state['message'] == 'Stream disconnected' and state['input_stalled'] is False
