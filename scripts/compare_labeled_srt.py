"""Compare only source-frame IDs actually scored by BOTH local SRT runs."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.evaluate_wide_tracking import load_labels, MissedReappearanceAudit


def compare(first, second, truth):
    def indexed(data):
        rows=data.get('frame_results')
        if not isinstance(rows,list): raise ValueError('Missing frame results')
        result={}
        for row in rows:
            frame=row.get('source_frame')
            if type(frame) is not int or frame in result or frame not in truth:
                raise ValueError('Duplicate, invalid or unannotated source frame')
            pairs=row.get('gt_track_pairs')
            if (not isinstance(pairs,list) or row.get('gt') != len(truth[frame]) or
                    type(row.get('predicted')) is not int or row['predicted'] < len(pairs) or
                    row.get('matched') != len(pairs) or
                    any(not isinstance(pair,(tuple,list)) or len(pair)!=2 for pair in pairs)):
                raise ValueError('Inconsistent frame counts or match pairs')
            gt_ids={gt_id for gt_id,_ in truth[frame]}
            if (len({p[0] for p in pairs}) != len(pairs) or len({str(p[1]) for p in pairs}) != len(pairs) or
                    any(p[0] not in gt_ids for p in pairs)):
                raise ValueError('Duplicate or unannotated matches')
            result[frame]=row
        return result
    a,b=indexed(first),indexed(second)
    common=sorted(a.keys() & b.keys())
    if not common: raise ValueError('No common source frames')
    result={'common_frames':common,'common_count':len(common),'models':{}}
    # Keep frame-level trade-offs visible: increased matches can coincide with
    # extra unmatched predictions. Adjacent frames are not independent samples.
    differences=[(b[i]['matched']-a[i]['matched'],
                  (b[i]['predicted']-b[i]['matched'])-(a[i]['predicted']-a[i]['matched'])) for i in common]
    result['paired_frames']={'second_more_matches':sum(d>0 for d,_ in differences),
                             'second_fewer_matches':sum(d<0 for d,_ in differences),
                             'equal_matches':sum(d==0 for d,_ in differences),
                             'second_more_unmatched_predictions':sum(u>0 for _,u in differences),
                             'second_fewer_unmatched_predictions':sum(u<0 for _,u in differences),
                             'equal_unmatched_predictions':sum(u==0 for _,u in differences),
                             'matched_difference':sum(d for d,_ in differences),
                             'unmatched_prediction_difference':sum(u for _,u in differences)}
    for name,rows in (('first',a),('second',b)):
        gt=sum(rows[i]['gt'] for i in common)
        predicted=sum(rows[i]['predicted'] for i in common)
        matched=sum(rows[i]['matched'] for i in common)
        audit=MissedReappearanceAudit();previous={};changes=0
        for i in common:
            pairs=rows[i]['gt_track_pairs']
            audit.update(truth[i],pairs)
            current=dict(pairs)
            changes+=sum(k in previous and previous[k] != v for k,v in current.items())
            previous=current
        gap=audit.summary()
        lengths=gap.pop('gap_lengths_scored_observations')
        gap['max_gap_scored_observations']=max(lengths) if lengths else None
        result['models'][name]={'gt':gt,'predicted':predicted,'matched':matched,
                                'recall_iou50':round(matched/gt,4) if gt else None,
                                'matched_prediction_fraction':round(matched/predicted,4) if predicted else None,
                                'consecutive_sample_id_changes':changes,'gap_reappearance':gap}
    result['limitations']='Small correlated matched-frame subset; match quality depends on labels and IoU; not IDF1, unseen-player accuracy, real phone or independent benchmark.'
    return result


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('first','second','labels'): p.add_argument('--'+name,required=True,type=Path)
    a=p.parse_args()
    print(json.dumps(compare(json.loads(a.first.read_text(encoding='utf8')),json.loads(a.second.read_text(encoding='utf8')),load_labels(a.labels)),ensure_ascii=False,indent=2))
