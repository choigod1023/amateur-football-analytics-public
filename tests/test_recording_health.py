import json
import pytest

from app import recording_health as health


def test_detects_growth_rotation_and_low_space():
    before = {'sizes': {'old.mp4': 10, 'gone.mp4': 2}, 'free_bytes': 100}
    after = {'sizes': {'old.mp4': 15, 'new.mp4': 4, 'empty.mp4': 0}, 'free_bytes': 20}
    result = health.summarize(before, after, low_space_bytes=30)
    assert result['growth_observed']
    assert result['growing_files'] == ['new.mp4', 'old.mp4']
    assert result['new_empty_files'] == ['empty.mp4']
    assert result['missing_files'] == ['gone.mp4']
    assert result['low_space'] and result['total_recording_bytes'] == 19


def test_unchanged_is_not_claimed_to_be_stopped():
    measurement = {'sizes': {'video.mp4': 10}, 'free_bytes': 100}
    result = health.summarize(measurement, measurement, low_space_bytes=30)
    assert not result['growth_observed']
    assert 'does not prove' in result['note']


def test_cli_observes_only_mp4_without_writing(tmp_path, monkeypatch, capsys):
    (tmp_path / 'match.mp4').write_bytes(b'video')
    (tmp_path / 'unrelated.txt').write_bytes(b'data')
    monkeypatch.setattr(health.time, 'sleep', lambda _: None)
    health.main(['--directory', str(tmp_path), '--sample-seconds', '1'])
    result = json.loads(capsys.readouterr().out)
    assert result['recording_file_count'] == 1
    assert result['total_recording_bytes'] == 5
    assert (tmp_path / 'match.mp4').read_bytes() == b'video'
    assert (tmp_path / 'unrelated.txt').read_bytes() == b'data'


def test_missing_directory_and_invalid_interval(tmp_path):
    with pytest.raises(ValueError):
        health.measure(tmp_path / 'missing')
    with pytest.raises(SystemExit):
        health.main(['--directory', str(tmp_path), '--sample-seconds', '0'])
