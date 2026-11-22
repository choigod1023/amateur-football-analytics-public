import importlib.util
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'gpu_guard.py'
spec = importlib.util.spec_from_file_location('gpu_guard', SCRIPT)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


def test_preflight_ok_when_free():
    assert guard.preflight((2000, 12288), 16000, live=False, locked=False, vram_need_gb=8, ram_need_gb=12) == []


def test_preflight_refuses_low_vram_low_ram_live_and_lock():
    reasons = guard.preflight((11800, 12288), 1000, live=True, locked=True, vram_need_gb=8, ram_need_gb=12)
    text = ' '.join(reasons)
    assert 'another guarded GPU job' in text and 'live analysis' in text
    assert 'free GPU memory' in text and 'free RAM' in text


def test_preflight_allow_live_and_missing_gpu():
    assert guard.preflight((0, 12288), 20000, live=True, locked=False, vram_need_gb=8, ram_need_gb=12, allow_live=True) == []
    assert 'nvidia-smi' in ' '.join(guard.preflight(None, 20000, False, False, 8, 12))


def test_watchdog_needs_two_readings_in_a_row():
    dog = guard.Watchdog(ram_kill=90, vram_kill=95)
    assert dog.check(95, 50) is None
    assert dog.check(80, 50) is None  # back under: count resets
    assert dog.check(95, 50) is None
    assert 'RAM' in dog.check(96, 50)
    dog = guard.Watchdog(ram_kill=90, vram_kill=95)
    dog.check(50, 99)
    assert 'GPU memory' in dog.check(50, 99)
    assert guard.Watchdog(90, 95).check(50, None) is None


def test_wrap_command_inserts_cap_runner():
    capped = str(guard.ROOT / 'scripts' / 'run_capped.py')
    assert guard.wrap_command(['python', 'a.py', '--x'], 8) == ['python', capped, '8', 'a.py', '--x']
    assert guard.wrap_command(['C:/v/python.exe', '-X', 'utf8', 'a.py'], 6) == ['C:/v/python.exe', '-X', 'utf8', capped, '6', 'a.py']
    assert guard.wrap_command(['python', '-m', 'pkg.mod', 'x.py'], 8) == ['python', '-m', 'pkg.mod', 'x.py']
    assert guard.wrap_command(['ffmpeg', '-i', 'a.mp4'], 8) == ['ffmpeg', '-i', 'a.mp4']


def test_live_running_detects_live_process():
    class P:
        def __init__(self, line):
            self.info = {'cmdline': line.split()}
    assert guard.live_running([P('python scripts/run_live_feedback.py rtsp://x')])
    assert not guard.live_running([P('python scripts/train_ball_rerank.py a b')])


def test_full_run_with_tiny_job(tmp_path):
    log = tmp_path / 'runs.jsonl'
    code = guard.main(['--vram-need', '0', '--ram-need', '0', '--allow-live', '--log', str(log), '--interval', '0.2',
                       '--', sys.executable, '-c', 'print(1)'])
    assert code == 0
    assert '"exit": 0' in log.read_text(encoding='utf-8')
    assert not (tmp_path / 'running.lock').exists()
