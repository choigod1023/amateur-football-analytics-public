import pytest

from scripts.local_playlist_sender import sender_command


def test_sender_encodes_full_resolution_with_short_gop(tmp_path):
    playlist = tmp_path / 'playlist.txt'
    playlist.write_text('file example.mp4\n')
    command = sender_command('ffmpeg', playlist, 'srt://127.0.0.1:18891?streamid=publish:match&pkt_size=1316')
    assert command[command.index('-c:v') + 1] == 'libx264'
    assert command[command.index('-bf') + 1] == '0'
    assert command[command.index('-g') + 1] == '25'
    assert '-vf' not in command


@pytest.mark.parametrize('target', [
    'srt://192.0.2.1:18891', 'srt://0.0.0.0:18891', 'rtsp://127.0.0.1:18891',
    'srt://127.0.0.1:18891?mode=listener', 'srt://user:pass@127.0.0.1:18891',
])
def test_sender_rejects_nonlocal_or_listener_targets(tmp_path, target):
    playlist = tmp_path / 'playlist.txt'
    playlist.touch()
    with pytest.raises(ValueError):
        sender_command('ffmpeg', playlist, target)


def test_sender_rejects_missing_playlist(tmp_path):
    with pytest.raises(ValueError):
        sender_command('ffmpeg', tmp_path / 'missing.txt', 'srt://127.0.0.1:18891')
