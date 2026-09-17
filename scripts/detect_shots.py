#!/usr/bin/env python3
import argparse
from pathlib import Path
from utils import dump_json,load_json,overlaps,safe_name

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--metadata',default='work/metadata/videos.json'); ap.add_argument('--frames',default='work/frames/frame_manifest.json'); ap.add_argument('--response-file',required=True); ap.add_argument('--output',default='work/shot_timeline.json'); a=ap.parse_args()
    metas={x['source_video']:x for x in load_json(a.metadata,{}).get('videos',[])}; fdocs={x['source_video']:x for x in load_json(a.frames,{}).get('videos',[])}; response=load_json(a.response_file,{}); docs=response if isinstance(response,list) else response.get('videos',[response]); all_shots=[]
    for doc in docs:
        name=doc.get('source_video'); meta=metas.get(name); frames=fdocs.get(name)
        if not meta or not frames: raise ValueError(f'unknown source_video: {name}')
        if doc.get('source_sha256')!=meta['source_sha256'] or doc.get('frame_manifest_hash')!=frames['frame_manifest_hash']: raise ValueError(f'{name}: stale boundary response hash')
        prev=0.0; seen=set(); shots=doc.get('shots',[])
        if not shots: raise ValueError(f'{name}: no shots')
        for i,s in enumerate(shots,1):
            sid=s.get('shot_id'); expected=f'{safe_name(name)}_shot_{i:03d}'; st=float(s['start']); en=float(s['end']); dur=en-st
            if sid!=expected or sid in seen: raise ValueError(f'{name}: shot_id must be {expected}')
            if st<prev-.04 or not 0<=st<en<=float(meta['safe_end'])+.04: raise ValueError(f'{sid}: overlapping or out-of-bounds range')
            if overlaps(st,en,meta.get('unsafe_ranges',[])): raise ValueError(f'{sid}: overlaps black/frozen range')
            if abs(float(s.get('duration',dur))-dur)>.05: raise ValueError(f'{sid}: duration mismatch')
            if not s.get('action_complete',False): raise ValueError(f'{sid}: incomplete action boundary rejected')
            row={'shot_id':sid,'source_video':name,'source_path':meta['path'],'source_sha256':meta['source_sha256'],'start':round(st,3),'end':round(en,3),'duration':round(dur,3),'boundary_reason':s.get('boundary_reason',''),'action_complete':True,'is_self_contained':bool(s.get('is_self_contained',True)),'similarity_tags':sorted(set(map(str,s.get('similarity_tags',[]))))}; all_shots.append(row); seen.add(sid); prev=en
    if set(metas)!={d.get('source_video') for d in docs}: raise ValueError('boundary response must cover every source video')
    dump_json(a.output,{'shots':all_shots}); print(a.output)
if __name__=='__main__': main()
