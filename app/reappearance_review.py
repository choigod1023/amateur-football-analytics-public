"""Consume only current, scene-scoped human identity answers; never rewrite them."""
from .difference_review import DifferenceReview, fingerprint, read


def reviewed_links(directory, source_sha256):
    review=DifferenceReview(directory);approved=[];blocked=[];pending=[]
    for ident,item in review.items().items():
        if item.get('review_scope')!='occlusion-reappearance' or item.get('source_sha256')!=source_sha256:
            continue
        answer=read(review.root/'answers'/f'{ident}.json',{})
        if not (answer.get('fingerprint')==fingerprint(item) and answer.get('source')=='human' and answer.get('id')==ident):
            pending.append(ident);continue
        boundary=item.get('boundary',{})
        # Even a same answer cannot justify overlapping track components.
        if answer.get('verdict')=='same' and boundary.get('end',float('inf')) < boundary.get('start',float('-inf')):
            approved.append({'question':ident,'pair':item['source_pair'],'boundary':boundary,
                             'basis':'human_scene_scoped','source_sha256':source_sha256})
        elif answer.get('verdict')=='different':
            blocked.append(item['source_pair'])
        else:pending.append(ident)
    return {'approved':approved,'blocked':blocked,'pending':pending,
            'scope':'These boundaries only; not permission to merge entire track histories.'}
