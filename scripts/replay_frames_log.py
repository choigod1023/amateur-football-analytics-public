"""Replay the frame logs of live runs (run_live_feedback.py --frames-log) through the alert rules, with variants of the rules that make the alerts less sensitive to detector flicker.

python scripts/replay_frames_log.py <folder with one sub folder e3_<condition> per condition, each holding frames.jsonl and alerts.jsonl> --reference reference [--output result.json]

* `default` must give exactly the alerts of the live run (the check that the replay is faithful).
* Variants (research only, none of them is in the live rules except `tolerant_box`, which is an option that is off):
    hold          seconds a player the detector missed stays where he was seen last (live: 1 s)
    tolerant_box  a second in which the box count dipped does not stop a box_attack
    line_k        the back line is the mean depth of the K deepest outfield players (live: the mean of the deepest group after cutting the depths at the two largest gaps,
                  which jumps when one player is not seen)
    smooth        radius in seconds of the median that smooths the back line before a line_drop or a run is read from it (live: 3)
    relink        a track that ends and a new track that starts within 1 s and 3 m are one player for the run rule (live: a new track number starts a new path)
* Robustness of a variant = how many of the alerts the variant gives on the undamaged video (reference) it also gives, within +-10 s and of the same kind, on each degraded stream
  (recall) and how many of the alerts on the degraded stream were also on the reference (precision). This measures stability, NOT whether an alert is right:
  that needs the judgements of the coach (an alert that nobody sees is not necessarily good).
"""
import argparse, json, math, statistics, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app.live_feedback as live  # noqa: E402
from app.goalkeeper import without_goalkeeper  # noqa: E402
from app.live_feedback import LiveAnalyzer, HOLD_SECONDS, SAME_PERSON  # noqa: E402

WINDOW = 10.0
SKIP = ('heartbeat', 'no_input', 'input_back', 'camera_moved', 'camera_back')
ORIGINAL_SMOOTH = live.smooth


def relink(paths, fps, gap_seconds=1.0, distance=3.0):
    """{track: [(frame, u, y)]} -> the same with a track that ends and a track that starts close by in time and place joined into one path."""
    tracks = sorted(((list(p)[0][0], list(p)) for p in paths.values() if p), key=lambda a: a[0])
    chains = []
    for first, points in tracks:
        best = None
        for chain in chains:
            last = chain[-1]
            gap = first - last[0]
            if 0 < gap <= gap_seconds * fps:
                d = math.hypot(points[0][1] - last[1], points[0][2] - last[2])
                if d <= distance and (best is None or d < best[0]):
                    best = (d, chain)
        if best:
            best[1].extend(points)
        else:
            chains.append(list(points))
    return {i: chain for i, chain in enumerate(chains)}


class Variant(LiveAnalyzer):
    hold = HOLD_SECONDS
    line_k = 0
    smooth_radius = 3
    relink_tracks = False

    def held(self, name, sample, seconds=None, apart=SAME_PERSON):
        return super().held(name, sample, self.hold if seconds is None else seconds, apart)

    def _close_second(self, second, team, other):
        super()._close_second(second, team, other)
        if not self.line_k:
            return
        for name, opponents, focus in (('team', other, self.direction), ('other', team, -self.direction)):
            metrics = self.series[name].get(second)
            if not metrics:
                continue
            depths, _ = without_goalkeeper([-(x * focus) for _, x, _y in opponents], key=lambda d: d)
            if len(depths) >= self.line_k:
                metrics['opponent_back_line'] = -(sum(depths[:self.line_k]) / self.line_k)

    def _check(self, t, second):
        saved = self.paths
        if self.relink_tracks:
            self.paths = {name: relink(paths, self.fps) for name, paths in saved.items()}
        live.smooth = (lambda values, radius=self.smooth_radius: ORIGINAL_SMOOTH(values, radius)) if self.smooth_radius != 3 else ORIGINAL_SMOOTH
        try:
            return super()._check(t, second)
        finally:
            self.paths = saved
            live.smooth = ORIGINAL_SMOOTH


# name: (hold seconds, tolerant box, line_k, smooth radius, relink)
VARIANTS = {'default': (1.0, False, 0, 3, False),
            'tolerant_box': (1.0, True, 0, 3, False),
            'tb+line_k3': (1.0, True, 3, 3, False),
            'tb+line_k4': (1.0, True, 4, 3, False),
            'tb+line_k3+smooth5': (1.0, True, 3, 5, False),
            'tb+relink': (1.0, True, 0, 3, True),
            'tb+line_k3+relink': (1.0, True, 3, 3, True),
            'tb+line_k3+smooth5+relink': (1.0, True, 3, 5, True)}


def read_frames(path):
    header, rows = None, []
    for line in Path(path).read_text(encoding='utf-8').splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if record.get('type') == 'header':
            header = header or record
        else:
            rows.append(record)
    return header, rows


def replay(header, rows, setting):
    hold, tolerant, line_k, radius, relinked = setting

    class V(Variant):
        pass
    V.hold, V.line_k, V.smooth_radius, V.relink_tracks = hold, line_k, radius, relinked
    analyzer = V(header['direction'], header['pitch_length'], header['pitch_width'], header['fps'], tolerant_box=tolerant)
    out = []
    for row in rows:
        for alert in analyzer.update(row['t'], [tuple(p) for p in row['team']], [tuple(p) for p in row['other']]):
            out.append((alert['kind'], round(alert['time'], 1)))
    return out


def live_alerts(path):
    out = []
    for line in Path(path).read_text(encoding='utf-8').splitlines():
        if line.strip():
            row = json.loads(line)
            if row.get('type') not in SKIP and row.get('kind') not in SKIP:
                out.append((row['kind'], round(float(row['time']), 1)))
    return out


def matches(first, second, window=WINDOW):
    pairs = sorted((abs(a[1] - b[1]), i, j) for i, a in enumerate(first) for j, b in enumerate(second) if a[0] == b[0] and abs(a[1] - b[1]) <= window)
    used_a, used_b, count = set(), set(), 0
    for _, i, j in pairs:
        if i not in used_a and j not in used_b:
            used_a.add(i); used_b.add(j); count += 1
    return count


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('folder', type=Path); p.add_argument('--reference', default='reference'); p.add_argument('--output', type=Path)
    p.add_argument('--prefix', default='e3_', help='folders are <prefix><condition>')
    args = p.parse_args()
    conditions = sorted(d.name[len(args.prefix):] for d in args.folder.iterdir() if d.is_dir() and d.name.startswith(args.prefix) and (d / 'frames.jsonl').exists())
    logs = {c: read_frames(args.folder / f'{args.prefix}{c}' / 'frames.jsonl') for c in conditions}
    result = {'conditions': conditions, 'replay_faithful': {}, 'variants': {}}
    for c in conditions:                                                      # the default replay against the alerts the live run wrote
        header, rows = logs[c]
        live_list = live_alerts(args.folder / f'{args.prefix}{c}' / 'alerts.jsonl')
        again = replay(header, rows, VARIANTS['default'])
        result['replay_faithful'][c] = {'live': len(live_list), 'replay': len(again), 'same': sorted(live_list) == sorted(again)}
    reference_default = replay(*logs[args.reference], VARIANTS['default'])
    minutes = (logs[args.reference][1][-1]['t'] - logs[args.reference][1][0]['t']) / 60
    for name, setting in VARIANTS.items():
        alerts = {c: replay(*logs[c], setting) for c in conditions}
        ref = alerts[args.reference]
        rows, by_kind = {}, {}
        for c in conditions:
            if c == args.reference:
                continue
            m = matches(ref, alerts[c])
            rows[c] = {'alerts': len(alerts[c]), 'matched': m, 'recall': round(m / len(ref), 3) if ref else None, 'precision': round(m / len(alerts[c]), 3) if alerts[c] else None}
            for kind in sorted({k for k, _ in ref}):
                a, b = [x for x in ref if x[0] == kind], [x for x in alerts[c] if x[0] == kind]
                got = by_kind.setdefault(kind, {'reference': len(a), 'matched': 0, 'candidate': 0})
                got['matched'] += matches(a, b); got['candidate'] += len(b)
        recalls = [r['recall'] for r in rows.values() if r['recall'] is not None]; precisions = [r['precision'] for r in rows.values() if r['precision'] is not None]
        result['variants'][name] = {'setting': {'hold_s': setting[0], 'tolerant_box': setting[1], 'line_k': setting[2], 'smooth_radius': setting[3], 'relink': setting[4]},
                                    'reference_alerts': len(ref), 'reference_kinds': {k: v['reference'] for k, v in by_kind.items()}, 'reference_alerts_per_minute': round(len(ref) / max(1e-6, minutes), 2),
                                    'mean_recall': round(statistics.mean(recalls), 3) if recalls else None, 'mean_precision': round(statistics.mean(precisions), 3) if precisions else None,
                                    'overlap_with_default_reference': round(matches(reference_default, ref) / max(1, len(reference_default)), 3),
                                    'recall_by_kind_over_conditions': {k: round(v['matched'] / max(1, v['reference'] * len(rows)), 3) for k, v in by_kind.items()}, 'per_condition': rows}
    for c, v in result['replay_faithful'].items():
        print(f'replay check {c:14s} live={v["live"]} replay={v["replay"]} same={v["same"]}')
    for name, v in result['variants'].items():
        print(f"{name:27s} ref={v['reference_alerts']} {v['reference_kinds']} mean_recall={v['mean_recall']} mean_precision={v['mean_precision']} overlap_default={v['overlap_with_default_reference']} by_kind={v['recall_by_kind_over_conditions']}")
    if args.output:
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding='utf-8')


if __name__ == '__main__':
    main()
