"""Read-only health check of the stream the server is receiving, with a green / yellow / red verdict in coach words.

What it reads: the newest recording file of the receiver (work/recordings/match/, see docs/live-recording.md) or a file given by path. Nothing is opened for writing.
Cost: one light ffprobe call that lists the packets of the last few seconds (no decoding), and every `decode_every_s` seconds a second call that decodes only the last
few seconds to count decoder errors. Both run at below-normal priority. The result is cached by `StreamHealthMonitor`, so any number of viewers cause the same load.

Rules (wiki/srt-degradation-test-1118.md, wiki/stream-diagnosis.md): 1080p needs 4000 kbps or more, around 2000 kbps 720p is better than 1080p, 500 kbps or less is not usable.
These come from a computer test (loopback SRT, re-encoded videos), not from measurements of the phone app. The limits for frame rate, key frame interval and gaps are proposals.
"""
import argparse
import json
import os
import statistics
import subprocess
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECORD_SUFFIXES = ('.mp4', '.ts', '.mkv')
LEVELS = {'green': 0, 'yellow': 1, 'red': 2}
LEVEL_NAME = {value: key for key, value in LEVELS.items()}
# bitrate limits (kbit/s) as (red below, yellow below) per picture height class, from the computer test
# (the limits sit a little under the test values 2000/4000 and 1000/2000 because a sender set to 4000 reaches about 3970 in the synthetic check: a setting must not turn yellow by rounding)
BITRATE_LIMITS = {'1080': (2100, 3800), '720': (1100, 1900), 'low': (550, 1000000)}
MIN_FPS_YELLOW, MIN_FPS_RED = 24.0, 15.0
KEY_INTERVAL_YELLOW_S = 2.5
GAP_YELLOW_S, GAP_RED_S = 0.15, 1.0
STALL_YELLOW_S, STALL_RED_S = 5.0, 15.0


def default_directory():
    override = os.environ.get('FOOTBALL_RECORD_DIR', '')
    return Path(override) if override else ROOT.parents[1] / 'work' / 'recordings' / 'match'


def default_ffprobe():
    for candidate in sorted((ROOT.parents[1] / 'work' / 'ffmpeg-local').glob('*/bin/ffprobe.exe')):
        return candidate
    return Path('ffprobe')


def newest_recording(directory):
    """The most recently written recording file in the directory, or None."""
    directory = Path(directory)
    best = None
    try:
        for path in directory.iterdir():
            if path.suffix.lower() in RECORD_SUFFIXES and path.is_file():
                try:
                    stat = path.stat()
                except FileNotFoundError:
                    continue
                if best is None or stat.st_mtime > best[0]:
                    best = (stat.st_mtime, path)
    except OSError:
        return None
    return best[1] if best else None


def _run(command, timeout):
    flags = getattr(subprocess, 'BELOW_NORMAL_PRIORITY_CLASS', 0) | getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    return subprocess.run(command, capture_output=True, text=True, timeout=timeout, creationflags=flags)


def read_packets(ffprobe, path, start_s, window_s):
    """(pts seconds, bytes, is key frame) of the packets from start_s on, without decoding. start_s None reads the whole file."""
    command = [str(ffprobe), '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'packet=pts_time,size,flags', '-of', 'csv=p=0']
    if start_s is not None:
        command += ['-read_intervals', f'{max(0.0, start_s):.2f}%+{window_s + 5:.0f}']
    command.append(str(path))
    packets = []
    for line in _run(command, 60).stdout.splitlines():
        parts = line.split(',')
        try:
            packets.append((float(parts[0]), int(parts[1]), len(parts) > 2 and 'K' in parts[2]))
        except (ValueError, IndexError):
            continue
    packets.sort()
    return packets


def read_stream_info(ffprobe, path):
    out = _run([str(ffprobe), '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=codec_name,width,height,r_frame_rate', '-of', 'json', str(path)], 30).stdout
    try:
        return (json.loads(out).get('streams') or [{}])[0]
    except ValueError:
        return {}


def count_decode_errors(ffprobe, path, start_s, seconds):
    """Decoder complaint lines and decoded frame count in a short window (decodes only that window)."""
    command = [str(ffprobe), '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'frame=pts_time', '-of', 'csv=p=0',
               '-read_intervals', f'{max(0.0, start_s):.2f}%+{seconds:.0f}', str(path)]
    result = _run(command, 60)
    frames = sum(1 for line in result.stdout.splitlines() if line.strip())
    errors = [line for line in (result.stderr or '').splitlines() if line.strip()]
    return {'errors': len(errors), 'frames': frames}


def summarize_packets(packets, window_s):
    """Numbers of the last window_s seconds of media time from the packet list."""
    if len(packets) < 2:
        return None
    end = packets[-1][0]
    recent = [p for p in packets if p[0] >= end - window_s]
    if len(recent) < 2:
        return None
    span = recent[-1][0] - recent[0][0]
    if span <= 0:
        return None
    times = [p[0] for p in recent]
    gaps = [b - a for a, b in zip(times, times[1:])]
    keys = [p[0] for p in recent if p[2]]
    key_intervals = [b - a for a, b in zip(keys, keys[1:])]
    seconds = {}
    for t, size, _ in recent:
        seconds[int(t - recent[0][0])] = seconds.get(int(t - recent[0][0]), 0) + size
    # the last bucket is usually partial; only whole seconds count for the low point
    whole = [bits * 8 / 1000 for second, bits in seconds.items() if second < int(span)]
    typical_gap = statistics.median(gaps)
    return {'media_end_s': round(end, 2), 'window_s': round(span, 1), 'packets': len(recent),
            'bitrate_kbps': round(sum(p[1] for p in recent[1:]) * 8 / span / 1000),
            'lowest_second_kbps': round(min(whole)) if whole else None,
            'fps': round((len(recent) - 1) / span, 1),
            'key_interval_s': round(statistics.median(key_intervals), 2) if key_intervals else None,
            'key_interval_max_s': round(max(key_intervals), 2) if key_intervals else None,
            'key_frames_seen': len(keys),
            'gap_count': sum(1 for g in gaps if g > max(GAP_YELLOW_S, 3 * typical_gap)),
            'longest_gap_s': round(max(gaps), 2)}


def height_class(height):
    if height is None:
        return None
    return '1080' if height >= 1000 else '720' if height >= 600 else 'low'


def judge(measure):
    """Items and overall verdict from one measurement dict (see measure_stream). Pure function so the rules can be tested without video."""
    items = []

    def add(key, label, value, level, message):
        items.append({'key': key, 'label': label, 'value': value, 'level': level, 'message': message})

    age = measure.get('seconds_since_data')
    if measure.get('file') is None:
        return {'level': 'gray', 'headline': '아직 송출이 들어오지 않았습니다.', 'detail': '휴대폰에서 송출을 시작하면 이 화면이 몇 초 안에 상태를 보여 드립니다.', 'items': []}
    if age is not None and age >= STALL_YELLOW_S:
        level = 'red' if age >= STALL_RED_S else 'yellow'
        return {'level': level, 'headline': f'영상이 {age:.0f}초째 들어오지 않고 있습니다.',
                'detail': '휴대폰의 송출이 멈췄거나 망이 끊겼을 수 있습니다. 앱에서 송출 상태와 5G 신호를 확인해 주세요.', 'items': []}
    stats = measure.get('numbers')
    if not stats:
        return {'level': 'gray', 'headline': '송출을 읽는 중입니다.', 'detail': '데이터가 몇 초 쌓이면 상태가 나옵니다.', 'items': []}

    height, kbps = measure.get('height'), stats['bitrate_kbps']
    cls = height_class(height)
    size_text = f"{measure.get('width')}x{height}" if height else '알 수 없음'
    if cls is None:
        add('quality', '해상도와 비트레이트', f'{kbps / 1000:.1f} Mbps', 'yellow', '해상도를 읽지 못했습니다. 비트레이트만으로는 판단하기 어렵습니다.')
    else:
        red_below, yellow_below = BITRATE_LIMITS[cls]
        value = f'{size_text}, {kbps / 1000:.1f} Mbps'
        if kbps <= 500 or kbps < red_below:
            msg = ('지금 영상이 많이 약해서 먼 쪽 선수를 놓칠 가능성이 큽니다. 비트레이트를 올리거나 해상도를 낮추고, 비트레이트를 고정으로 바꿔 주세요.'
                   if cls != '1080' else '1080p인데 비트레이트가 모자랍니다. 비트레이트를 4 Mbps 이상으로 고정하거나, 망이 받쳐 주지 않으면 해상도를 720p로 낮춰 2 Mbps 이상으로 보내 주세요.')
            add('quality', '해상도와 비트레이트', value, 'red', msg)
        elif kbps < yellow_below:
            msg = ('1080p에 비해 비트레이트가 낮습니다. 4 Mbps 이상으로 올리거나, 망이 불안하면 720p로 낮춰 2 Mbps 이상으로 고정해 주세요.' if cls == '1080'
                   else '비트레이트가 약간 낮습니다. 2 Mbps 이상으로 올려 주세요. 선수가 작게 보이는 구도에서는 더 많이 놓칠 수 있습니다.')
            add('quality', '해상도와 비트레이트', value, 'yellow', msg)
        elif cls == 'low':
            add('quality', '해상도와 비트레이트', value, 'yellow', '해상도가 낮아서 먼 쪽 선수를 놓칠 수 있습니다. 가능하면 720p 이상으로 올려 주세요.')
        else:
            low = stats.get('lowest_second_kbps')
            if low is not None and low < red_below and kbps >= yellow_below:
                add('quality', '해상도와 비트레이트', value, 'yellow',
                    f'평균은 충분하지만 순간적으로 {low / 1000:.1f} Mbps까지 내려갔습니다. 비트레이트를 고정으로 두고 앱의 적응형 설정은 하한을 정해 주세요.')
            else:
                add('quality', '해상도와 비트레이트', value, 'green', '분석에 충분한 화질로 들어오고 있습니다.')

    fps = stats['fps']
    if fps < MIN_FPS_RED:
        add('fps', '초당 화면 수', f'{fps:.0f}', 'red', '화면 수가 너무 적어 움직임을 따라가기 어렵습니다. 앱에서 30프레임으로 맞춰 주세요.')
    elif fps < MIN_FPS_YELLOW:
        add('fps', '초당 화면 수', f'{fps:.0f}', 'yellow', '화면 수가 적습니다. 앱에서 30프레임으로 맞춰 주세요. 휴대폰이 뜨거우면 줄어들기도 합니다.')
    else:
        add('fps', '초당 화면 수', f'{fps:.0f}', 'green', '충분합니다.')

    interval = stats.get('key_interval_s')
    if interval is None:
        add('key', '화면 복구 간격(키프레임)', '확인 중', 'yellow', '이 구간에서는 키프레임을 보지 못했습니다. 앱에서 키프레임 간격을 1~2초로 지정해 주세요.')
    elif interval > KEY_INTERVAL_YELLOW_S:
        add('key', '화면 복구 간격(키프레임)', f'{interval:.1f}초', 'yellow', '간격이 깁니다. 화면이 깨지면 다시 맑아지기까지 오래 걸립니다. 앱에서 1~2초로 줄여 주세요.')
    else:
        add('key', '화면 복구 간격(키프레임)', f'{interval:.1f}초', 'green', '적절합니다.')

    gaps, longest = stats['gap_count'], stats['longest_gap_s']
    if longest >= GAP_RED_S:
        add('gaps', '끊김', f'가장 긴 공백 {longest:.1f}초', 'red', '영상이 1초 이상 멈춘 순간이 있었습니다. 그동안 선수 위치는 분석되지 않습니다. 망이 약하면 SRT 지연 시간 설정을 늘려 주세요.')
    elif gaps:
        add('gaps', '끊김', f'{gaps}번, 가장 긴 공백 {longest:.2f}초', 'yellow', '짧게 끊긴 순간이 있습니다. 자주 생기면 SRT 지연 시간 설정을 늘려 주세요(대신 화면이 조금 늦게 옵니다).')
    else:
        add('gaps', '끊김', '없음', 'green', '끊김 없이 들어오고 있습니다.')

    decode = measure.get('decode')
    if decode is None:
        add('decode', '화면 깨짐', '확인 중', 'green', '곧 확인합니다.')
    elif decode['errors']:
        add('decode', '화면 깨짐', f"{decode['errors']}번", 'yellow', '화면이 순간적으로 깨진 흔적이 있습니다. 망이 불안하다는 신호입니다. 지속되면 비트레이트를 낮추거나 SRT 지연 시간을 늘려 주세요.')
    else:
        add('decode', '화면 깨짐', '없음', 'green', '깨짐 없이 읽힙니다.')

    level = LEVEL_NAME[max(LEVELS[i['level']] for i in items)]
    worst = [i for i in items if i['level'] == level]
    headline = {'green': '지금 설정이면 분석에 충분합니다.', 'yellow': '쓸 수는 있지만 조정하면 더 좋아집니다.', 'red': '지금 설정으로는 분석이 약해집니다. 먼저 조정해 주세요.'}[level]
    detail = worst[0]['message'] if level != 'green' else '이대로 경기를 시작하셔도 됩니다. 송출 중에 이 화면을 계속 보실 수 있습니다.'
    return {'level': level, 'headline': headline, 'detail': detail, 'items': items}


def measure_stream(ffprobe, path, window_s=10.0, decode=True, now=None):
    """Read-only measurement of the last window_s seconds of one recording file."""
    path = Path(path)
    now = time.time() if now is None else now
    try:
        stat = path.stat()
    except OSError:
        return {'file': None}
    info = read_stream_info(ffprobe, path)
    # the file is being written: media time is about the time since the file was created, so seek near the end; fall back to a full scan
    created = getattr(stat, 'st_birthtime', None) or stat.st_ctime
    guess = max(0.0, stat.st_mtime - created - window_s - 3)
    packets = read_packets(ffprobe, path, guess, window_s) if guess > 20 else []
    if len(packets) < 2:
        packets = read_packets(ffprobe, path, None, window_s)
    numbers = summarize_packets(packets, window_s)
    result = {'file': path.name, 'file_bytes': stat.st_size, 'seconds_since_data': round(max(0.0, now - stat.st_mtime), 1), 'codec': info.get('codec_name'),
              'width': info.get('width'), 'height': info.get('height'), 'numbers': numbers, 'decode': None}
    if numbers and decode:
        result['decode'] = count_decode_errors(ffprobe, path, numbers['media_end_s'] - 8, 5)
    return result


class StreamHealthMonitor:
    """Measures in the background and keeps the latest result, so viewers only read the cache."""

    def __init__(self, directory=None, ffprobe=None, file=None, interval_s=3.0, window_s=10.0, decode_every_s=15.0):
        self.directory, self.file = Path(directory) if directory else default_directory(), Path(file) if file else None
        self.ffprobe = Path(ffprobe) if ffprobe else default_ffprobe()
        self.interval_s, self.window_s, self.decode_every_s = interval_s, window_s, decode_every_s
        self.latest = {'level': 'gray', 'headline': '송출을 읽는 중입니다.', 'detail': '', 'items': [], 'updated': None}
        self._decode = None
        self._decode_at = 0.0
        self._decode_file = None
        self._stop = threading.Event()
        self._thread = None

    def once(self):
        path = self.file or newest_recording(self.directory)
        if path is None:
            measure = {'file': None}
        else:
            due = time.time() - self._decode_at >= self.decode_every_s or self._decode_file != path.name
            measure = measure_stream(self.ffprobe, path, self.window_s, decode=due)
            if due and measure.get('decode') is not None:
                self._decode, self._decode_at, self._decode_file = measure['decode'], time.time(), path.name
            elif measure.get('numbers'):
                measure['decode'] = self._decode if self._decode_file == path.name else None
        verdict = judge(measure)
        verdict['updated'] = time.strftime('%H:%M:%S')
        verdict['file'] = measure.get('file')
        verdict['numbers'] = measure.get('numbers')
        verdict['size'] = f"{measure.get('width')}x{measure.get('height')}" if measure.get('height') else None
        verdict['codec'] = measure.get('codec')
        verdict['seconds_since_data'] = measure.get('seconds_since_data')
        self.latest = verdict
        return verdict

    def start(self):
        def loop():
            while not self._stop.is_set():
                try:
                    self.once()
                except Exception as exc:  # a failed read must never stop the screen
                    self.latest = {'level': 'gray', 'headline': '송출 상태를 읽지 못했습니다.', 'detail': f'다시 시도하고 있습니다. ({type(exc).__name__})', 'items': [], 'updated': time.strftime('%H:%M:%S')}
                self._stop.wait(self.interval_s)
        self._thread = threading.Thread(target=loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()


def install(app, monitor, web_root=None):
    """Adds GET /stream (page) and GET /api/stream-health (cached JSON) to a FastAPI app. Read only."""
    from fastapi import HTTPException
    from fastapi.responses import FileResponse
    root = Path(web_root) if web_root else ROOT / 'web'

    @app.get('/api/stream-health')
    def api():
        return monitor.latest

    @app.get('/stream')
    def page():
        path = root / 'stream_health.html'
        if not path.is_file():
            raise HTTPException(404)
        return FileResponse(path)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Print one measurement of the stream being recorded.')
    parser.add_argument('--directory', type=Path); parser.add_argument('--file', type=Path); parser.add_argument('--ffprobe', type=Path)
    args = parser.parse_args(argv)
    monitor = StreamHealthMonitor(args.directory, args.ffprobe, args.file)
    print(json.dumps(monitor.once(), ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
