"""Plot how the two teams' shape changes over the clips written by scripts/build_team_minimap.py.

Usage: python scripts/plot_team_timeline.py <output image.png> <metrics.json> [<metrics.json> ...] [--smooth N]

--smooth N draws the median of the last N frames instead of every frame (use about 15 for 60 second stretches).

One column per clip: horizontal centre of each team along the pitch (metres, the goal on the left is negative), team depth,
team width and the share of crowded players. Teams with fewer than four players in a frame leave a gap. The values describe
10 second clips, are measured on an estimated pitch size and are not tactical judgements.
"""
import json
import sys
from pathlib import Path


def rolling_median(values, window):
    """Median of the last `window` values that are numbers; gaps stay gaps. window <= 1 returns the values unchanged."""
    if window <= 1:
        return list(values)
    out = []
    for i in range(len(values)):
        part = sorted(v for v in values[max(0, i - window + 1):i + 1] if v == v)
        out.append(part[len(part) // 2] if part and values[i] == values[i] else float('nan'))
    return out


def series(metrics, team, key, window=1):
    fps = 5.0
    xs, ys = [], []
    for frame in metrics['frames']:
        shape = frame.get(team)
        xs.append(frame['frame'] / fps)
        ys.append(shape[key] if shape else float('nan'))
    return xs, rolling_median(ys, window)


def main():
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    args = sys.argv[2:]
    window = 1
    if '--smooth' in args:
        window = int(args[args.index('--smooth') + 1])
        del args[args.index('--smooth'):args.index('--smooth') + 2]
    files = [Path(p) for p in args]
    data = [json.loads(p.read_text(encoding='utf-8')) for p in files]
    rows = (('centre_x', 'team centre along the pitch (m)'), ('depth', 'depth (m)'), ('width', 'width (m)'))
    figure, axes = plt.subplots(len(rows) + 1, len(data), figsize=(2.6 * len(data) + 1, 9), squeeze=False, sharex='col')
    for col, metrics in enumerate(data):
        axes[0][col].set_title(f"{metrics['clip']} ({metrics['camera']})", fontsize=9)
        for row, (key, label) in enumerate(rows):
            for team, colour in (('team_a', '#b5d800'), ('team_b', '#5b7fa6')):
                x, y = series(metrics, team, key, window)
                axes[row][col].plot(x, y, color=colour, label=team[-1].upper())
            axes[row][col].set_ylabel(label if col == 0 else '', fontsize=8)
        crowded = [f['crowded_share'] if f['crowded_share'] is not None else float('nan') for f in metrics['frames']]
        axes[len(rows)][col].plot([f['frame'] / 5.0 for f in metrics['frames']], crowded, color='#888')
        axes[len(rows)][col].set_ylim(0, 1)
        axes[len(rows)][col].set_ylabel('crowded share' if col == 0 else '', fontsize=8)
        axes[len(rows)][col].set_xlabel('seconds', fontsize=8)
    axes[0][0].legend(fontsize=7, loc='best')
    figure.suptitle('Team shape over short clips (pitch size is an estimate; not a tactical judgement)', fontsize=10)
    figure.tight_layout()
    figure.savefig(sys.argv[1], dpi=110)
    print('wrote', sys.argv[1])


if __name__ == '__main__':
    main()
