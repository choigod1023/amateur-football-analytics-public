import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(shutil.which('node') is None, reason='node not available')
def test_match_clock_words():
    done = subprocess.run(['node', str(ROOT / 'tests' / 'test_match_clock_ui.cjs')], cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stdout + done.stderr
