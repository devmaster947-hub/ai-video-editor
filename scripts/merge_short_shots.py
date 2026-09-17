#!/usr/bin/env python3
"""Plan semantic short-shot merges without extracting or encoding media."""
import argparse,itertools
from utils import VISUAL_FACET_KEYS,config,dump_json,load_json,normalize_shot

TAG_FIELDS=('product','scene','person','action','story_role','tags')
def values(shot,field):
    if field=='product':
        product=shot.get('product',{}); value=[product.get('name',''),product.get('interaction',''),product.get('state','')] if isinstance(product,dict) else product
    elif field=='person':
        person=shot.get('person',{}); value=([person.get('person_id',''),person.get('appearance','')]+list(shot.get('people',[]) if isinstance(shot.get('people',[]),list) else [shot.get('people','')])) if isinstance(person,dict) else shot.get('people',[])
    elif field=='action':
        person=shot.get('person',{}); value=[person.get('action',''),shot.get('action','')] if isinstance(person,dict) else shot.get('action',[])
    elif field=='story_role':
        value=list(shot.get('usable_position',[]))+list(shot.get('story_roles',[]) if isinstance(shot.get('story_roles',[]),list) else [shot.get('story_roles','')])
    else: value=shot.get(field,[])
    if isinstance(value,str): value=[value]
    return {str(x).strip().lower() for x in value if str(x).strip() and str(x)!='无法确认'}
def compatibility(a,b):
    # Priority order from the V3 contract. Same-source is mandatory so a virtual
    # merged shot remains traceable and cacheable under one source video key.
    if a.get('source_video')!=b.get('source_video'): return None
    matches=[bool(values(a,f)&values(b,f)) for f in TAG_FIELDS]
    if not any(matches): return None
    return tuple(int(x) for x in matches)
def choose_group(anchor,available,cfg):
    candidates=[x for x in available if x['shot_id']!=anchor['shot_id'] and compatibility(anchor,x)][:12]; best=None
    for count in range(1,min(5,len(candidates))+1):
        for extra in itertools.combinations(candidates,count):
            group=(anchor,*extra)
            if not all(any(compatibility(x,y) for y in group if y is not x) for x in group): continue
            total=sum(float(x['duration']) for x in group)
            if float(cfg['merge_min_duration'])<=total<=float(cfg['merge_max_duration']):
                affinity=sum(sum(compatibility(anchor,x) or ()) for x in extra)
                score=(abs(total-float(cfg['merge_target_duration'])),-affinity,len(group))
                ordered=sorted(group,key=lambda x:(x.get('_order',0),float(x.get('start',0))))
                if best is None or score<best[0]: best=(score,ordered)
    return best[1] if best else None
def virtual_library(shots,cfg):
    rows=[dict(normalize_shot(x),_order=i) for i,x in enumerate(shots)]; threshold=float(cfg['short_shot_threshold']); final=[]; rejected=[]; used=set(); merge_no=1
    for s in rows:
        if float(s['duration'])>=threshold:
            row={k:v for k,v in s.items() if k!='_order'}; row['merge_type']='original'; row['source_shot_ids']=[s['shot_id']]; row['eligible_for_edit']=bool(row.get('eligible_for_edit',True)); row['edit']['selectable']=row['eligible_for_edit']; final.append(row)
    short=[x for x in rows if float(x['duration'])<threshold]
    for anchor in short:
        if anchor['shot_id'] in used: continue
        group=choose_group(anchor,[x for x in short if x['shot_id'] not in used],cfg)
        if not group: continue
        ids=[x['shot_id'] for x in group]; sid=f"{anchor['source_video'].rsplit('.',1)[0]}_merged_{merge_no:03d}"; merge_no+=1
        segments=[{'source_path':x['source_path'],'source_video':x['source_video'],'start':x['start'],'end':x['end'],'duration':x['duration'],'source_shot_id':x['shot_id']} for x in group]
        combined={f:sorted(set().union(*(values(x,f) for x in group))) for f in TAG_FIELDS}; descriptions=[x.get('description','') for x in group if x.get('description')]; positions=combined.pop('story_role'); tags=combined.pop('tags'); explicit_people={x['person']['person_id'] for x in group if x['person']['person_id']}; products={x['product']['name'] for x in group if x['product']['name']}
        visual_facts={k:sorted(set().union(*(set(x.get('visual_facts',{}).get(k,[])) for x in group))) for k in VISUAL_FACET_KEYS}
        merged=normalize_shot({'shot_id':sid,'merge_type':'merged','source_video':anchor['source_video'],'source_sha256':anchor['source_sha256'],'video_hash':anchor['video_hash'],'duration':round(sum(float(x['duration']) for x in group),3),'segments':segments,'source_shot_ids':ids,'description':' / '.join(descriptions),'person':{'person_id':next(iter(explicit_people)) if len(explicit_people)==1 else '','appearance':'','action':' / '.join(x['person']['action'] for x in group if x['person']['action']),'emotion':''},'product':{'visible':any(x['product']['visible'] for x in group),'name':next(iter(products)) if len(products)==1 else '','interaction':anchor['product']['interaction'],'state':anchor['product']['state']},'scene':anchor.get('scene',''),'shot_type':anchor.get('shot_type',''),'usable_position':positions,'continuity':{'previous_relation':group[0]['continuity']['previous_relation'],'next_relation':group[-1]['continuity']['next_relation']},'tags':tags,'visual_facts':visual_facts,'edit':{'merge_allowed':all(x['edit']['merge_allowed'] for x in group),'selectable':all(x.get('eligible_for_edit',True) for x in group)},'action_complete':all(x.get('action_complete') for x in group),'is_self_contained':all(x.get('is_self_contained') for x in group),'burned_caption':any(x.get('burned_caption') for x in group),'caption_interferes':any(x.get('caption_interferes') for x in group),'caption_bbox':next((x.get('caption_bbox') for x in group if x.get('caption_bbox')),None),'eligible_for_edit':all(x.get('eligible_for_edit',True) for x in group)}); merged['visual_summary']=merged['description']; final.append(merged); used.update(ids)
    for s in short:
        if s['shot_id'] not in used:
            row={k:v for k,v in s.items() if k!='_order'}; row.update({'merge_type':'original','source_shot_ids':[s['shot_id']],'eligible_for_edit':False,'discard_reason':'sub-2-second shot has no semantically related 3.5-4.5s merge group'}); row['edit']['selectable']=False; rejected.append(row)
    final.sort(key=lambda x:min(next(i for i,s in enumerate(rows) if s['shot_id']==sid) for sid in x['source_shot_ids']))
    return {'shots':final,'rejected_short_shots':rejected,'rules':{'short_threshold':threshold,'merge_target':cfg['merge_target_duration'],'accepted_range':[cfg['merge_min_duration'],cfg['merge_max_duration']]}}
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--config',required=True); ap.add_argument('--library',default='work/raw_shot_library.json'); ap.add_argument('--output',default='work/shot_library.json'); a=ap.parse_args(); dump_json(a.output,virtual_library(load_json(a.library,{}).get('shots',[]),config(a.config))); print(a.output)
if __name__=='__main__': main()
