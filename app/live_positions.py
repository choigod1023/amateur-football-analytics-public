"""The positions of a live run, one line per analysed second, so that a half can be summed up at half time without the video.

scripts/run_live_feedback.py --positions positions.jsonl writes a header line and then one line per second:
  {"type": "header", "team": "B", "other": "A", "direction": -1, "pitch_length": 89.0, "pitch_width": 62.0, "first_second": 64.0}
  {"type": "second", "time": 65.0, "team": [[track, x, y], ...], "other": [[track, x, y], ...]}
x and y are metres on the pitch (the form of scripts/build_tactical_report.metre_rows). The players are the ones the alerts see (app.live_feedback.LiveAnalyzer.held: a player
missed by the detector for a moment stays where he was seen last, two tracks closer than 1 m are one person). Nothing else is stored: no pictures, no names.

`read_positions` turns the file back into `by_frame` with one frame per second ({second: {team letter: [(track, x, y)]}}), the same shape that scripts/build_team_report.series_of and
app.team_tactics.seconds_series read when they are given fps 1.
"""
import json
from pathlib import Path


class PositionLog:
    def __init__(self, path, team, other, direction, pitch_length, pitch_width, first_second=0.0):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = open(self.path, 'a', encoding='utf-8')
        self.last_second = None
        self.write({'type': 'header', 'team': team, 'other': other, 'direction': direction, 'pitch_length': pitch_length, 'pitch_width': pitch_width,
                    'first_second': round(float(first_second), 1)})

    def write(self, record):
        self.handle.write(json.dumps(record, ensure_ascii=False) + '\n')
        self.handle.flush()

    def add(self, t, team, other):
        """One observation at stream time t; a line is written for the first observation of every whole second. Returns True when a line was written."""
        second = int(t)
        if second == self.last_second:
            return False
        self.last_second = second
        self.write({'type': 'second', 'time': round(float(t), 1), 'team': [[tid, round(x, 2), round(y, 2)] for tid, x, y in team],
                    'other': [[tid, round(x, 2), round(y, 2)] for tid, x, y in other]})
        return True

    def close(self):
        self.handle.close()


def read_positions(path):
    """-> (header dict, by_frame, frames): by_frame[second since the first line][team letter] = [(track, x, y)], frames = the number of seconds covered. A line that cannot be read is skipped."""
    header, seconds = {}, []
    with open(path, encoding='utf-8') as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if record.get('type') == 'header' and not header:
                header = record
            elif record.get('type') == 'second':
                seconds.append(record)
    if not header:
        raise ValueError('no header line in the positions file')
    team, other = header['team'], header['other']
    start = int(seconds[0]['time']) if seconds else 0
    by_frame = {}
    for record in seconds:
        frame = int(record['time']) - start
        by_frame[frame] = {team: [(tid, x, y) for tid, x, y in record['team']], other: [(tid, x, y) for tid, x, y in record['other']]}
    frames = (max(by_frame) + 1) if by_frame else 0
    return {**header, 'start_second': start}, by_frame, frames
