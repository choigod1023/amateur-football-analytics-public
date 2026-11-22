import pytest
from app.srt_path_ingest import config_for, secure_environment, mediamtx_binary, ROOT


def test_approved_firewall_binary_requires_explicit_setting():
    assert mediamtx_binary({}) == ROOT / 'mediamtx' / 'mediamtx.exe'
    assert mediamtx_binary({'FOOTBALL_SRT_APPROVED_BINARY': '1'}) == ROOT.parent / 'football-coach-server' / 'mediamtx' / 'mediamtx.exe'
    with pytest.raises(ValueError):
        mediamtx_binary({'FOOTBALL_SRT_APPROVED_BINARY': '../other.exe'})


def test_config_is_restricted_and_uses_path_not_a_user_password():
    config = config_for('127.0.0.1', '127.0.0.1', 18990, 18555)
    assert 'srtAddress: 127.0.0.1:18990' in config
    assert 'ips: [127.0.0.1/32]' in config
    assert 'srtPublishPassphrase: invalid_config_not_for_direct_use' in config
    assert 'api: false' in config and 'webrtc: false' in config
    assert 'record: true' not in config  # Plaintext demo uses default; no accidental recordings.


def test_recording_opt_in_preserves_security_and_never_autodeletes():
    config = config_for('127.0.0.1', '127.0.0.1', record=True)
    assert 'record: true' in config and 'recordDeleteAfter: 0s' in config
    assert 'recordFormat: fmp4' in config and 'recordSegmentDuration: 10m' in config


def test_allow_any_publisher_is_explicit_and_preserves_loopback_reader_and_encryption():
    config = config_for('192.168.1.44', '127.0.0.1', 8890, 18554, record=True, allow_any_publisher=True)
    assert 'srtAddress: 192.168.1.44:8890' in config
    assert '    ips: []\n    permissions:\n      - action: publish' in config
    assert '    ips: [127.0.0.1/32]\n    permissions:\n      - action: read' in config
    assert 'srtPublishPassphrase: invalid_config_not_for_direct_use' in config
    assert 'recordDeleteAfter: 0s' in config
    with pytest.raises(ValueError): config_for('127.0.0.1','127.0.0.1', allow_any_publisher='1')


@pytest.mark.parametrize('bind,source', [('0.0.0.0','127.0.0.1'), ('203.0.113.10','127.0.0.1'), ('127.0.0.1','0.0.0.0'), ('127.0.0.1','10.0.0.1/24')])
def test_rejects_ambiguous_bind_or_source(bind, source):
    with pytest.raises(ValueError): config_for(bind, source)


def test_environment_requires_passphrase_and_removes_mtx_overrides():
    with pytest.raises(ValueError): secure_environment({'FOOTBALL_SRT_PASSPHRASE':'short'})
    env=secure_environment({'FOOTBALL_SRT_PASSPHRASE':'a'*32,'MTX_API':'yes'})
    assert 'MTX_API' not in env
    assert env['MTX_PATHS_MATCH_SRTPUBLISHPASSPHRASE']=='a'*32
    assert env['MTX_PATHS_MATCH_RECORDPATH'].endswith('/%path/%Y-%m-%d_%H-%M-%S-%f_%z')
