"""Read-only report of the git worktrees: which ones hold nothing that the chain top (or main) does not already hold.

Usage: python scripts/list_worktrees.py [--top <branch or commit>] [--main <commit>] [--json <file>]

For every worktree it prints the branch, whether the working tree has uncommitted changes, and whether its HEAD is an ancestor of the chosen top (so that removing the worktree
loses no commit). Nothing is removed: the list is only the basis for a decision. A worktree with uncommitted changes is never a removal candidate.
"""
import argparse
import json
import subprocess
from pathlib import Path


def run(*args, cwd=None):
    return subprocess.run(args, capture_output=True, text=True, cwd=cwd)


def worktrees():
    entries, current = [], {}
    for line in run('git', 'worktree', 'list', '--porcelain').stdout.splitlines():
        if not line.strip():
            if current:
                entries.append(current)
            current = {}
            continue
        key, _, value = line.partition(' ')
        current[key] = value
    if current:
        entries.append(current)
    return entries


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--top', default='HEAD')
    parser.add_argument('--main', default='')
    parser.add_argument('--json')
    args = parser.parse_args()
    top = run('git', 'rev-parse', args.top).stdout.strip()
    rows = []
    for w in worktrees():
        path, head = w.get('worktree', ''), w.get('HEAD', '')
        dirty = bool(run('git', 'status', '--porcelain', cwd=path).stdout.strip()) if Path(path).is_dir() else None
        in_top = run('git', 'merge-base', '--is-ancestor', head, top).returncode == 0 if head else None
        in_main = run('git', 'merge-base', '--is-ancestor', head, args.main).returncode == 0 if args.main and head else None
        rows.append({'path': path, 'branch': w.get('branch', '').replace('refs/heads/', ''), 'head': head[:7], 'dirty': dirty, 'in_top': in_top, 'in_main': in_main, 'missing': not Path(path).is_dir()})
    safe = [r for r in rows if r['dirty'] is False and r['in_top']]
    print(f'{len(rows)} worktrees: {len(safe)} are clean and fully contained in {args.top}; {sum(1 for r in rows if r["dirty"])} have uncommitted changes; {sum(1 for r in rows if r["missing"])} are missing on disk; '
          f'{sum(1 for r in rows if r["dirty"] is False and not r["in_top"])} are clean but hold commits that {args.top} lacks')
    if args.json:
        Path(args.json).write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding='utf-8')


if __name__ == '__main__':
    main()
