#!/usr/bin/env python3
import argparse,hashlib,json,shutil,zipfile
from datetime import datetime
from pathlib import Path
from utils import VIDEO_EXTS,config,detect_unsafe_ranges,dump_json,ffprobe,file_sha256,rate,require,run,videos

def import_archives(root,out,map_output):
    old=json.loads(Path(map_output).read_text(encoding='utf-8')) if Path(map_output).exists() else {}
    mapping=list(old.get('files',[])); archive_state=dict(old.get('archives',{})); out.mkdir(parents=True,exist_ok=True)
    next_id=len(videos(out))+1
    for archive in sorted(root.glob('*.zip')):
        key=str(archive.resolve()); sig=f'{archive.stat().st_size}:{archive.stat().st_mtime_ns}'; prior=archive_state.get(key,{})
        if prior.get('signature')==sig and all((out/x).exists() for x in prior.get('normalized_names',[])): continue
        names=[]
        with zipfile.ZipFile(archive) as z:
            for info in z.infolist():
                ext=Path(info.filename).suffix.lower()
                if info.is_dir() or ext not in VIDEO_EXTS: continue
                dest=out/f'source_{next_id:03d}{ext}'; next_id+=1
                with z.open(info) as src,dest.open('wb') as dst: shutil.copyfileobj(src,dst)
                mapping.append({'archive':key,'original_name':info.filename,'normalized_name':dest.name}); names.append(dest.name)
        archive_state[key]={'signature':sig,'normalized_names':names}
    dump_json(map_output,{'files':mapping,'archives':archive_state})

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--config',required=True); ap.add_argument('--input-dir',default='input'); ap.add_argument('--videos-dir',default='input/videos'); ap.add_argument('--work-dir',default='work'); a=ap.parse_args(); cfg=config(a.config); require('ffmpeg')
    root=Path(a.input_dir); video_dir=Path(a.videos_dir); work=Path(a.work_dir); import_archives(root,video_dir,work/'input_name_map.json')
    rows=[]; frame_docs=[]; interval=float(cfg['frame_interval'])
    for p in videos(video_dir):
        probe=ffprobe(p); streams=probe.get('streams',[]); v=next((x for x in streams if x.get('codec_type')=='video'),{}); dur=float(probe.get('format',{}).get('duration') or 0); unsafe=detect_unsafe_ranges(p); safe_end=dur
        for r in unsafe:
            if r['end']>=dur-.08 and r['start']<safe_end: safe_end=float(r['start'])
        sha=file_sha256(p); row={'source_video':p.name,'path':str(p.resolve()),'source_sha256':sha,'duration':round(dur,3),'safe_end':round(max(0,safe_end),3),'unsafe_ranges':unsafe,'width':v.get('width',0),'height':v.get('height',0),'fps':round(rate(v.get('avg_frame_rate','0/1')),3),'has_audio':any(x.get('codec_type')=='audio' for x in streams)}; rows.append(row)
        frame_dir=work/'frames'/p.stem; frame_dir.mkdir(parents=True,exist_ok=True); pattern=frame_dir/'frame_%06d.jpg'
        run(['ffmpeg','-hide_banner','-loglevel','error','-y','-i',p,'-vf',f'fps=1/{interval},scale=480:-2','-q:v','3',pattern])
        files=sorted(frame_dir.glob('frame_*.jpg')); frames=[{'timestamp':round(i*interval,3),'path':str(x.resolve()),'sha256':file_sha256(x)} for i,x in enumerate(files)]
        frame_hash=hashlib.sha256(json.dumps([(x['timestamp'],x['sha256']) for x in frames],separators=(',',':')).encode()).hexdigest()
        frame_docs.append({'source_video':p.name,'source_sha256':sha,'frame_manifest_hash':frame_hash,'interval':interval,'frames':frames})
    if not rows: raise ValueError('No source videos found')
    dump_json(work/'metadata/videos.json',{'created_at':datetime.now().isoformat(timespec='seconds'),'videos':rows}); dump_json(work/'frames/frame_manifest.json',{'videos':frame_docs}); print(work)
if __name__=='__main__': main()
