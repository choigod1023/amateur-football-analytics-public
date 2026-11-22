from scripts.wait_srt_analysis import should_start


def test_start_only_when_video_ready_live_and_idle_or_error():
    assert should_start({'status': 'idle', 'input_mode': 'live'}, True)
    assert should_start({'status': 'error', 'input_mode': 'live'}, True)
    assert not should_start({'status': 'idle', 'input_mode': 'live'}, False)
    assert not should_start({'status': 'running', 'input_mode': 'live'}, True)
    assert not should_start({'status': 'idle', 'input_mode': 'file'}, True)
    assert not should_start(None, True)
