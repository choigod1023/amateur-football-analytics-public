"""Commands for a running live run: the button of the second half writes a line to <store>/alerts/<session>/control.jsonl and the run reads it between two frames,
so that nobody has to stop and start the run at half time.

  {"seq": 1, "cmd": "second_half", "direction": -1, "at": 1794965430.0}

The run (scripts/run_live_feedback.py) turns the attack direction round, starts a new analyser (positions held, the pause between repeated alerts, the paths of the first half are gone),
writes a line {"type": "half", "half": 2, ...} into positions.jsonl and a status row 'half_switch' into the alerts file. Lines that were already in the file when the run started are not
executed again (a run that is started again for the second half must not turn the direction a second time).
"""
import json
import os
from pathlib import Path


class ControlWatcher:
    def __init__(self, path):
        self.path = Path(path)
        self.seen = self._count()
        self.size = self._size()

    def _size(self):
        try:
            return os.path.getsize(self.path)
        except OSError:
            return 0

    def _count(self):
        try:
            return sum(1 for line in open(self.path, encoding='utf-8') if line.strip())
        except OSError:
            return 0

    def poll(self):
        """The new commands since the last call: [{'cmd': 'second_half', 'direction': 1 or -1, ...}]. A stat of the file per call, nothing else while the file does not change."""
        size = self._size()
        if size == self.size:
            return []
        self.size = size
        commands = []
        try:
            lines = [line for line in open(self.path, encoding='utf-8') if line.strip()]
        except OSError:
            return []
        for line in lines[self.seen:]:
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict) and row.get('cmd') == 'second_half' and row.get('direction') in (1, -1):
                commands.append(row)
        self.seen = len(lines)
        return commands
