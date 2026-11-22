"""Sample two manually selected jersey patches without altering project config."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import cv2
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.team_reference import build_references


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('image', type=Path, help='Original, unresized frame image')
    p.add_argument('--home', type=int, nargs=4, required=True, metavar=('X1','Y1','X2','Y2'))
    p.add_argument('--away', type=int, nargs=4, required=True, metavar=('X1','Y1','X2','Y2'))
    args = p.parse_args()
    try:
        data = args.image.read_bytes()
        frame = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
        result = build_references(frame, args.home, args.away)
        result.update(frame_size_px=[frame.shape[1], frame.shape[0]], frame_sha256=hashlib.sha256(data).hexdigest(),
                      note='Manual shirt references only; never automatically marks team classification validated.')
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    except (OSError, ValueError) as exc:
        p.exit(2, f'Unable to sample shirt references: {exc}\n')


if __name__ == '__main__':
    main()
