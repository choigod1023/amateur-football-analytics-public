"""Separate the tracker's estimated box from its current matched measurement.

Ultralytics STrack.result returns xyxy, ID, score, class, detection index.
The index refers to the exact detection array supplied to that update. This
helper changes only a COPY used by downstream observations, never tracker state.
It cannot establish that a detection is a real/full person or the ID is correct.
"""
from collections import Counter
import numpy as np


def current_detection_boxes(tracked, detections, mode='all'):
    if mode not in ('all','shape-outliers'):
        raise ValueError('Unknown observation box mode')
    rows=np.asarray(tracked,dtype=float)
    found=np.asarray(detections,dtype=float)
    if rows.size==0:
        return np.empty((0,8),dtype=float),[]
    if rows.ndim!=2 or found.ndim!=2:
        raise ValueError('Expected tracker and exact current detection matrices')
    indexes=[]
    for row in rows:
        idx=row[7] if len(row)>=8 else float('nan')
        indexes.append(int(idx) if np.isfinite(idx) and idx==int(idx) else None)
    counts=Counter(i for i in indexes if i is not None)
    accepted=[];diagnostics=[]
    for number,(row,idx) in enumerate(zip(rows,indexes)):
        reason=None
        if len(row)!=8:
            reason='unsupported_tracker_layout'
        elif not np.isfinite(row).all() or row[4]!=int(row[4]):
            reason='invalid_tracker_metadata'
        elif idx is None:
            reason='invalid_detection_index'
        elif idx<0 or idx>=len(found):
            reason='detection_index_out_of_range'
        elif counts[idx]!=1:
            reason='duplicate_detection_assignment'
        elif found.shape[1]<4 or not np.isfinite(found[idx,:4]).all():
            reason='invalid_detection_box'
        elif found[idx,2]<=found[idx,0] or found[idx,3]<=found[idx,1]:
            reason='invalid_detection_box'
        diagnostic={'row':number,'detection_index':idx,'accepted':reason is None}
        if len(row)>=5 and np.isfinite(row[4]):diagnostic['track_id']=float(row[4])
        if reason:
            diagnostic['reason']=reason
        else:
            observed=row.copy()
            track_size=row[2:4]-row[:2]
            detection_size=found[idx,2:4]-found[idx,:2]
            # Experimental shape guard only, not evidence that the detection is
            # a whole person or that the tracker matched the correct person.
            ratio=float(max(np.max(track_size/detection_size),np.max(detection_size/track_size))) if np.all(track_size>0) else None
            replace=mode=='all' or ratio is None or ratio>2.
            if replace:observed[:4]=found[idx,:4]
            accepted.append(observed)
            diagnostic['tracker_box']=row[:4].tolist()
            diagnostic['current_detection_box']=found[idx,:4].tolist()
            diagnostic['observed_box']=observed[:4].tolist()
            diagnostic['shape_ratio']=ratio
            diagnostic['box_basis']='current_detection' if replace else 'tracker_estimate'
        diagnostics.append(diagnostic)
    return np.asarray(accepted,dtype=float).reshape(-1,8),diagnostics
