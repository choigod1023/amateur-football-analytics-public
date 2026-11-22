import pytest
from app.secure_srt import local_environment, recording_directory


def test_secrets_required_and_untrusted_overrides_removed():
    with pytest.raises(ValueError):
        local_environment({})
    env = local_environment({
        'FOOTBALL_SRT_USER': 'safe-user-123',
        'FOOTBALL_SRT_PASSWORD': 'x' * 32,
        'FOOTBALL_SRT_PASSPHRASE': 'y' * 32,
        'MTX_SRTADDRESS': ':18890',
        'MTX_API': 'yes',
    })
    assert 'MTX_SRTADDRESS' not in env and 'MTX_API' not in env
    assert env['MTX_AUTHINTERNALUSERS_0_USER'] == 'safe-user-123'
    assert env['MTX_PATHS_MATCH_SRTPUBLISHPASSPHRASE'] == 'y' * 32
    assert env['MTX_PATHS_MATCH_RECORDPATH'].endswith('/%path/%Y-%m-%d_%H-%M-%S-%f_%z')


def test_record_directory_rejects_relative_path():
    with pytest.raises(ValueError):
        recording_directory({'FOOTBALL_RECORD_DIR': 'relative'})
