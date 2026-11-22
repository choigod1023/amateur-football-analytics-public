"""Join the tracks of one team that clearly continue each other, without asking anybody (only clear cases; the rest stays for the chain screen).

Usage: python scripts/auto_link_tracks.py <store> [--team B] [--gap 3.0] [--base 1.5] [--speed 3.0] [--dry]

The tracker loses a player for a moment (a crowd, a hidden leg) and starts a new track a second later a few metres away. A pair a -> b is joined only when ALL of this holds:
  * same team, b starts after a ended, with a gap of at most --gap seconds and no overlap;
  * b starts within --base + --speed * gap metres of the place where a ended (a player does not jump);
  * the positions of the two tracks are known and, if both tracks have a position line (defence, midfield, attack), the lines agree;
  * a is the best successor of b's kind and b the best predecessor of a (mutual), and the second best candidate on either side is at least twice as costly (no doubt about who continues whom);
  * nobody answered "different person" for the pair.
The pairs go to <store>/players/auto_links/<half>.json as {'same': [[a, b], ...], 'cost': {...}}. The store reads them like the 'same' answers of a person, except that a person's
"different person" answer wins. They are kept apart from the people's answers, so that deleting the file removes them all.
"""
import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.player_identity import LINE_OF  # noqa: E402


def cost(a, b, base, speed):
    gap = b['first'] - a['last']
    distance = math.hypot(a['last_pos'][0] - b['first_pos'][0], a['last_pos'][1] - b['first_pos'][1])
    return gap, distance, distance / (base + speed * gap) + gap / 10.0


def auto_pairs(tracks, team='B', max_gap=3.0, base=1.5, speed=3.0, different=()):
    """The pairs [a, b] of track ids that continue each other beyond doubt, and their cost."""
    own = [t for t in tracks if t['team'] == team and 'first_pos' in t and 'last_pos' in t]
    banned = {(min(a, b), max(a, b)) for a, b in different}
    options = {}                                                              # (a, b) -> cost
    for a in own:
        for b in own:
            if a['id'] == b['id'] or b['first'] < a['last']:
                continue
            gap, distance, c = cost(a, b, base, speed)
            if gap > max_gap or distance > base + speed * gap or (min(a['id'], b['id']), max(a['id'], b['id'])) in banned:
                continue
            la, lb = LINE_OF.get(a.get('slot')), LINE_OF.get(b.get('slot'))
            if la and lb and la != lb:
                continue
            options[(a['id'], b['id'])] = c
    after, before = {}, {}
    for (a, b), c in options.items():
        after.setdefault(a, []).append((c, b))
        before.setdefault(b, []).append((c, a))
    pairs = {}
    for (a, b), c in options.items():
        others_after = sorted(x for x, t in after[a] if t != b)
        others_before = sorted(x for x, t in before[b] if t != a)
        best_after = min(after[a])[1] == b
        best_before = min(before[b])[1] == a
        if best_after and best_before and (not others_after or others_after[0] >= 2 * c) and (not others_before or others_before[0] >= 2 * c):
            pairs[(a, b)] = round(c, 3)
    return pairs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('store')
    parser.add_argument('--team', default='B')
    parser.add_argument('--gap', type=float, default=3.0)
    parser.add_argument('--base', type=float, default=1.5)
    parser.add_argument('--speed', type=float, default=3.0)
    parser.add_argument('--dry', action='store_true')
    args = parser.parse_args()
    root = Path(args.store) / 'players'
    for folder in sorted(p for p in root.iterdir() if p.is_dir() and (p / 'index.json').is_file()):
        index = json.loads((folder / 'index.json').read_text(encoding='utf-8'))
        tracks = index['tracks']
        links_path = root / 'links' / f'{folder.name}.json'
        different = json.loads(links_path.read_text(encoding='utf-8')).get('different', []) if links_path.is_file() else []
        pairs = auto_pairs(tracks, args.team, args.gap, args.base, args.speed, different)
        mine = [t for t in tracks if t['team'] == args.team]
        parent = {t['id']: t['id'] for t in mine}

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x
        for a, b in pairs:
            parent[find(a)] = find(b)
        groups = len({find(t) for t in parent})
        print(f'{folder.name}: team {args.team}: {len(mine)} tracks -> {groups} after joining {len(pairs)} pairs')
        if not args.dry:
            out = root / 'auto_links'
            out.mkdir(exist_ok=True)
            (out / f'{folder.name}.json').write_text(json.dumps({'same': [list(p) for p in pairs], 'cost': {f'{a}-{b}': c for (a, b), c in pairs.items()}}, ensure_ascii=False), encoding='utf-8')


if __name__ == '__main__':
    main()
