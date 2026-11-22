"""Fine-tune a person detector on the tiled dataset written by scripts/prepare_detector_data.py (runs on this computer only).

Usage: python scripts/finetune_person_detector.py <data.yaml> <base weights> <output folder> [--epochs 60] [--imgsz 768]

Anonymous Ultralytics analytics are switched off and no plots are made (plots would download a font). The best
weights are written to <output folder>/best.pt. The result is a research model: it is only worth using when it beats the base model on photos it
never saw (the evaluation scenes), see scripts/evaluate_person_detector.py.
"""
import argparse
import shutil
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('data')
    parser.add_argument('base')
    parser.add_argument('output')
    parser.add_argument('--epochs', type=int, default=60)
    parser.add_argument('--imgsz', type=int, default=768)
    parser.add_argument('--batch', type=int, default=16)
    args = parser.parse_args()
    from ultralytics import YOLO, settings
    settings.update({'sync': False})
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    model = YOLO(args.base)
    model.train(data=args.data, epochs=args.epochs, imgsz=args.imgsz, batch=args.batch, device=0, project=str(out.resolve()), name='run', exist_ok=True,
                plots=False, workers=0, patience=25, seed=0, verbose=False, amp=False)
    best = out / 'run' / 'weights' / 'best.pt'
    if best.is_file():
        shutil.copy(best, out / 'best.pt')
        print('wrote', out / 'best.pt')


if __name__ == '__main__':
    main()
