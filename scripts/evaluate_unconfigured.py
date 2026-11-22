"""Measure real-video abstention when no team or calibration data is supplied."""
import argparse
import json
from pathlib import Path
import statistics
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import main


def main_cli():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', required=True, help='Local YOLO weights')
    parser.add_argument('clips', nargs='+', help='Short local clips to evaluate sequentially')
    args = parser.parse_args()
    original = main.set_state
    results = []
    try:
        for clip in args.clips:
            samples = []

            def capture(target, **values):
                original(target, **values)
                if target is main.analysis and values.get('timestamp'):
                    samples.append({'persons': len(values['players']),
                                    'team': sum(p['team'] != 'unknown' for p in values['players']),
                                    'localized': sum(p['x'] is not None for p in values['players']),
                                    'feedback': bool(values['feedback']),
                                    'diagnostics': values['coaching_diagnostics']})

            main.set_state = capture
            main.stop_event.clear()
            main.run(str(Path(clip).resolve()), {'model': str(Path(args.model).resolve()),
                     'tiled_detection': 'auto', 'formation_observation': True})
            results.append({'clip': Path(clip).name, 'status': main.status['status'], 'frames': len(samples),
                            'mean_persons': round(statistics.mean(s['persons'] for s in samples), 2) if samples else None,
                            'known_team_observations': sum(s['team'] for s in samples),
                            'localized_observations': sum(s['localized'] for s in samples),
                            'feedback_frames': sum(s['feedback'] for s in samples),
                            'diagnostics': samples[-1]['diagnostics'] if samples else None})
    finally:
        main.set_state = original
    print(json.dumps({'input': 'unconfigured; no teams, calibration, or ground truth', 'results': results}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main_cli()
