#!/usr/bin/env python3
"""Compatibility shim: mark caption repair for the final render; never encode shots."""
import argparse

from utils import config,dump_json,load_json


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--library',default='work/selected_shot_library.json')
    ap.add_argument('--config',required=True)
    ap.add_argument('--output-dir')  # Legacy no-op: no intermediate media is written.
    ap.add_argument('--output',default='work/render_shot_library.json')
    a=ap.parse_args(); cfg=config(a.config); data=load_json(a.library,{})
    rows=[]; report=[]
    for original in data.get('shots',[]):
        row=dict(original); enabled=bool(cfg.get('repair_burned_captions',True) and row.get('burned_caption') and row.get('caption_interferes'))
        if enabled and (not isinstance(row.get('caption_bbox'),list) or len(row['caption_bbox'])!=4):
            raise ValueError(f"{row['shot_id']}: interfering caption requires normalized caption_bbox [x,y,w,h]")
        row['caption_repair_in_final_render']=enabled; rows.append(row)
        report.append({'shot_id':row['shot_id'],'status':'deferred_to_final_render' if enabled else 'skipped_not_interfering'})
    result=dict(data); result.update({'shots':rows,'repair_report':report,'intermediate_media_created':False})
    dump_json(a.output,result); print(a.output)


if __name__=='__main__': main()
