"""Offline simulated occlusion against annotated same-camera tracks.

The projection is an unvalidated manual-reference candidate. These errors are
relative to projected annotated box bottoms, not physical ground truth.
"""
import argparse, csv, json, math, statistics, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.experimental_map import ExperimentalMap
from app.main import project


def points(row, columns, cal):
    out = {}
    for i, tid in columns:
        try: x, y, w, h = map(float, row[i:i+4])
        except (ValueError, IndexError): continue
        if not all(math.isfinite(v) for v in (x,y,w,h)) or w <= 0 or h <= 0: continue
        px, py = project((x+w/2,y+h), cal)
        if px is not None and py is not None: out[tid] = {'id':tid,'x':px,'y':py}
    return out


def evaluate(files, calibration, horizons=(5,12,20), stride=10, max_age=0.8):
    cal = {**calibration, 'validated':True}  # research-only projection, never runtime validation
    dims = cal['field_size_m']
    results = {h:{'eligible':0,'predicted':0,'pred_error':[],'hold_error':[]} for h in horizons}
    for path in files:
        with Path(path).open(encoding='utf-8-sig', newline='') as handle:
            reader=csv.reader(handle); teams=next(reader); ids=next(reader); fields=next(reader); next(reader)
            columns=[(i,f'{teams[i]}:{ids[i]}') for i in range(1,len(fields),4)
                     if i+3<len(fields) and teams[i] in ('0','1') and ids[i]!='0']
            frames={int(r[0]):points(r,columns,cal) for r in reader if r and r[0]}
        for index in range(6, max(frames)-max(horizons)+1, stride):
            prior, current = frames.get(index-5,{}), frames.get(index,{})
            for horizon in horizons:
                later=frames.get(index+horizon,{})
                eligible=set(prior) & set(current) & set(later)
                results[horizon]['eligible']+=len(eligible)
                model=ExperimentalMap(max_age=max_age); model.update(list(prior.values()),0.,dims); model.update(list(current.values()),.2,dims)
                predicted=model.update([],.2+horizon/25,dims)
                for p in predicted:
                    tid=p['id']
                    if tid not in eligible: continue
                    target=later[tid]; last=current[tid]
                    err=math.hypot((p['x']-target['x'])*dims[0],(p['y']-target['y'])*dims[1])
                    hold=math.hypot((last['x']-target['x'])*dims[0],(last['y']-target['y'])*dims[1])
                    results[horizon]['predicted']+=1; results[horizon]['pred_error'].append(err); results[horizon]['hold_error'].append(hold)
    output={}
    for h,r in results.items():
        pred,hold=r.pop('pred_error'),r.pop('hold_error')
        output[str(h/25)]={**r,'coverage':r['predicted']/r['eligible'] if r['eligible'] else None,
            'pred_median_m':statistics.median(pred) if pred else None,'pred_p90_m':float(np.percentile(pred,90)) if pred else None,
            'hold_median_m':statistics.median(hold) if hold else None,'hold_p90_m':float(np.percentile(hold,90)) if hold else None}
    return output


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--calibration',type=Path,required=True); parser.add_argument('csv',type=Path,nargs='+')
    parser.add_argument('--horizons',type=int,nargs='+',default=[5,12,20], help='Occlusion durations in frames at 25fps')
    parser.add_argument('--max-age',type=float,default=0.8,help='Maximum prediction time for offline study only')
    args=parser.parse_args()
    config=json.loads(args.calibration.read_text(encoding='utf-8-sig'))
    if args.max_age <= 0 or not math.isfinite(args.max_age) or any(h <= 0 for h in args.horizons):
        parser.error('horizons and maximum age must be positive and finite')
    print(json.dumps(evaluate(args.csv,config['calibration'],tuple(args.horizons),max_age=args.max_age),indent=2))
