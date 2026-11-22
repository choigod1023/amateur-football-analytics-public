"""Replay real boxes and decoded crops; audit contamination, not identity accuracy."""
import argparse, json, sys, time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('code');p.add_argument('trace');p.add_argument('video');p.add_argument('output');a=p.parse_args()
sys.path.insert(0,a.code)
import cv2
from app.temporal_reconnect import TemporalLinker, TEMPORAL_FEATURES
from app.identity_guard import _overlap
rows=[json.loads(x) for x in Path(a.trace).read_text(encoding='utf-8').splitlines()]
model={'features':TEMPORAL_FEATURES,'mean':[0.]*14,'scale':[1.]*14,'weights':[0.]*14,'bias':-30.,'threshold':.9,'ambiguity_margin':.15,'max_prediction_residual_heights':1.5}
link=TemporalLinker(model);cap=cv2.VideoCapture(a.video)
counts={'frames':0,'observations':0,'crowded_observations':0,'crowded_history_rows':0,'input_id_changes':0,'duplicate_output_ids':0}
start=time.perf_counter()
for r in rows:
    cap.set(cv2.CAP_PROP_POS_MSEC,r['time']*1000);ok,frame=cap.read()
    if not ok:raise RuntimeError('decode failure')
    tracks=r['source_tracks'];current={str(int(b[4])):b for b in tracks}
    crowded={k for k,b in current.items() if any(k!=j and _overlap(b[:4],c[:4])>=.35 for j,c in current.items())}
    mapping,_=link.update(r['time'],frame,tracks)
    counts['frames']+=1;counts['observations']+=len(current);counts['crowded_observations']+=len(crowded)
    counts['crowded_history_rows']+=sum(any(abs(h['time']-r['time'])<1e-8 for h in link.memory[k]['history']) for k in crowded)
    counts['input_id_changes']+=sum(k!=v for k,v in mapping.items())
    counts['duplicate_output_ids']+=len(mapping)-len(set(mapping.values()))
cap.release();counts['seconds']=time.perf_counter()-start
counts['limitation']='Scorer disabled identically to isolate evidence contamination. No identity accuracy or live FPS claim.'
Path(a.output).write_text(json.dumps(counts,indent=2));print(json.dumps(counts))

