#!/usr/bin/env python3
import argparse
from pathlib import Path
from utils import config,detect_unsafe_ranges,dump_json,ffprobe,load_json,normalize_shot,run,shot_covers_requirements
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--videos-dir',required=True); ap.add_argument('--variants-dir',default='work/variants'); ap.add_argument('--library',default='work/shot_library.json'); ap.add_argument('--narration',default='work/narration_manifest.json'); ap.add_argument('--config',required=True); ap.add_argument('--output',required=True); ap.add_argument('--qa-dir',required=True); a=ap.parse_args(); config(a.config); reports=[]; errors=[]; qa=Path(a.qa_dir); qa.mkdir(parents=True,exist_ok=True)
    plans={p.stem:load_json(p,{}) for p in Path(a.variants_dir).glob('variant_*.json')}
    shots={x['shot_id']:normalize_shot(x) for x in load_json(a.library,{}).get('shots',[])}; segments={x['script_id']:x for x in load_json(a.narration,{}).get('script_segments',[])}
    for p in sorted(Path(a.videos_dir).glob('variant_*.mp4')):
        probe=ffprobe(p); dur=float(probe.get('format',{}).get('duration') or 0); streams=probe.get('streams',[]); video=next((x for x in streams if x.get('codec_type')=='video'),{}); unsafe=detect_unsafe_ranges(p); verr=[]
        if (video.get('width'),video.get('height'))!=(1080,1920): verr.append('尺寸应为 1080x1920')
        if not any(x.get('codec_type')=='audio' for x in streams): verr.append('缺少口播音轨')
        if any(x['type']=='black' and x['end']>=dur-.1 for x in unsafe): verr.append('末尾检测到黑屏')
        if any(x['type']=='freeze' and x['end']-x['start']>=.8 for x in unsafe): verr.append('检测到超过 0.8s 的冻结画面')
        for clip in plans.get(p.stem,{}).get('clips',[]):
            shot=shots.get(clip.get('shot_id'),{}); segment=segments.get(clip.get('script_id'),{}); covered,missing=shot_covers_requirements(shot,segment.get('visual_requirements',{}))
            if not covered: verr.append(f"音画覆盖失败 {clip.get('script_id')}: {missing}")
        times=[('first',.2),('middle',max(.2,dur/2)),('last',max(.2,dur-.25))]; cursor=0
        for i,clip in enumerate(plans.get(p.stem,{}).get('clips',[])[:-1],1): cursor+=float(clip['target_duration']); times += [(f'transition_{i:02d}_before',max(.05,cursor-.08)),(f'transition_{i:02d}_after',min(dur-.05,cursor+.08))]
        frames=[]
        for label,t in times:
            dest=qa/f'{p.stem}_{label}.png'; result=run(['ffmpeg','-hide_banner','-loglevel','error','-y','-ss',f'{t:.3f}','-i',p,'-frames:v','1',dest],check=False)
            if result.returncode or not dest.exists(): verr.append(f'{label} 抽帧失败')
            else: frames.append(str(dest.resolve()))
        errors.extend(f'{p.name}: {x}' for x in verr); reports.append({'video':str(p.resolve()),'duration':round(dur,3),'unsafe_ranges':unsafe,'qa_frames':frames,'passed':not verr,'errors':verr})
    if not reports: errors.append('未找到渲染视频')
    dump_json(a.output,{'passed':not errors,'errors':errors,'videos':reports})
    if errors: raise SystemExit('\n'.join(errors))
    print(a.output)
if __name__=='__main__': main()
