import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import stream_health as sh  # noqa: E402


def numbers(**over):
    base = {'media_end_s': 100.0, 'window_s': 10.0, 'packets': 300, 'bitrate_kbps': 8000, 'lowest_second_kbps': 7500, 'fps': 30.0, 'key_interval_s': 1.0,
            'key_interval_max_s': 1.0, 'key_frames_seen': 10, 'gap_count': 0, 'longest_gap_s': 0.04}
    base.update(over)
    return base


def measure(height=1080, decode=None, age=1.0, **over):
    return {'file': 'a.mp4', 'seconds_since_data': age, 'width': height * 16 // 9, 'height': height, 'numbers': numbers(**over), 'decode': decode if decode is not None else {'errors': 0, 'frames': 150}}


def level(m):
    return sh.judge(m)['level']


def test_no_file_is_gray_waiting():
    verdict = sh.judge({'file': None})
    assert verdict['level'] == 'gray' and '송출' in verdict['headline']


def test_1080p_bitrate_limits_follow_the_computer_test():
    assert level(measure(1080, bitrate_kbps=8000)) == 'green'
    assert level(measure(1080, bitrate_kbps=4000, lowest_second_kbps=4000)) == 'green'
    assert level(measure(1080, bitrate_kbps=3000, lowest_second_kbps=3000)) == 'yellow'
    assert level(measure(1080, bitrate_kbps=1500, lowest_second_kbps=1500)) == 'red'


def test_720p_at_2000_is_fine_and_500_is_never_usable():
    assert level(measure(720, bitrate_kbps=2000, lowest_second_kbps=2000)) == 'green'
    assert level(measure(720, bitrate_kbps=1200, lowest_second_kbps=1200)) == 'yellow'
    assert level(measure(720, bitrate_kbps=500, lowest_second_kbps=500)) == 'red'
    assert level(measure(1080, bitrate_kbps=500, lowest_second_kbps=500)) == 'red'


def test_low_resolution_is_never_green():
    assert level(measure(360, bitrate_kbps=3000, lowest_second_kbps=3000)) == 'yellow'


def test_a_dip_below_the_red_limit_turns_a_good_average_yellow():
    verdict = sh.judge(measure(1080, bitrate_kbps=6000, lowest_second_kbps=1500))
    assert verdict['level'] == 'yellow' and '순간적으로' in verdict['items'][0]['message']


def test_gaps_and_frame_rate_and_key_frames():
    assert level(measure(longest_gap_s=1.4, gap_count=1)) == 'red'
    assert level(measure(longest_gap_s=0.3, gap_count=2)) == 'yellow'
    assert level(measure(fps=20.0)) == 'yellow'
    assert level(measure(fps=10.0)) == 'red'
    assert level(measure(key_interval_s=4.0)) == 'yellow'


def test_decoder_errors_make_it_yellow_not_red():
    assert level(measure(decode={'errors': 3, 'frames': 100})) == 'yellow'


def test_stalled_data_is_red_after_15_seconds_and_names_the_seconds():
    verdict = sh.judge(measure(age=20.0))
    assert verdict['level'] == 'red' and '20초' in verdict['headline']
    assert sh.judge(measure(age=7.0))['level'] == 'yellow'


def test_coach_text_has_no_developer_words():
    verdicts = [sh.judge(measure(1080, bitrate_kbps=1500, lowest_second_kbps=1500, fps=20.0, key_interval_s=4.0, longest_gap_s=2.0, gap_count=3, decode={'errors': 2, 'frames': 9}))]
    text = json.dumps(verdicts, ensure_ascii=False)
    for word in ('ffprobe', 'ffmpeg', 'pts', 'packet', 'kbps', '퍼센트', '%'):
        assert word not in text


def test_summarize_packets_computes_bitrate_fps_key_interval_and_gaps():
    packets = []
    for i in range(300):                      # 10 s at 30 fps, 10000 bytes each (2.4 Mbit/s), a key frame every second, one 0.5 s hole
        t = i / 30 + (0.5 if i >= 150 else 0)
        packets.append((t, 10000, i % 30 == 0))
    s = sh.summarize_packets(packets, 20.0)
    assert s['gap_count'] == 1 and s['longest_gap_s'] > 0.5
    assert 2200 <= s['bitrate_kbps'] <= 2400 and 27 <= s['fps'] <= 29      # 299 packets over 10.5 s including the hole
    assert s['key_interval_s'] == pytest.approx(1.0, abs=0.05)
    assert sh.summarize_packets(packets[:1], 10) is None


def test_newest_recording_picks_latest_and_ignores_other_files(tmp_path):
    old, new = tmp_path / 'a.mp4', tmp_path / 'b.mp4'
    old.write_bytes(b'x'); new.write_bytes(b'y'); (tmp_path / 'c.txt').write_bytes(b'z')
    os.utime(old, (1000, 1000)); os.utime(new, (2000, 2000)); os.utime(tmp_path / 'c.txt', (3000, 3000))
    assert sh.newest_recording(tmp_path) == new
    assert sh.newest_recording(tmp_path / 'missing') is None


def test_monitor_without_recordings_says_waiting(tmp_path):
    monitor = sh.StreamHealthMonitor(tmp_path, ffprobe='unused')
    assert monitor.once()['level'] == 'gray'


def test_web_app_serves_page_and_cached_json(tmp_path):
    from fastapi.testclient import TestClient
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
    import run_stream_health
    app = run_stream_health.build_app(tmp_path, start=False)
    app.state.monitor.once()
    client = TestClient(app)
    assert client.get('/api/stream-health').json()['level'] == 'gray'
    page = client.get('/stream')
    assert page.status_code == 200 and '송출 상태' in page.text
    assert client.post('/api/stream-health').status_code == 405


FFMPEG = next(iter(sorted((Path(__file__).resolve().parents[3] / 'work' / 'ffmpeg-local').glob('*/bin/ffmpeg.exe'))), None)


@pytest.mark.skipif(FFMPEG is None, reason='ffmpeg not found')
def test_measure_a_real_file_and_never_modify_it(tmp_path):
    path = tmp_path / 'sample.mp4'
    subprocess.run([str(FFMPEG), '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=1280x720:rate=30', '-t', '25', '-c:v', 'libx264', '-b:v', '2000k', '-maxrate', '2000k', '-bufsize', '4000k',
                    '-g', '30', '-bf', '0', '-pix_fmt', 'yuv420p', str(path)], check=True)
    before = (path.stat().st_size, path.stat().st_mtime_ns)
    result = sh.measure_stream(FFMPEG.with_name('ffprobe.exe'), path, now=path.stat().st_mtime + 1)
    assert (path.stat().st_size, path.stat().st_mtime_ns) == before
    assert result['height'] == 720 and result['numbers']['fps'] == pytest.approx(30, abs=1)
    assert result['numbers']['key_interval_s'] == pytest.approx(1.0, abs=0.05)
    assert result['decode']['errors'] == 0 and result['decode']['frames'] > 50
