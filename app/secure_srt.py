"""Launch a deliberately loopback-only MediaMTX setup from process secrets.

Do not log env or command-line arguments containing credentials. This helper does
not open a firewall or router, and is not a public deployment configuration.
"""
import os
from pathlib import Path
import re
import subprocess
from app.recording_space import watch_free_space

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / 'configs' / 'mediamtx-srt-local.yml'
DEFAULT_RECORD_DIR = ROOT.parent.parent / 'work' / 'recordings'


def recording_directory(environ):
    """Absolute destination; never delete existing recordings automatically."""
    override = environ.get('FOOTBALL_RECORD_DIR', '')
    path = Path(override).expanduser() if override else DEFAULT_RECORD_DIR
    if not path.is_absolute():
        raise ValueError('FOOTBALL_RECORD_DIR must be an absolute path')
    return path.resolve()


def local_environment(environ):
    user = environ.get('FOOTBALL_SRT_USER', '')
    password = environ.get('FOOTBALL_SRT_PASSWORD', '')
    phrase = environ.get('FOOTBALL_SRT_PASSPHRASE', '')
    # The stream-id syntax uses colon as separator. Require sufficiently long
    # printable values, but entropy must come from a secure generator.
    if not re.fullmatch(r'[A-Za-z0-9_-]{8,64}', user):
        raise ValueError('FOOTBALL_SRT_USER must contain 8-64 safe ASCII characters')
    if not re.fullmatch(r'[A-Za-z0-9_-]{32,64}', password):
        raise ValueError('FOOTBALL_SRT_PASSWORD must contain 32-64 safe ASCII characters')
    if not re.fullmatch(r'[A-Za-z0-9_-]{32,64}', phrase):
        raise ValueError('FOOTBALL_SRT_PASSPHRASE must contain 32-64 safe ASCII characters')
    if len({user, password, phrase}) != 3:
        raise ValueError('Use distinct credentials and passphrase')
    # Do not inherit externally supplied MTX_ overrides that could expose
    # listeners or silently change the authentication and allowed paths.
    env = {k: v for k, v in environ.items() if not k.upper().startswith('MTX_')}
    env.update({
        'MTX_AUTHINTERNALUSERS_0_USER': user,
        'MTX_AUTHINTERNALUSERS_0_PASS': password,
        'MTX_PATHS_MATCH_SRTPUBLISHPASSPHRASE': phrase,
        'MTX_PATHS_MATCH_RECORDPATH': (recording_directory(environ) / '%path' / '%Y-%m-%d_%H-%M-%S-%f_%z').as_posix(),
    })
    return env


def main():
    binary = ROOT / 'mediamtx' / 'mediamtx.exe'
    env = local_environment(os.environ)
    recording_directory(os.environ).mkdir(parents=True, exist_ok=True)
    if not binary.is_file():
        raise SystemExit('MediaMTX binary missing; see README')
    with watch_free_space(recording_directory(os.environ)):
        subprocess.run([str(binary), str(CONFIG)], env=env, check=True)


if __name__ == '__main__':
    main()
