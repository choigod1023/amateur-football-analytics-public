"""Prepare a source-restricted SRT listener without modifying router/firewall.

Test only. SRT media encryption does not make the Stream ID credentials
confidential; use only after assessing the connection and credential risks.
"""
import ipaddress
import os
from pathlib import Path
import subprocess
import tempfile

from app.secure_srt import CONFIG, ROOT, local_environment, recording_directory
from app.recording_space import watch_free_space


def lan_configuration(bind_ip, publisher_ip):
    bind = ipaddress.ip_address(bind_ip)
    publisher = ipaddress.ip_address(publisher_ip)
    if bind.version != 4 or not bind.is_private or bind.is_loopback or bind.is_unspecified or bind.is_link_local:
        raise ValueError('Bind address must be a private IPv4 LAN address')
    if publisher.version != 4 or publisher.is_unspecified or publisher.is_multicast or publisher.is_loopback:
        raise ValueError('Publisher must be one non-loopback IPv4 address')
    template = Path(CONFIG).read_text(encoding='utf-8')
    if template.count('srtAddress: 127.0.0.1:18890') != 1 or template.count('    ips: [127.0.0.1]') != 2:
        raise ValueError('Unexpected MediaMTX template; refusing to run')
    template = template.replace('srtAddress: 127.0.0.1:18890', f'srtAddress: {bind}:8890')
    template = template.replace('    ips: [127.0.0.1]', f'    ips: [{publisher}/32]', 1)
    return template


def main():
    try:
        env = local_environment(os.environ)
        config = lan_configuration(os.environ.get('FOOTBALL_SRT_BIND_IP', ''), os.environ.get('FOOTBALL_SRT_PUBLISHER_IP', ''))
        recording_directory(os.environ).mkdir(parents=True, exist_ok=True)
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
    binary = ROOT / 'mediamtx' / 'mediamtx.exe'
    if not binary.is_file():
        raise SystemExit('MediaMTX binary missing; see README')
    with tempfile.TemporaryDirectory(prefix='football-srt-') as directory:
        path = Path(directory) / 'mediamtx.yml'
        path.write_text(config, encoding='utf-8')
        with watch_free_space(recording_directory(os.environ)):
            subprocess.run([str(binary), str(path)], env=env, check=True)


if __name__ == '__main__':
    main()
