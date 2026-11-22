"""Export explicitly reviewed crops for a future classifier, not detector GT.

Partially annotated full frames must never be exported as complete YOLO labels:
unmarked people would become false-negative background. Duplicate and unknown
labels are omitted. Match-disjoint train/test assignment is a separate step.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

import cv2


CLASSES = {'player', 'goalkeeper', 'referee', 'spectator', 'shadow'}


def export(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if not source.is_dir():
        raise ValueError('label directory does not exist')
    if destination.exists():
        raise ValueError('output directory already exists')
    if destination == source or source in destination.parents:
        raise ValueError('output must be outside the label directory')
    destination.mkdir(parents=True)
    rows, skipped = [], {}
    for path in sorted(source.glob('*.json')):
        try:
            label = json.loads(path.read_text(encoding='utf-8'))
            role = label.get('role')
            if role not in CLASSES:
                skipped[role or 'missing_role'] = skipped.get(role or 'missing_role', 0) + 1
                continue
            name = label.get('image')
            if not isinstance(name, str) or Path(name).name != name:
                raise ValueError('invalid image name')
            image_path = (source / name).resolve()
            if image_path.parent != source:
                raise ValueError('image outside label directory')
            image = cv2.imread(str(image_path))
            if image is None:
                raise ValueError('image not readable')
            bbox = label.get('bbox_image_norm')
            if not isinstance(bbox, list) or len(bbox) != 4 or not all(type(v) in (int, float) and math.isfinite(v) and 0 <= v <= 1 for v in bbox):
                raise ValueError('invalid box')
            x1,y1,x2,y2 = bbox
            if x1 >= x2 or y1 >= y2:
                raise ValueError('empty box')
            height,width = image.shape[:2]
            left,top,right,bottom = int(x1*width),int(y1*height),math.ceil(x2*width),math.ceil(y2*height)
            crop = image[top:bottom,left:right]
            if not crop.size:
                raise ValueError('empty crop')
            # A label ID plus its source avoids silently overwriting crops.
            ident = hashlib.sha256(str(path).encode('utf-8')).hexdigest()[:24]
            target = destination / f'{ident}.png'
            if not cv2.imwrite(str(target), crop):
                raise ValueError('crop write failed')
            rows.append({'crop': target.name, 'role': role, 'source_label': path.name,
                         'source_image': name, 'bbox_image_norm': bbox,
                         'source_provenance': label.get('source_provenance', {}),
                         'split': 'unassigned'})
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            skipped['invalid'] = skipped.get('invalid', 0) + 1
    (destination / 'manifest.json').write_text(json.dumps({
        'purpose': 'reviewed object crops for classification; not complete-frame detector labels',
        'warning': 'Assign train/test by distinct match before evaluating; shadow crops may contain unlabeled people.',
        'items': rows, 'skipped': skipped,
    }, ensure_ascii=False, indent=2), encoding='utf-8')
    return {'exported': len(rows), 'skipped': skipped}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--labels', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(export(args.labels, args.output), ensure_ascii=False))


if __name__ == '__main__':
    main()
