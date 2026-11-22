"""Causal segmentation of suspicious tracker-ID discontinuities, not re-identification.

Appearance alone cannot distinguish teammates. A new segment requires independent
appearance and box-motion/scale evidence. The module never fills a missing person
or asserts that two different raw tracker IDs belong to the same player.
"""
import math

import cv2
import numpy as np


def _descriptor(frame, box):
    h, w = frame.shape[:2]
    x1, y1, x2, y2 = map(float, box)
    bw, bh = x2-x1, y2-y1
    if not np.isfinite(box).all() or bw <= 0 or bh <= 0:
        return None
    left, right = max(0, int(x1+.15*bw)), min(w, int(x2-.15*bw)+1)
    top, bottom = max(0, int(y1+.15*bh)), min(h, int(y1+.65*bh)+1)
    patch = frame[top:bottom, left:right]
    if patch.size < 36:
        return None
    hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)
    parts = []
    for channel, bins, high in ((0,12,180),(1,8,256),(2,8,256)):
        histogram = np.histogram(hsv[:,:,channel], bins=bins, range=(0,high))[0].astype(float)+.01
        parts.append(histogram/histogram.sum())
    return parts


def _appearance(a, b):
    return float(np.sqrt(np.mean([max(0., 1.-np.sqrt(x*y).sum()) for x,y in zip(a,b)])))


def _overlap(a, b):
    ix = max(0., min(a[2],b[2])-max(a[0],b[0]))
    iy = max(0., min(a[3],b[3])-max(a[1],b[1]))
    minimum = min(max(0.,a[2]-a[0])*max(0.,a[3]-a[1]),max(0.,b[2]-b[0])*max(0.,b[3]-b[1]))
    return ix*iy/max(minimum,1.)


class IdentityGuard:
    def __init__(self, max_gap=.6, ttl=30., first_segment_id=1_000_000):
        self.max_gap, self.ttl = max_gap, ttl
        self.next_id = first_segment_id
        self.tracks = {}

    def update(self, t, frame, tracked):
        """Return (float64 rows, diagnostic events), IDs in column4 of Nx5+ rows.

        Strong colour+scale/motion breaks receive a new *segment* ID. Events with
        action='review' retain the ID and must not be counted as a split. Overlapping
        observations keep their current segment but do not update appearance.
        Geometry/appearance evidence and raw IDs are retained in events for audit.
        """
        rows = np.array(tracked, dtype=np.float64, copy=True)
        if rows.size == 0:
            rows = rows.reshape(0, rows.shape[-1] if rows.ndim == 2 else 5)
        if rows.ndim != 2 or rows.shape[1] < 5 or not math.isfinite(t):
            raise ValueError('Finite time and Nx5+ tracked rows required')
        self.tracks = {key:value for key,value in self.tracks.items() if 0 <= t-value['time'] <= self.ttl}
        events = []
        raw_ids = {int(row[4]) for row in rows if np.isfinite(row[4])}
        for i, row in enumerate(rows):
            box = row[:4]
            if not np.isfinite(row[:5]).all():
                continue
            raw_id = int(row[4])
            descriptor = _descriptor(frame, box)
            prior = self.tracks.get(raw_id)
            segment = prior['segment'] if prior else raw_id
            crowded = any(j != i and _overlap(box,other[:4]) >= .35 for j,other in enumerate(rows))
            distance = scale = displacement = None
            if prior and descriptor is not None and prior['appearance'] is not None and 0 < t-prior['time'] <= self.max_gap:
                old = prior['box']; old_h, new_h = old[3]-old[1],box[3]-box[1]
                if min(old_h,new_h) > 0:
                    distance = _appearance(prior['appearance'],descriptor)
                    scale = float(max(old_h,new_h)/min(old_h,new_h))
                    displacement = float(np.linalg.norm((box[:2]+box[2:])/2-(old[:2]+old[2:])/2)/min(old_h,new_h))
                    old_foot = np.array([(old[0]+old[2])/2, old[3]])
                    new_foot = np.array([(box[0]+box[2])/2, box[3]])
                    foot_displacement = float(np.linalg.norm(new_foot-old_foot)/min(old_h,new_h))
                    containment = float(_overlap(old,box))
                    partial_full = containment >= .75 and foot_displacement <= .6
                    suspicious = (distance >= .20 and scale >= 2. and displacement >= .5) or (distance >= .55 and displacement >= .75)
                    if suspicious and partial_full:
                        events.append({'raw_id':raw_id,'old_segment':segment,'new_segment':segment,
                            'time':float(t),'action':'review','reason':'partial_full_box_change',
                            'appearance_distance':distance,'height_ratio':scale,
                            'centre_displacement_heights':displacement,'foot_displacement_heights':foot_displacement,
                            'smaller_box_coverage':containment,'identity_verified':False})
                        suspicious = False
                    if suspicious and not crowded:
                        while self.next_id in raw_ids or any(v['segment']==self.next_id for v in self.tracks.values()):
                            self.next_id += 1
                        segment = self.next_id; self.next_id += 1
                        events.append({'raw_id':raw_id,'old_segment':prior['segment'],'new_segment':segment,
                            'time':float(t),'action':'split','reason':'appearance_geometry_discontinuity','appearance_distance':distance,
                            'height_ratio':scale,'centre_displacement_heights':displacement,
                            'foot_displacement_heights':foot_displacement,'smaller_box_coverage':containment,
                            'identity_verified':False})
                        prior = None
            # An overlapping box can blend two shirts; never teach the prototype from it.
            appearance = prior['appearance'] if crowded and prior else descriptor if not crowded else None
            self.tracks[raw_id] = {'time':t,'box':box.copy(),'appearance':appearance,'segment':segment}
            row[4] = segment
        return rows, events
