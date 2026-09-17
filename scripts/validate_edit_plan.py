#!/usr/bin/env python3
import argparse,re
from pathlib import Path
from utils import config,dump_json,load_json,normalize_shot,require,shot_covers_requirements,speed_bounds
FONT_DIRS=['/System/Library/Fonts/Supplemental','/System/Library/Fonts','/Library/Fonts']
def stamp(x):
    ms=round(x*1000); h,ms=divmod(ms,3600000); m,ms=divmod(ms,60000); s,ms=divmod(ms,1000); return f'{h:02d}:{m:02d}:{s:02d},{ms:03d}'
def write_srt(cues,path):
    blocks=[f"{i}\n{stamp(float(c['start']))} --> {stamp(float(c['end']))}\n{c['text']}\n" for i,c in enumerate(cues,1)]; Path(path).parent.mkdir(parents=True,exist_ok=True); Path(path).write_text('\n'.join(blocks),encoding='utf-8')
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--variants-dir',default='work/variants'); ap.add_argument('--library',default='work/shot_library.json'); ap.add_argument('--config',required=True); ap.add_argument('--narration',default='work/narration_manifest.json'); ap.add_argument('--output',default='work/validation_report.json'); ap.add_argument('--subtitles-dir',default='work/subtitles'); a=ap.parse_args(); require('ffmpeg'); cfg=config(a.config); shots={x['shot_id']:normalize_shot(x) for x in load_json(a.library,{}).get('shots',[])}; narr=load_json(a.narration,{}); segments={x['script_id']:x for x in narr.get('script_segments',[])}; target=float(narr.get('duration') or 0); errors=[]; reports=[]
    if not target or not Path(narr.get('voiceover_path','')).is_file(): errors.append('missing narration audio')
    cues=narr.get('cues',[])
    if any(not x.get('text') or re.fullmatch(r'[\W_]+',x.get('text','')) for x in cues): errors.append('invalid caption cue')
    for cue in cues:
        lines=str(cue.get('text','')).splitlines()
        if len(lines)>int(cfg['subtitle_max_lines']): errors.append(f"{cue.get('cue_id','cue')}: subtitle exceeds max lines")
    min_speed,max_speed=speed_bounds(cfg)
    for vf in sorted(Path(a.variants_dir).glob('variant_*.json')):
        v=load_json(vf,{}); verr=[]; seen=set(); total=0
        for i,c in enumerate(v.get('clips',[]),1):
            sid=c.get('shot_id'); shot=shots.get(sid); wanted=float(c.get('target_duration',0)); total+=wanted
            if not shot: verr.append(f'clip {i}: unknown shot_id'); continue
            if sid in seen: verr.append(f'clip {i}: repeated shot_id')
            if not shot.get('eligible_for_edit'): verr.append(f'clip {i}: unavailable shot')
            for segment in shot.get('segments',[]):
                if not Path(segment.get('source_path','')).is_file(): verr.append(f'clip {i}: missing source media')
            merge_type=shot.get('merge_type') or (shot.get('shot_type') if shot.get('shot_type') in ('original','merged') else '')
            if float(shot['duration'])<float(cfg['short_shot_threshold']) and merge_type!='merged': verr.append(f'clip {i}: unmerged short shot')
            speed=float(shot['duration'])/wanted if wanted else 99
            if not min_speed<=speed<=max_speed: verr.append(f'clip {i}: speed {speed:.3f} outside {min_speed:.2f}..{max_speed:.2f}; never render above 1.30x')
            if any(k in c for k in ('start','end','start_time','end_time')): verr.append(f'clip {i}: arbitrary trimming is forbidden')
            segment=segments.get(c.get('script_id'),{}); covered_visuals,missing=shot_covers_requirements(shot,segment.get('visual_requirements',{}))
            if not covered_visuals: verr.append(f'clip {i}: visual requirements are not covered: {missing}')
            seen.add(sid)
        if abs(total-target)>1/30+.001: verr.append(f'plan {total:.3f}s does not match narration {target:.3f}s')
        srt=Path(a.subtitles_dir)/(v.get('variant_id',vf.stem)+'.srt'); write_srt(cues,srt); reports.append({'variant_id':v.get('variant_id'),'duration':round(total,3),'subtitle_path':str(srt.resolve()),'errors':verr}); errors.extend(f'{vf.stem}: {x}' for x in verr)
    if not reports: errors.append('no variants found')
    font_dir=next((x for x in FONT_DIRS if Path(x).exists()),None)
    if not font_dir: errors.append('no usable font directory')
    dump_json(a.output,{'passed':not errors,'errors':errors,'narration_duration':target,'variants':reports,'font_dir':font_dir})
    if errors: raise SystemExit('\n'.join(errors))
    print(a.output)
if __name__=='__main__': main()
