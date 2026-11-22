"""Read-only observations of a MediaMTX recording directory.

File growth is not proof that a stream is complete or playable. No files are
opened for writing, deleted, moved, or finalized by this module.
"""
import argparse
import json
import shutil
import time
from pathlib import Path


def measure(directory):
    directory = Path(directory)
    if not directory.is_dir():
        raise ValueError('recording directory does not exist')
    sizes = {}
    for path in directory.glob('*.mp4'):
        try:
            if path.is_file():
                sizes[path.name] = path.stat().st_size
        except FileNotFoundError:
            # A concurrent rotation or external change must not abort a check.
            continue
    return {'sizes': sizes, 'free_bytes': shutil.disk_usage(directory).free}


def summarize(before, after, *, low_space_bytes=30 * 1024**3):
    old, new = before['sizes'], after['sizes']
    increased = sorted(name for name, size in new.items() if size > old.get(name, 0))
    created_empty = sorted(name for name in new if name not in old and new[name] == 0)
    decreased = sorted(name for name, size in new.items() if name in old and size < old[name])
    missing = sorted(set(old) - set(new))
    return {
        'growth_observed': bool(increased),
        'growing_files': increased,
        'new_empty_files': created_empty,
        'decreased_files': decreased,
        'missing_files': missing,
        'recording_file_count': len(new),
        'total_recording_bytes': sum(new.values()),
        'free_bytes': after['free_bytes'],
        'low_space': after['free_bytes'] < low_space_bytes,
        'note': 'No growth does not prove that recording stopped or that a file is finalized.',
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description='Observe recording growth without modifying files.')
    parser.add_argument('--directory', type=Path, required=True, help='Existing directory containing MP4 segments')
    parser.add_argument('--sample-seconds', type=float, default=5.)
    parser.add_argument('--low-space-gib', type=float, default=30.)
    args = parser.parse_args(argv)
    if not 0 < args.sample_seconds <= 60 or not 0 <= args.low_space_gib <= 1_000_000:
        parser.error('sample-seconds must be 0–60 and low-space-gib must be nonnegative')
    try:
        before = measure(args.directory)
        time.sleep(args.sample_seconds)
        after = measure(args.directory)
    except (OSError, ValueError) as exc:
        parser.exit(2, f'Recording check failed: {exc}\n')
    result = summarize(before, after, low_space_bytes=args.low_space_gib * 1024**3)
    result.update(directory=str(args.directory.resolve()), sample_seconds=args.sample_seconds)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
