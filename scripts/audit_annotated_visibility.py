"""Summarize local annotation coverage; does not run a model or infer tactics."""
import argparse
import csv
import json
import math
import statistics
from pathlib import Path


def summarize(path):
    totals = {'0': [], '1': []}
    heights = []
    with Path(path).open(encoding='utf-8-sig', newline='') as handle:
        rows = csv.reader(handle)
        teams, ids, fields = next(rows), next(rows), next(rows)
        next(rows)  # frame-index heading
        columns = [(i, teams[i]) for i in range(1, len(fields), 4)
                   if i + 3 < len(fields) and teams[i] in totals and ids[i] != '0'
                   and fields[i:i+4] == ['bb_left', 'bb_top', 'bb_width', 'bb_height']]
        if not columns:
            raise ValueError('No recognized player box columns')
        for row in rows:
            if not row or not row[0]:
                continue
            counts = {'0': 0, '1': 0}
            for index, team in columns:
                try:
                    x, y, width, height = map(float, row[index:index+4])
                except (ValueError, IndexError):
                    continue
                if all(math.isfinite(v) for v in (x, y, width, height)) and width > 0 and height > 0 and x >= 0 and y >= 0:
                    counts[team] += 1
                    heights.append(height)
            for team in totals:
                totals[team].append(counts[team])
    if not totals['0']:
        raise ValueError('No annotated frames')
    count = len(totals['0'])
    both = sum(a >= 2 and b >= 2 for a, b in zip(totals['0'], totals['1']))
    return {'frames': count, 'team_0_median': statistics.median(totals['0']),
            'team_1_median': statistics.median(totals['1']),
            'both_teams_at_least_two_frames': both,
            'both_teams_at_least_two_fraction': round(both / count, 4),
            'box_height_median_px': round(statistics.median(heights), 2) if heights else None,
            'limitations': 'Annotation coverage only; roles, detector performance, calibration and tactics are not established.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('csv_files', nargs='+', type=Path)
    args = parser.parse_args()
    print(json.dumps({path.name: summarize(path) for path in args.csv_files}, ensure_ascii=False, indent=2))
