#!/usr/bin/env python3
import argparse,shutil
from pathlib import Path
from prepare_materials import import_archives
from utils import config,dump_json,load_json,normalize_shot,video_cache_key,videos

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--config',required=True); ap.add_argument('--input-dir',default='input'); ap.add_argument('--videos-dir',default='input/videos'); ap.add_argument('--cache-dir'); ap.add_argument('--work-dir',default='work'); a=ap.parse_args(); cfg=config(a.config); root=Path(a.config).resolve().parents[1]; cache=Path(a.cache_dir or cfg['cache_dir']); cache=cache if cache.is_absolute() else root/cache; work=Path(a.work_dir); work.mkdir(parents=True,exist_ok=True); import_archives(Path(a.input_dir),Path(a.videos_dir),work/'input_name_map.json')
    states=[]; aggregated=[]
    for p in videos(a.videos_dir):
        key,identity=video_cache_key(p); folder=cache/key; lib=folder/'shot_library.json'; cached=load_json(lib,{}) if lib.is_file() else {}; hit=cached.get('schema_version') in (3,4)
        states.append({'source_video':p.name,'source_path':str(p.resolve()),'video_hash':key,'cache_dir':str(folder.resolve()),'hit':hit,**identity})
        if hit:
            for original in cached.get('shots',[]):
                row=normalize_shot(original); row['source_path']=str(p.resolve())
                row['segments']=[dict(x,source_path=str(p.resolve())) for x in original.get('segments',[])]; aggregated.append(row)
    if not states: raise ValueError('No source videos found')
    all_hit=all(x['hit'] for x in states)
    dump_json(work/'cache_state.json',{'all_hit':all_hit,'videos':states})
    if all_hit: dump_json(work/'shot_library.json',{'schema_version':4,'shots':aggregated,'cache_hit':True})
    print('hit' if all_hit else 'miss')
if __name__=='__main__': main()
