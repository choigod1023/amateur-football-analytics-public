"""Find the moment of an analyst tag in the match recordings and cut a short clip around it.

The recorder (scripts/record_stream_loop.ps1) writes pieces named YYYY-MM-DD_HH-MM-SS.mp4 (local time at the start of the piece) into one folder per match.
A tag stores the server time at which the analyst pressed the button; the clip is taken from BEFORE seconds before that time to AFTER seconds after it,
because the button is pressed after the event and the stream reaches the server a few seconds late. A clip that crosses two pieces is joined.

The clip is copied, not re-encoded (no load on the computer during the match), so it starts at the key frame before the asked time, at most a few seconds earlier.
Only the standard library and ffmpeg are used.
"""
import datetime as dt
import os
import re
import subprocess
import tempfile
from pathlib import Path

PIECE = re.compile(r'^(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})\.mp4$')
BEFORE, AFTER = 20.0, 6.0
DEFAULT_LENGTH = 600.0          # the recorder cuts pieces of 10 minutes


def default_recordings():
    """outputs/football-coach-server/recordings next to this project."""
    return Path(__file__).resolve().parents[2] / 'football-coach-server' / 'recordings'


def default_ffmpeg():
    env = os.environ.get('FOOTBALL_FFMPEG')
    if env:
        return env
    found = sorted((Path(__file__).resolve().parents[3] / 'work' / 'ffmpeg-local').glob('*/bin/ffmpeg.exe'))
    return str(found[-1]) if found else 'ffmpeg'


def pieces(root):
    """All recording pieces below root as (start epoch, path), oldest first. Pieces of every match folder are included."""
    out = []
    root = Path(root)
    if not root.is_dir():
        return out
    for path in root.rglob('*.mp4'):
        m = PIECE.match(path.name)
        if not m:
            continue
        start = dt.datetime.strptime(m.group(1), '%Y-%m-%d_%H-%M-%S').timestamp()
        out.append((start, path))
    out.sort()
    return out


def spans(all_pieces, start, end):
    """The parts of [start, end) covered by the pieces: [(path, inpoint, outpoint)]. A piece lasts until the next piece starts (or DEFAULT_LENGTH)."""
    out = []
    for k, (begin, path) in enumerate(all_pieces):
        finish = all_pieces[k + 1][0] if k + 1 < len(all_pieces) else begin + DEFAULT_LENGTH
        finish = min(finish, begin + DEFAULT_LENGTH + 30)      # a gap after a crash is not inside the previous piece
        lo, hi = max(start, begin), min(end, finish)
        if hi > lo:
            out.append((path, lo - begin, hi - begin))
    return out


def cut(ffmpeg, parts, out_path, timeout=90):
    """Copy the parts into one clip. Returns True when the clip exists afterwards."""
    if not parts:
        return False
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fd, listing = tempfile.mkstemp(suffix='.txt', dir=out_path.parent)
    temporary = out_path.with_suffix('.part.mp4')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            for path, inpoint, outpoint in parts:
                handle.write("file '%s'\ninpoint %.2f\noutpoint %.2f\n" % (Path(path).as_posix().replace("'", "'\\''"), inpoint, outpoint))
        flags = getattr(subprocess, 'BELOW_NORMAL_PRIORITY_CLASS', 0)
        result = subprocess.run([ffmpeg, '-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', listing, '-c', 'copy', '-movflags', '+faststart', str(temporary)],
                                capture_output=True, timeout=timeout, creationflags=flags)
        if result.returncode == 0 and temporary.is_file() and temporary.stat().st_size > 0:
            os.replace(temporary, out_path)
            return True
        return False
    except (OSError, subprocess.SubprocessError):
        return False
    finally:
        for p in (listing, temporary):
            try:
                os.unlink(p)
            except OSError:
                pass


def clip_for(epoch, recordings, ffmpeg, out_path, before=BEFORE, after=AFTER):
    """Cut the clip of one tag. Returns 'done', 'no-recording' or 'failed'."""
    parts = spans(pieces(recordings), epoch - before, epoch + after)
    if not parts:
        return 'no-recording'
    return 'done' if cut(ffmpeg, parts, out_path) else 'failed'
