#!/usr/bin/env python3
"""Resolve selected shot_ids to source time references without creating media."""
import argparse
from pathlib import Path

from utils import dump_json,load_json,seconds


def segment_references(shot):
    raw=shot.get('segments') or [{
        'source_path':shot.get('source_path'),
        'source_video':shot.get('source_video'),
        'start':shot.get('start',0),
        'end':shot.get('end'),
        'duration':shot.get('duration'),
        'source_shot_id':shot.get('shot_id'),
    }]
    references=[]
    for order,segment in enumerate(raw,1):
        source=segment.get('source_path') or shot.get('source_path')
        start=seconds(segment.get('start'))
        duration=seconds(segment.get('duration'))
        end=seconds(segment.get('end'),start+duration)
        if not source: raise ValueError(f"{shot.get('shot_id','shot')}: source video is missing")
        if end<=start and duration>0: end=start+duration
        if end<=start: raise ValueError(f"{shot.get('shot_id','shot')}: invalid source range")
        references.append({
            'source':str(source),
            'source_video':segment.get('source_video') or shot.get('source_video') or Path(source).name,
            'start':round(start,6),
            'end':round(end,6),
            'duration':round(end-start,6),
            'order':order,
            'source_shot_id':segment.get('source_shot_id') or shot.get('shot_id'),
        })
    return references


def selection(shot,order):
    refs=segment_references(shot)
    row={
        'shot_id':shot['shot_id'],
        'order':order,
        'source':refs[0]['source'],
        'start':refs[0]['start'],
        'end':refs[0]['end'],
    }
    if len(refs)>1: row['segments']=refs
    return row


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--variants-dir',default='work/variants')
    ap.add_argument('--library',default='work/shot_library.json')
    ap.add_argument('--config')  # Retained for CLI compatibility; no media work occurs here.
    ap.add_argument('--cache-dir')
    ap.add_argument('--output-dir')
    ap.add_argument('--output',default='work/selected_shot_library.json')
    a=ap.parse_args()
    library_data=load_json(a.library,{})
    library={x['shot_id']:x for x in library_data.get('shots',[])}
    ids=[]; variant_refs=[]; orders={}
    for vf in sorted(Path(a.variants_dir).glob('variant_*.json')):
        variant=load_json(vf,{})
        selected=[]
        for order,clip in enumerate(variant.get('clips',[]),1):
            sid=clip.get('shot_id')
            if sid not in library: raise ValueError(f'{vf.name}: unknown shot_id {sid}')
            if sid not in ids: ids.append(sid)
            orders.setdefault(sid,[]).append({'variant_id':variant.get('variant_id',vf.stem),'order':order})
            selected.append(selection(library[sid],order))
        variant_refs.append({'variant_id':variant.get('variant_id',vf.stem),'shots':selected})
    if not ids: raise ValueError('no selected shots')
    rows=[]
    for sid in ids:
        row=dict(library[sid]); row.pop('clip_path',None); row.pop('extraction_cache_hit',None)
        refs=segment_references(row); row.update({
            'source':refs[0]['source'],
            'start':refs[0]['start'],
            'end':refs[0]['end'],
            'duration':round(sum(x['duration'] for x in refs),6),
            'segments':refs,
            'shot_order':orders[sid][0]['order'],
            'variant_orders':orders[sid],
        })
        rows.append(row)
    dump_json(a.output,{
        'schema_version':library_data.get('schema_version',4),
        'reference_schema_version':1,
        'reference_kind':'source_time_ranges',
        'shots':rows,
        'selected_shot_ids':ids,
        'variants':variant_refs,
        'intermediate_media_created':False,
    })
    print(a.output)


if __name__=='__main__': main()
