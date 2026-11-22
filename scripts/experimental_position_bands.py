"""Offline position-band feasibility; never outputs official positions or feeds coaching."""
import argparse, csv, json, statistics
from pathlib import Path
import cv2
import numpy as np


def bands(tracks, direction, min_span=20, min_samples=15, min_players=6):
    """Rank long-lived observed x coordinates into thirds, per known team.

    This is a research proxy for spatial bands, not a defender/midfielder/striker model.
    Direction must be specified for each team; observed IDs must be stable.
    """
    if direction not in (-1, 1):
        return {}
    eligible = {}
    for player, values in tracks.items():
        clean = sorted((float(t),float(x)) for t,x in values if np.isfinite(t) and np.isfinite(x) and 0 <= x <= 1)
        if len(clean) >= min_samples and clean[-1][0]-clean[0][0] >= min_span:
            eligible[player] = statistics.median(x for _,x in clean)
    if len(eligible) < min_players:
        return {}
    ranked = sorted(eligible, key=lambda k:(eligible[k]*direction, str(k)))
    # Exact ties at a band boundary are withheld, not broken by player ID.
    n=len(ranked); out={}
    for index, player in enumerate(ranked):
        label = ('back','middle','front')[min(2, index*3//n)]
        left = index > 0 and (index-1)*3//n != index*3//n and abs(eligible[ranked[index-1]]-eligible[player]) < 1e-8
        right = index+1 < n and (index+1)*3//n != index*3//n and abs(eligible[ranked[index+1]]-eligible[player]) < 1e-8
        if not (left or right): out[player] = label
    return out


def read_clip(path, calibration):
    source=np.asarray(calibration['image_points'], np.float32)
    dest=np.asarray(calibration['field_points_m'], np.float32)
    length=float(calibration['field_size_m'][0]); mat=cv2.getPerspectiveTransform(source,dest)
    teams={'0':{}, '1':{}}
    with path.open(encoding='utf-8-sig',newline='') as handle:
        data=csv.reader(handle); ts, ids, fields=next(data),next(data),next(data); next(data)
        columns=[(i,ts[i],ids[i]) for i in range(1,len(fields),4) if i+3<len(fields) and ts[i] in teams and ids[i]!='0']
        for row in data:
            if not row or not row[0]: continue
            frame=int(row[0]);
            if (frame-1)%25: continue
            for i,team,identity in columns:
                try: x,y,w,h=map(float,row[i:i+4])
                except (ValueError,IndexError):continue
                if not np.isfinite([x,y,w,h]).all() or w<=0 or h<=0:continue
                foot=(x+w/2,y+h)
                if cv2.pointPolygonTest(source, foot, False)<0: continue
                projected=cv2.perspectiveTransform(np.array([[foot]],dtype=np.float32),mat)[0,0]
                nx=float(projected[0])/length
                if 0<=nx<=1:teams[team].setdefault(identity,[]).append(((frame-1)/25,nx))
    return teams


def compare(a,b):
    common=set(a)&set(b)
    return {'eligible_common':len(common),'same_band':sum(a[k]==b[k] for k in common),
            'changed_band':sum(a[k]!=b[k] for k in common)}


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('folder',type=Path);ap.add_argument('config',type=Path)
    args=ap.parse_args(); cal=json.loads(args.config.read_text(encoding='utf-8-sig'))['calibration']
    names=('0000_0030','0030_0060','0060_0090','0120_0150')
    clips=[read_clip(args.folder/(name+'.csv'),cal) for name in names]
    result={'clips':[], 'comparison':{}, 'limitations':'Known GT team and IDs; manually provided experimental camera geometry; no actual role ground truth, automatic tracking, attack direction, or other matches.'}
    for name,clip in zip(names,clips):
        result['clips'].append({'clip':name,'eligible_per_team':{team:len(bands(clip[team],1)) for team in ('0','1')}})
    for i in range(len(clips)-1):
        key=f'{names[i]}_to_{names[i+1]}'
        result['comparison'][key]={team:compare(bands(clips[i][team],1),bands(clips[i+1][team],1)) for team in ('0','1')}
    result['direction_flip']={team:compare(bands(clips[0][team],1),bands(clips[0][team],-1)) for team in ('0','1')}
    print(json.dumps(result,indent=2,ensure_ascii=False))


if __name__ == '__main__':main()
