"""Research only: compare per-frame and temporal-median green pitch candidates.

Landmarks are used only for scoring. No candidate is installed or validated.
"""
import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.experimental_green_pitch import propose, score
from scripts.experimental_panorama_groundtruth import load


def median_candidate(candidates, minimum=3):
    """Aggregate complete four-corner candidates, without filling missing frames."""
    valid = [np.asarray(c, dtype=float) for c in candidates if c is not None]
    if len(valid) < minimum or any(c.shape != (4, 2) or not np.isfinite(c).all() for c in valid):
        return None
    return np.median(np.stack(valid), axis=0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('landmarks')
    parser.add_argument('videos', nargs='+')
    args = parser.parse_args()
    pairs = load(args.landmarks)
    output = []
    for filename in args.videos:
        capture = cv2.VideoCapture(filename)
        candidates = []
        samples = []
        for second in (2, 5, 8, 11, 14, 17, 20):
            capture.set(cv2.CAP_PROP_POS_MSEC, second * 1000)
            ok, frame = capture.read()
            candidate = propose(frame, field_support=True) if ok else None
            candidates.append(candidate)
            samples.append({'second': second, 'score': score(candidate, pairs) if candidate is not None else None})
        capture.release()
        combined = median_candidate(candidates)
        output.append({'video': Path(filename).name, 'samples': samples,
                       'temporal_median': score(combined, pairs) if combined is not None else None,
                       'successful_candidates': sum(c is not None for c in candidates)})
    print(json.dumps(output, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
