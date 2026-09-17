#!/usr/bin/env python3
"""Validate one combined AI boundary/content response and build the cached library."""
import argparse,shutil
from pathlib import Path
from merge_short_shots import virtual_library
from utils import CONTINUITY_RELATIONS,PRODUCT_INTERACTIONS,PRODUCT_STATES,USABLE_POSITIONS,config,dump_json,load_json,normalize_shot,overlaps,safe_name,seconds,timestamp

REQUIRED=('shot_id','time','description','person','product','scene','shot_type','usable_position','continuity','tags','visual_facts','edit','action_complete','is_self_contained','burned_caption','caption_interferes','caption_bbox','eligible_for_edit')
def validate_semantics(item,sid):
    for field,keys in (('time',('start','end','duration')),('person',('person_id','appearance','action','emotion')),('product',('visible','name','interaction','state')),('continuity',('previous_relation','next_relation')),('edit',('merge_allowed','selectable'))):
        value=item.get(field)
        if not isinstance(value,dict) or any(k not in value for k in keys): raise ValueError(f'{sid}: invalid {field} object')
    if item['product']['interaction'] not in PRODUCT_INTERACTIONS: raise ValueError(f'{sid}: invalid product.interaction')
    if item['product']['state'] not in PRODUCT_STATES: raise ValueError(f'{sid}: invalid product.state')
    if not isinstance(item['usable_position'],list) or any(x not in USABLE_POSITIONS for x in item['usable_position']): raise ValueError(f'{sid}: invalid usable_position')
    if any(item['continuity'][k] not in CONTINUITY_RELATIONS for k in ('previous_relation','next_relation')): raise ValueError(f'{sid}: invalid continuity relation')
    if not isinstance(item['tags'],list): raise ValueError(f'{sid}: tags must be an array')
    facets=item.get('visual_facts')
    if not isinstance(facets,dict) or any(not isinstance(facets.get(k),list) for k in ('garment_area','action','result')): raise ValueError(f'{sid}: visual_facts must contain garment_area, action, and result arrays')
    if bool(item['edit']['selectable'])!=bool(item['eligible_for_edit']): raise ValueError(f'{sid}: edit.selectable and eligible_for_edit must agree')
    bbox=item['caption_bbox']
    if item['caption_interferes'] and (not isinstance(bbox,list) or len(bbox)!=4): raise ValueError(f'{sid}: interfering caption requires a normalized caption_bbox')
    if not item['caption_interferes'] and bbox is not None: raise ValueError(f'{sid}: caption_bbox must be null when caption_interferes is false')
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--config',required=True); ap.add_argument('--metadata',default='work/metadata/videos.json'); ap.add_argument('--frames',default='work/frames/frame_manifest.json'); ap.add_argument('--cache-state',default='work/cache_state.json'); ap.add_argument('--response-file',required=True); ap.add_argument('--work-dir',default='work'); a=ap.parse_args(); cfg=config(a.config); work=Path(a.work_dir)
    metas={x['source_video']:x for x in load_json(a.metadata,{}).get('videos',[])}; frames={x['source_video']:x for x in load_json(a.frames,{}).get('videos',[])}; state={x['source_video']:x for x in load_json(a.cache_state,{}).get('videos',[])}
    response=load_json(a.response_file,{}); docs=response if isinstance(response,list) else response.get('videos',[]); provided={x.get('source_video'):x for x in docs}; raw=[]
    for name,meta in metas.items():
        st=state[name]
        if st.get('hit'):
            for original in load_json(Path(st['cache_dir'])/'shot_metadata.json',{}).get('shots',[]):
                row=dict(original); row['source_path']=st['source_path']; row['source_video']=name; row['segments']=[dict(x,source_path=st['source_path'],source_video=name) for x in original.get('segments',[])]; raw.append(row)
            continue
        doc=provided.get(name)
        if not doc: raise ValueError(f'missing combined analysis for uncached source: {name}')
        if doc.get('source_sha256')!=meta['source_sha256'] or doc.get('frame_manifest_hash')!=frames[name]['frame_manifest_hash']: raise ValueError(f'{name}: stale analysis response hash')
        prev=0.0; seen=set()
        for i,item in enumerate(doc.get('shots',[]),1):
            missing=[x for x in REQUIRED if x not in item]
            if missing: raise ValueError(f'{name}: analysis missing fields: {", ".join(missing)}')
            validate_semantics(item,item.get('shot_id','unknown'))
            sid=item['shot_id']; expected=f'{safe_name(name)}_shot_{i:03d}'; timing=item.get('time',{}); start=seconds(timing.get('start')); end=seconds(timing.get('end')); dur=end-start
            if sid!=expected or sid in seen: raise ValueError(f'{name}: shot_id must be {expected}')
            gap=start-prev
            if start<prev-.04 or (gap>.08 and not overlaps(prev,start,meta.get('unsafe_ranges',[]))) or not 0<=start<end<=float(meta['safe_end'])+.04 or overlaps(start,end,meta.get('unsafe_ranges',[])): raise ValueError(f'{sid}: invalid, uncovered, or unsafe range')
            if not item['action_complete']: raise ValueError(f'{sid}: incomplete action boundary rejected')
            if abs(seconds(timing.get('duration'),dur)-dur)>.08: raise ValueError(f'{sid}: time.duration must equal end - start')
            keyframes=[x for x in frames[name]['frames'] if start-.05<=float(x['timestamp'])<=end+.05]
            row=normalize_shot(item); row.update({'time':{'start':timestamp(start),'end':timestamp(end),'duration':round(dur,3)},'source_video':name,'source_path':meta['path'],'source_sha256':meta['source_sha256'],'video_hash':st['video_hash'],'start':round(start,3),'end':round(end,3),'duration':round(dur,3),'segments':[{'source_path':meta['path'],'source_video':name,'start':round(start,3),'end':round(end,3),'duration':round(dur,3),'source_shot_id':sid}],'keyframes':keyframes}); row['eligible_for_edit']=bool(row['eligible_for_edit'] and row['action_complete'] and row['is_self_contained']); row['edit']['selectable']=row['eligible_for_edit']; raw.append(row); prev=end; seen.add(sid)
        if abs(prev-float(meta['safe_end']))>.08: raise ValueError(f'{name}: shots must cover the usable timeline through safe_end')
    result=virtual_library(raw,cfg); result['schema_version']=4; dump_json(work/'shot_metadata.json',{'schema_version':4,'shots':raw}); dump_json(work/'shot_library.json',result)
    for name,st in state.items():
        if st.get('hit'): continue
        folder=Path(st['cache_dir']); folder.mkdir(parents=True,exist_ok=True); per_raw=[x for x in raw if x['source_video']==name]; ids={x['shot_id'] for x in per_raw}; per_final=[x for x in result['shots'] if set(x['source_shot_ids'])<=ids]; per_rejected=[x for x in result['rejected_short_shots'] if x['shot_id'] in ids]
        src=work/'frames'/Path(name).stem; dst=folder/'frames'
        if dst.exists(): shutil.rmtree(dst)
        if src.exists(): shutil.copytree(src,dst)
        def cached_frames(rows):
            copied=[]
            for original in rows:
                row=dict(original); row['keyframes']=[dict(frame,path=str((dst/Path(frame['path']).name).resolve())) for frame in original.get('keyframes',[])]; copied.append(row)
            return copied
        dump_json(folder/'shot_metadata.json',{'schema_version':4,'identity':{k:st[k] for k in ('source_sha256','duration','size','video_hash')},'shots':cached_frames(per_raw)}); dump_json(folder/'shot_library.json',{'schema_version':4,'shots':cached_frames(per_final),'rejected_short_shots':cached_frames(per_rejected),'rules':result['rules']})
    print(work/'shot_library.json')
if __name__=='__main__': main()
