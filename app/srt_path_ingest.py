"""Source-restricted SRT ingestion without secrets in the SRT Stream ID.

This is a prototype, not an authorization to expose a public endpoint.
The SRT pre-shared passphrase still requires secure out-of-band distribution.
"""
import ipaddress
import os
import re
import subprocess
import tempfile
from pathlib import Path
from app.secure_srt import recording_directory
from app.recording_space import watch_free_space
from app.demo_job import ChildJob

ROOT = Path(__file__).resolve().parent.parent


def config_for(bind_ip: str, source_ip: str, srt_port: int = 18890, rtsp_port: int = 18554, *, record: bool = False, allow_any_publisher: bool = False, hls_port: int = 18888) -> str:
    bind = ipaddress.ip_address(bind_ip)
    source = ipaddress.ip_address(source_ip)
    if bind.version != 4 or bind.is_unspecified or bind.is_multicast or bind.is_link_local:
        raise ValueError('bind must be a specific IPv4 address')
    if not (bind.is_loopback or bind in ipaddress.ip_network('10.0.0.0/8') or bind in ipaddress.ip_network('172.16.0.0/12') or bind in ipaddress.ip_network('192.168.0.0/16')):
        raise ValueError('bind must be loopback or an RFC1918 address')
    if source.version != 4 or source.is_unspecified or source.is_multicast or source.is_link_local:
        raise ValueError('source must be one valid IPv4 address')
    if not all(isinstance(v, int) and not isinstance(v, bool) and 1024 <= v <= 65535 for v in (srt_port, rtsp_port, hls_port)):
        raise ValueError('invalid port')
    if hls_port in (srt_port, rtsp_port):
        raise ValueError('HLS port must differ from the SRT and RTSP ports')
    if not isinstance(allow_any_publisher, bool):
        raise ValueError('allow_any_publisher must be boolean')
    publisher_ips = '[]' if allow_any_publisher else f'[{source}/32]'
    recording = ('    record: true\n    recordFormat: fmp4\n    recordPartDuration: 1s\n'
                 '    recordSegmentDuration: 10m\n    recordDeleteAfter: 0s\n') if record else ''
    return f'''logLevel: error
rtsp: true
rtspAddress: 127.0.0.1:{rtsp_port}
rtspTransports: [tcp]
rtmp: false
hls: true
hlsAddress: 127.0.0.1:{hls_port}
hlsVariant: fmp4
hlsSegmentDuration: 1s
hlsSegmentCount: 5
hlsAllowOrigins: []
webrtc: false
moq: false
srt: true
srtAddress: {bind}:{srt_port}
api: false
metrics: false
pprof: false
playback: false
authMethod: internal
authInternalUsers:
  - user: any
    ips: {publisher_ips}
    permissions:
      - action: publish
        path: match
  - user: any
    ips: [127.0.0.1/32]
    permissions:
      - action: read
        path: match
paths:
  match:
    srtPublishPassphrase: invalid_config_not_for_direct_use
    overridePublisher: false
{recording}'''


def secure_environment(environ):
    phrase = environ.get('FOOTBALL_SRT_PASSPHRASE', '')
    if not re.fullmatch(r'[A-Za-z0-9_-]{32,64}', phrase):
        raise ValueError('passphrase must be 32-64 safe ASCII characters')
    env = {k: v for k, v in environ.items() if not k.upper().startswith('MTX_')}
    env['MTX_PATHS_MATCH_SRTPUBLISHPASSPHRASE'] = phrase
    env['MTX_PATHS_MATCH_RECORDPATH'] = (recording_directory(environ) / '%path' / '%Y-%m-%d_%H-%M-%S-%f_%z').as_posix()
    return env


def mediamtx_binary(environ):
    """Select only the local executable or the existing firewall-approved copy."""
    use_approved = environ.get('FOOTBALL_SRT_APPROVED_BINARY', '0')
    if use_approved not in ('0', '1'):
        raise ValueError('FOOTBALL_SRT_APPROVED_BINARY must be 0 or 1')
    root = ROOT.parent / 'football-coach-server' if use_approved == '1' else ROOT
    return root / 'mediamtx' / 'mediamtx.exe'


def main():
    try:
        allow_any = os.environ.get('FOOTBALL_SRT_ALLOW_ANY_PUBLISHER', '0')
        if allow_any not in ('0', '1'):
            raise ValueError('FOOTBALL_SRT_ALLOW_ANY_PUBLISHER must be 0 or 1')
        cfg = config_for(os.environ.get('FOOTBALL_SRT_BIND_IP', '127.0.0.1'),
                         os.environ.get('FOOTBALL_SRT_PUBLISHER_IP', '127.0.0.1'),
                         int(os.environ.get('FOOTBALL_SRT_PORT', '18890')),
                         int(os.environ.get('FOOTBALL_RTSP_PORT', '18554')),
                         record=True, allow_any_publisher=allow_any == '1',
                         hls_port=int(os.environ.get('FOOTBALL_HLS_PORT', '18888')))
        env = secure_environment(os.environ)
        exe = mediamtx_binary(os.environ)
        recording_directory(os.environ).mkdir(parents=True, exist_ok=True)
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
    if not exe.is_file(): raise SystemExit('MediaMTX binary missing')
    with tempfile.TemporaryDirectory(prefix='football-path-ingest-') as temp:
        config = Path(temp) / 'mediamtx.yml'
        config.write_text(cfg, encoding='utf-8')
        with watch_free_space(recording_directory(os.environ)):
            job = ChildJob()
            process = None
            try:
                process = subprocess.Popen([str(exe), str(config)], env=env)
                job.add(process)
                result = process.wait()
                if result:
                    raise subprocess.CalledProcessError(result, [str(exe), str(config)])
            finally:
                if process is not None and process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                job.close()


if __name__ == '__main__': main()
