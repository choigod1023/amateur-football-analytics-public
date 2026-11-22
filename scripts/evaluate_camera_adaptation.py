"""Known-warp checks on real imagery plus unlabelled real camera samples.

Known synthetic geometry is not evidence of accuracy on real moved cameras.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.camera_adaptation import CameraAdaptation, _project


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('work', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    store = args.work / 'human-labels/public-own-match-review-20261111'
    calibration_file = store / 'calibration/calibrations.json'
    before = hashlib.sha256(calibration_file.read_bytes()).hexdigest()
    records = json.loads(calibration_file.read_text(encoding='utf-8'))
    record = records['cam3']
    ref = cv2.imread(str(store / 'pending' / (record['ref_token'] + '.jpg')))
    h,w = ref.shape[:2]
    polygon = cv2.convexHull(np.float32([[p['x']*w, p['y']*h] for p in record['points']])).reshape(-1,2)
    transforms = {'identity': np.eye(3), 'translation': np.array([[1,0,22],[0,1,-9],[0,0,1.]]),
                  'zoom_rotation': np.vstack([cv2.getRotationMatrix2D((w/2,h/2),2,1.08),[0,0,1]]),
                  'perspective': cv2.getPerspectiveTransform(np.float32([[0,0],[w,0],[w,h],[0,h]]),
                      np.float32([[35,12],[w-30,0],[w,h-10],[0,h]]))}
    cases = [(name, cv2.warpPerspective(ref, matrix, (w,h)), matrix) for name,matrix in transforms.items()]
    cases += [('blank', np.zeros_like(ref), None)]
    ref1 = cv2.imread(str(store / 'pending' / (records['cam1']['ref_token']+'.jpg')))
    cases += [('other_saved_angle_cam1', ref1, None)]
    for t in [1800,2100,2600]:
        frame=cv2.imread(str(args.work / 'camera-adaptation-eval-20261113' / f'frame-{t}.jpg'))
        if frame is not None: cases.append((f'recorded_{t}',frame,None))
    probe = np.float32([[x,y] for x in np.linspace(polygon[:,0].min(),polygon[:,0].max(),15)
                        for y in np.linspace(polygon[:,1].min(),polygon[:,1].max(),8)
                        if cv2.pointPolygonTest(polygon,(float(x),float(y)),False)>=0])
    engine=CameraAdaptation()
    rows=[]
    for name,frame,truth in cases:
        start=time.perf_counter();result=engine.fit(ref,frame,polygon);elapsed=(time.perf_counter()-start)*1000
        item={'case':name,'status':result['status'],'reason':result['reason'],'latency_ms':round(elapsed,1),
              'holdout_p90_px':result.get('holdout_p90_px'),'known_warp':truth is not None,'metric_accuracy_verified':False}
        if truth is not None and result['status']=='ready':
            current=_project(probe,truth);back=_project(current,np.asarray(result['current_to_reference']))
            error=np.linalg.norm(probe-back,axis=1)
            item.update(probe_count=len(probe),true_pixel_error_median=float(np.median(error)),true_pixel_error_p90=float(np.percentile(error,90)))
        rows.append(item)
    report={'reference':'cam3','results':rows,'real_world_metres_error':None,
            'pitch_dimensions':{k:v['pitch'] for k,v in records.items()},
            'limitations':['No human ground truth for moved-camera samples. Ready is registration acceptance, not proven metre accuracy.',
                           'Known image warp does not simulate 3D parallax, rolling shutter or lens changes.',
                           'Reference cam1/cam3 widths differ; real field dimensions still need confirmation.'],
            'calibration_unchanged':hashlib.sha256(calibration_file.read_bytes()).hexdigest()==before}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x',encoding='utf-8') as f:json.dump(report,f,ensure_ascii=False,indent=2)
    print(json.dumps(rows,ensure_ascii=False))


if __name__=='__main__': main()
