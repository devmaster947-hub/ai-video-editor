#!/usr/bin/env python3
import argparse
from pathlib import Path
from utils import dump_json,load_json
REQUIRED=('shot_id','visual_summary','people','action','product','product_state','scene','story_roles','action_complete','is_self_contained','burned_caption','tags','eligible_for_edit')
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--manifest',default='work/final_shot_manifest.json'); ap.add_argument('--response-file',required=True); ap.add_argument('--output',default='work/shot_library.json'); a=ap.parse_args(); manifest=load_json(a.manifest,{}).get('shots',[]); by_id={x['shot_id']:x for x in manifest}; response=load_json(a.response_file,{}); analyses=response if isinstance(response,list) else response.get('shots',[])
    seen=set(); rows=[]
    for item in analyses:
        missing=[x for x in REQUIRED if x not in item]
        if missing: raise ValueError(f"analysis missing fields: {', '.join(missing)}")
        sid=item['shot_id']
        if sid not in by_id or sid in seen: raise ValueError(f'unknown or duplicate shot_id: {sid}')
        if any(k in item for k in ('start','end','start_time','end_time','source_path')): raise ValueError(f'{sid}: arbitrary source ranges/paths are forbidden')
        base=by_id[sid]
        if not Path(base['clip_path']).is_file(): raise ValueError(f'{sid}: clip file missing')
        row=dict(base); row.update(item); row['eligible_for_edit']=bool(base.get('eligible_for_edit') and item['eligible_for_edit'] and item['action_complete'] and item['is_self_contained']); rows.append(row); seen.add(sid)
    missing=set(by_id)-seen
    if missing: raise ValueError('analysis must cover every final shot: '+', '.join(sorted(missing)))
    dump_json(a.output,{'shots':rows}); print(a.output)
if __name__=='__main__': main()
