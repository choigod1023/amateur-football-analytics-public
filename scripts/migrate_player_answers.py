"""Carry the answers of the player screen over to a new tracking of the same half (other track ids).

Usage: python scripts/migrate_player_answers.py <store> <half key> <old tracks.json> <new tracks.json> [--dry]

A track of the old tracking is found again in the new one by its boxes: for the frames where the old track has a row, the new track whose box overlaps it by IoU > 0.5 most often is
its successor (a joined track keeps the id of its first piece, so most ids stay, and the pieces that were joined into another track follow that track).
Rewritten in <store>/players: assign/<half>.json, links/<half>.json, rejects/<half>.json, auto_notes.json (the notes of that half) and card_photos.json is left alone (it names picture files).
  * two old tracks that now are one track with the same answer: one answer; with different players: the answer of the longer old track stays and the other is listed as a conflict;
  * a "same person" link whose two tracks are one now is dropped (nothing left to ask), a "different person" link whose two tracks are one now is kept out of the new links and listed;
  * an old track that has no successor loses its answer (listed).
The old files are copied to <name>.before-migration.json next to them.
"""
import argparse
import json
import shutil
from collections import Counter
from pathlib import Path


def iou(a, b):
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    if w <= 0 or h <= 0:
        return 0.0
    inter = w * h
    return inter / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter)


def successors(old_tracks, new_tracks, wanted, step=2):
    """{old id: new id or None} for the old ids in `wanted`."""
    at = {}
    for nid, rows in new_tracks.items():
        for r in rows:
            at.setdefault(r['frame'], []).append((nid, r['box']))
    result = {}
    for t in wanted:
        votes = Counter()
        for r in old_tracks.get(t, [])[::step]:
            for nid, box in at.get(r['frame'], []):
                if iou(box, r['box']) > 0.5:
                    votes[nid] += 1
        result[t] = votes.most_common(1)[0][0] if votes else None
    return result


def migrate_assign(assign, where, length):
    """-> (new assign, conflicts [(old id, player, kept player)], lost [old id])"""
    new, conflicts, lost = {}, [], []
    for old, player in sorted(assign.items(), key=lambda kv: -length.get(kv[0], 0)):          # the longer old track first
        target = where.get(old)
        if target is None:
            lost.append(old)
        elif target in new and new[target] != player:
            conflicts.append((old, player, new[target]))
        else:
            new[target] = player
    return new, conflicts, lost


def migrate_links(links, where):
    new = {'same': [], 'different': []}
    dropped_same, merged_different = [], []
    for a, b in links.get('same', []):
        x, y = where.get(a), where.get(b)
        if x is None or y is None or x == y:
            dropped_same.append((a, b))
        else:
            new['same'].append([x, y])
    for a, b in links.get('different', []):
        x, y = where.get(a), where.get(b)
        if x is None or y is None:
            continue
        if x == y:
            merged_different.append((a, b))
        else:
            new['different'].append([x, y])
    return new, dropped_same, merged_different


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('store')
    parser.add_argument('half')
    parser.add_argument('old')
    parser.add_argument('new')
    parser.add_argument('--dry', action='store_true')
    args = parser.parse_args()
    root = Path(args.store) / 'players'
    old = json.loads(Path(args.old).read_text(encoding='utf-8'))['tracks']
    new = json.loads(Path(args.new).read_text(encoding='utf-8'))['tracks']
    assign_path, links_path = root / 'assign' / f'{args.half}.json', root / 'links' / f'{args.half}.json'
    assign = json.loads(assign_path.read_text(encoding='utf-8')) if assign_path.is_file() else {}
    links = json.loads(links_path.read_text(encoding='utf-8')) if links_path.is_file() else {}
    notes_path = root / 'auto_notes.json'
    notes = json.loads(notes_path.read_text(encoding='utf-8')) if notes_path.is_file() else {}
    wanted = set(assign) | {t for k in ('same', 'different') for p in links.get(k, []) for t in p} | set(notes.get('notes', {}).get(args.half, {}))
    where = successors(old, new, wanted)
    length = {t: len(old.get(t, [])) for t in wanted}
    new_assign, conflicts, lost = migrate_assign(assign, where, length)
    new_links, dropped_same, merged_different = migrate_links(links, where)
    print(f'{args.half}: answers {len(assign)} -> {len(new_assign)}; conflicts {conflicts}; lost {lost}')
    print(f'{args.half}: links same {len(links.get("same", []))} -> {len(new_links["same"])} (dropped {len(dropped_same)}), different {len(links.get("different", []))} -> {len(new_links["different"])}; "different" pairs that are one track now: {merged_different}')
    if args.dry:
        return
    for path, value in ((assign_path, new_assign), (links_path, new_links)):
        if path.is_file():
            shutil.copy(path, path.with_suffix('.before-migration.json'))
        path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
    if notes_path.is_file():
        shutil.copy(notes_path, notes_path.with_suffix('.before-migration.json'))
        notes.setdefault('notes', {})[args.half] = {where.get(t) or t: v for t, v in notes.get('notes', {}).get(args.half, {}).items()}
        notes_path.write_text(json.dumps(notes, ensure_ascii=False, indent=1), encoding='utf-8')


if __name__ == '__main__':
    main()
