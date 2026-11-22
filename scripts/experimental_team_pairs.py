"""Classify explicitly labeled player boxes for research, not live analysis."""
import argparse
import json
from pathlib import Path
import sys

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.experimental_team_pair import ExperimentalTeamPair, shirt_histogram


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--weights', required=True, help='research weight JSON')
    parser.add_argument('--inputs', required=True, help='JSON with labeled support and player targets')
    args = parser.parse_args()
    data = json.loads(Path(args.inputs).read_text(encoding='utf8'))
    weights = json.loads(Path(args.weights).read_text(encoding='utf8'))

    def read_crop(item):
        image = cv2.imread(item['image'])
        if image is None:
            raise ValueError('Cannot read image: ' + item['image'])
        return image

    support = {}
    for team in ('home', 'away'):
        support[team] = []
        for item in data['support'][team]:
            hist = shirt_histogram(read_crop(item), item['box'])
            if hist is None:
                raise ValueError('Invalid labeled reference crop')
            support[team].append(hist)
    classifier = ExperimentalTeamPair(weights, support)
    result = []
    for item in data['targets']:
        team = classifier.classify(read_crop(item), item['box'], role=item.get('role'))
        result.append({'image': item['image'], 'box': item['box'], 'team': team})
    print(json.dumps({'experimental': True, 'players': result}, ensure_ascii=False))


if __name__ == '__main__':
    main()
