"""Offline two-person crossing hypothesis check; never silently rewrites live IDs.

Needs three clean observations on BOTH sides. Any use online must buffer until
all after observations arrive; review means keep identity unconfirmed, not merge.
"""
import numpy as np
from .temporal_reconnect import aggregate


def _distance(a,b):
    return float(np.mean([np.sqrt(max(0.,1-float(np.sqrt(x*y).sum()))) for x,y in zip(a,b)]))


def decide_crossing(before,after,appearance_margin=.08,motion_margin=.15):
    result={'decision':'review','reason':'insufficient_clean_sequence','identity_verified':False,
            'appearance_costs':None,'motion_costs':None,'available_at':None}
    if len(before)!=2 or len(after)!=2 or any(len(s)<3 for s in before+after):return result
    if any(r.get('crowded',False) for s in before+after for r in s):return result
    if max(r['time'] for s in before for r in s)>=min(r['time'] for s in after for r in s):return result
    stats=[aggregate(s) for s in before+after]
    if any(a is None for a in stats):return result
    result['available_at']=max(r['time'] for s in after for r in s)
    # Reject unstable appearance rather than learning mixed-shirt prototypes.
    if any(a[3]>.15 for a in stats):result['reason']='unstable_appearance';return result
    appearance=np.zeros((2,2));motion=np.zeros((2,2))
    for i in range(2):
        for j in range(2):
            a,b=stats[i],stats[j+2]
            appearance[i,j]=_distance(a[0],b[0])
            ba,bb=before[i][-1]['box'],after[j][0]['box']
            height=max(1.,(ba[3]-ba[1]+bb[3]-bb[1])/2)
            residuals=[]
            for k,r in enumerate(after[j]):
                dt=r['time']-before[i][-1]['time']
                residuals.append(np.linalg.norm(a[1][-1]+a[2]*dt-b[1][k])/height)
            for k,r in enumerate(before[i]):
                dt=after[j][0]['time']-r['time']
                residuals.append(np.linalg.norm(b[1][0]-b[2]*dt-a[1][k])/height)
            motion[i,j]=float(np.median(residuals))
    ac=[float(appearance[0,0]+appearance[1,1]),float(appearance[0,1]+appearance[1,0])]
    mc=[float(motion[0,0]+motion[1,1]),float(motion[0,1]+motion[1,0])]
    result.update(appearance_costs=ac,motion_costs=mc)
    if abs(ac[0]-ac[1])<appearance_margin:result['reason']='appearance_ambiguous';return result
    if abs(mc[0]-mc[1])<motion_margin:result['reason']='motion_ambiguous';return result
    choice=int(ac[1]<ac[0])
    if choice!=int(mc[1]<mc[0]):result['reason']='appearance_motion_disagree';return result
    if mc[choice]>1.5:result['reason']='motion_residual_large';return result
    result.update(decision='swap_candidate' if choice else 'keep_candidate',reason='independent_evidence_agrees')
    return result
