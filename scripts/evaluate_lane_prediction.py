"""Does a straight-line forecast of the passing lanes beat 'the lane stays as it is'?  (recorded matches, no labels needed)

Usage: python scripts/evaluate_lane_prediction.py <half spec> [<half spec> ...] <calibrations.json> [--horizons 1.0 1.5 2.0] [--step 1.0]
   half spec: "<name>|<tracks.json>|<camera>|<direction>|<offset>|<bg a,b,tx,ty>|<schedule>|<goals>"   (the same as scripts/build_match_report.py)

Every `step` seconds, while the team is in the opponent half, the most advanced player of the team is taken as the carrier and every lane from him to a teammate within 35 m
is judged at that moment and, again, `horizon` seconds later from the real positions (only lanes whose two players were seen at both moments). Measured:
  persistence   the lane is judged to stay as it is now                          (the baseline)
  forecast      the lane status computed on straight-line positions (app/lane_forecast.py)
and, for the lanes that are open now, how many stay open (the base rate) and how well each method picks the ones that close.
The positions are the tracked players only (6-9 per team) so 'open' means open among the players found.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from app.attack_options import LANE_CLEAR, MAX_PASS  # noqa: E402
from app.lane_forecast import forecast, lane_open  # noqa: E402


def actual_lane(by_frame, team, other, direction, frame, carrier, mate):
    mine = {t: (x * direction, y) for t, x, y in by_frame.get(frame, {}).get(team, [])}
    theirs = [(x * direction, y) for t, x, y in by_frame.get(frame, {}).get(other, [])]
    if carrier not in mine or mate not in mine or len(theirs) < 4:
        return None
    return lane_open(mine[carrier], mine[mate], theirs)[0]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('items', nargs='+', help='half specs and, last, the calibrations file')
    parser.add_argument('--horizons', type=float, nargs='+', default=[1.0, 1.5, 2.0])
    parser.add_argument('--step', type=float, default=1.0)
    parser.add_argument('--team', default='B')
    args = parser.parse_args()
    from build_match_report import load_half  # noqa: E402
    calibrations = json.loads(Path(args.items[-1]).read_text(encoding='utf-8'))
    other = 'A' if args.team == 'B' else 'B'
    rows = {h: [] for h in args.horizons}
    for spec in args.items[:-1]:
        half = load_half(spec, calibrations, args.team)
        fps, direction, by_frame = half['fps'], half['direction'], half['by_frame']
        frames = sorted(by_frame)
        step = max(1, int(round(args.step * fps)))
        for frame in range(frames[0] + int(fps * 2), frames[-1] - int(fps * 3), step):
            ours = [(t, x * direction, y) for t, x, y in by_frame.get(frame, {}).get(args.team, [])]
            if len(ours) < 6 or len(by_frame.get(frame, {}).get(other, [])) < 6:
                continue
            carrier, lead = max(ours, key=lambda p: p[1])[0], max(p[1] for p in ours)
            if lead < 0:
                continue                                       # the team is in its own half: no attack to speak of
            for horizon in args.horizons:
                later = frame + int(round(horizon * fps))
                for lane in forecast(by_frame, args.team, other, direction, fps, frame, carrier, horizon):
                    truth = actual_lane(by_frame, args.team, other, direction, later, carrier, lane['track'])
                    if truth is not None:
                        rows[horizon].append((lane['open_now'], lane['open_later'], truth))
    for horizon in args.horizons:
        data = rows[horizon]
        n = len(data)
        if not n:
            print(f'horizon {horizon} s: no lanes')
            continue
        persist = sum(1 for now, _f, truth in data if now == truth) / n
        forecasted = sum(1 for _n, fc, truth in data if fc == truth) / n
        open_now = [(fc, truth) for now, fc, truth in data if now]
        stay = sum(1 for _fc, truth in open_now if truth) / max(1, len(open_now))
        closing = [(fc, truth) for fc, truth in open_now if not truth]
        caught = sum(1 for fc, _t in closing if not fc) / max(1, len(closing))
        false_alarm = sum(1 for fc, truth in open_now if not fc and truth) / max(1, sum(1 for fc, _t in open_now if not fc))
        print(f'horizon {horizon:.1f} s: {n} lanes | status right: persistence {persist:.1%}, forecast {forecasted:.1%} | of {len(open_now)} lanes open now {stay:.1%} stay open; '
              f'forecast caught {caught:.1%} of the {len(closing)} that closed, {false_alarm:.1%} of its "closing" calls were wrong')


if __name__ == '__main__':
    main()
