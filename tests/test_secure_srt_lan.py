import pytest
from app.secure_srt_lan import lan_configuration


def test_config_is_source_restricted_and_other_listeners_stay_local():
    config = lan_configuration('192.168.42.10', '203.0.113.50')
    assert 'srtAddress: 192.168.42.10:8890' in config
    assert 'ips: [203.0.113.50/32]' in config
    assert 'rtspAddress: 127.0.0.1:18554' in config
    assert 'ips: [127.0.0.1]' in config
    assert all(line in config for line in ('api: false', 'webrtc: false', 'rtmp: false'))


@pytest.mark.parametrize('bind,publisher', [('', '203.0.113.50'), ('0.0.0.0','203.0.113.50'), ('127.0.0.1','203.0.113.50'), ('192.168.1.4','0.0.0.0'), ('192.168.1.4','203.0.113.0/24')])
def test_rejects_ambiguous_or_wildcard_addresses(bind, publisher):
    with pytest.raises(ValueError):
        lan_configuration(bind, publisher)
