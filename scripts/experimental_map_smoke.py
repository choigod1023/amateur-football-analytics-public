"""Local video smoke test, keeping reference coordinates out of trusted outputs."""
import argparse, json, sys, threading, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import main

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--config', type=Path, required=True)
parser.add_argument('--video', type=Path, required=True)
parser.add_argument('--model', type=Path, required=True)
parser.add_argument('--reference', type=Path, required=True)
args = parser.parse_args()
config = json.loads(args.config.read_text(encoding='utf-8-sig'))
config['model'] = str(args.model.resolve())
config['experimental_map'] = True
config['calibration']['camera_guard_reference'] = str(args.reference.resolve())
config['calibration']['camera_guard_feature_region'] = [[0,0],[6499,0],[6499,450],[0,450]]
main.validate_config(config)
main.manual_mode = bool(config.get('manual_player_assignments'))
main.stop_event.clear()
main.set_state(main.status, status='running')
worker = threading.Thread(target=main.run, args=(str(args.video.resolve()), config))
worker.start()
peak = 0; observations = 0; max_feedback = 0; trusted_positions = 0; samples = 0
try:
    deadline = time.monotonic()+12
    while worker.is_alive() and time.monotonic() < deadline:
        with main.lock:
            result = json.loads(json.dumps(main.analysis))
        exp = result.get('experimental_map') or {}
        ps = exp.get('players', [])
        if exp.get('status') == 'reference_unverified':
            samples += 1; observations += len(ps); peak=max(peak, len(ps))
        max_feedback=max(max_feedback, len(result.get('feedback',[])))
        trusted_positions=max(trusted_positions, sum(p.get('x') is not None for p in result.get('players',[])))
        time.sleep(.1)
finally:
    main.stop_event.set(); worker.join(15)
if worker.is_alive(): raise SystemExit('Analysis worker did not stop')
print(json.dumps({'experimental_samples':samples, 'max_experimental_people':peak,
                  'experimental_observations':observations, 'max_trusted_positions':trusted_positions,
                  'max_feedback':max_feedback, 'file_predictions_enabled':False,
                  'note':'Same-camera video; reference projection and tracked-player positions are unverified.'}))
if not samples or not peak or trusted_positions or max_feedback: raise SystemExit(1)
