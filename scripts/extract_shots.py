#!/usr/bin/env python3
import argparse
from pathlib import Path
from utils import dump_json,duration,load_json,require,run
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--timeline',default='work/shot_timeline.json'); ap.add_argument('--output-dir',default='work/shots'); ap.add_argument('--manifest',default='work/shot_manifest.json'); a=ap.parse_args(); require('ffmpeg'); out=Path(a.output_dir); out.mkdir(parents=True,exist_ok=True); rows=[]
    for s in load_json(a.timeline,{}).get('shots',[]):
        dest=out/(s['shot_id']+'.mp4'); run(['ffmpeg','-hide_banner','-loglevel','error','-y','-ss',f"{float(s['start']):.3f}",'-i',s['source_path'],'-t',f"{float(s['duration']):.3f}",'-map','0:v:0','-an','-c:v','libx264','-preset','veryfast','-crf','18','-pix_fmt','yuv420p','-movflags','+faststart',dest]); actual=duration(dest)
        if abs(actual-float(s['duration']))>.12: raise RuntimeError(f"{s['shot_id']}: extracted duration mismatch")
        row=dict(s); row.update({'clip_path':str(dest.resolve()),'duration':round(actual,3),'shot_type':'original','source_shot_ids':[s['shot_id']]}); rows.append(row)
    dump_json(a.manifest,{'shots':rows}); print(a.manifest)
if __name__=='__main__': main()
