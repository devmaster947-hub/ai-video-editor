#!/usr/bin/env python3
"""Render variants once from source time ranges and the validated edit plan."""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
from functools import lru_cache
from pathlib import Path

from utils import config,dump_json,encoder_args,ffprobe,load_json,require,run,seconds


def esc(p): return str(Path(p).resolve()).replace('\\','/').replace(':','\\:').replace("'","\\'")
def ass_metric(value): return float(value)*288/1920
def ass_colour(value):
    raw=str(value).lstrip('#'); return f'&H00{raw[4:6]}{raw[2:4]}{raw[0:2]}'


def bgm_tracks(cfg,root):
    rows=[]
    for item in cfg.get('bgm_tracks',[]):
        path=item.get('path') if isinstance(item,dict) else item
        volume=float(item.get('volume',cfg['bgm_volume'])) if isinstance(item,dict) else float(cfg['bgm_volume'])
        resolved=Path(path); resolved=resolved if resolved.is_absolute() else root/resolved
        if not resolved.is_file(): raise ValueError(f'missing background music file: {resolved}')
        rows.append({'path':str(resolved.resolve()),'volume':volume})
    return rows


def source_segments(shot):
    segments=shot.get('segments') or [{
        'source':shot.get('source') or shot.get('source_path'),
        'start':shot.get('start',0),
        'end':shot.get('end'),
        'duration':shot.get('duration'),
    }]
    rows=[]
    for segment in segments:
        source=segment.get('source') or segment.get('source_path') or shot.get('source') or shot.get('source_path')
        start=seconds(segment.get('start'))
        duration=seconds(segment.get('duration'))
        end=seconds(segment.get('end'),start+duration)
        if not source or not Path(source).is_file(): raise ValueError(f"{shot['shot_id']}: missing source media {source}")
        if end<=start and duration>0: end=start+duration
        if end<=start: raise ValueError(f"{shot['shot_id']}: invalid source range")
        rows.append((str(source),start,end-start))
    return rows


@lru_cache(maxsize=None)
def source_dimensions(source):
    video=next((x for x in ffprobe(source).get('streams',[]) if x.get('codec_type')=='video'),None)
    if not video: raise ValueError(f'no video stream in {source}')
    return int(video['width']),int(video['height'])


def delogo_filter(shot,cfg,source):
    if not (cfg.get('repair_burned_captions',True) and shot.get('burned_caption') and shot.get('caption_interferes')): return ''
    bbox=shot.get('caption_bbox')
    if not isinstance(bbox,list) or len(bbox)!=4: raise ValueError(f"{shot['shot_id']}: interfering caption requires normalized caption_bbox [x,y,w,h]")
    x,y,w,h=(max(0.0,min(1.0,float(value))) for value in bbox); width,height=source_dimensions(source)
    px=max(1,min(width-3,round(width*x))); py=max(1,min(height-3,round(height*y)))
    pw=max(1,min(width-px-1,round(width*w))); ph=max(1,min(height-py-1,round(height*h)))
    # delogo interpolates the covered region in the same final FFmpeg graph. The
    # border clamps prevent invalid rectangles when a normalized box touches an edge.
    return f'delogo=x={px}:y={py}:w={pw}:h={ph},'


def build(variant,shots,cfg,narr,srt,dest,bgm=None):
    inputs=[]; filters=[]; shot_labels=[]; frame_cursor=0; target_cursor=0; input_index=0; repaired=[]
    for clip_no,item in enumerate(variant.get('clips',[])):
        shot=shots[item['shot_id']]; segment_labels=[]; segments=source_segments(shot)
        source_duration=sum(x[2] for x in segments); target_cursor+=float(item['target_duration'])
        next_frames=round(target_cursor*30); out_frames=next_frames-frame_cursor; out_duration=out_frames/30; frame_cursor=next_frames
        if out_duration<=0: raise ValueError(f"{variant['variant_id']}: non-positive target duration")
        speed=source_duration/out_duration; segment_frame_cursor=0; source_cursor=0.0
        if any(delogo_filter(shot,cfg,source) for source,_,_ in segments): repaired.append(shot['shot_id'])
        for segment_no,(source,start,duration) in enumerate(segments):
            repair=delogo_filter(shot,cfg,source)
            source_cursor+=duration; remaining=len(segments)-segment_no-1
            segment_frame_end=(out_frames if not remaining else round(source_cursor/source_duration*out_frames))
            segment_frame_end=max(segment_frame_cursor+1,min(out_frames-remaining,segment_frame_end))
            segment_frames=segment_frame_end-segment_frame_cursor; segment_frame_cursor=segment_frame_end
            # Decode a small guard beyond the selected range, then trim exactly in
            # the graph. This avoids losing the last frame on low/odd source FPS.
            inputs += ['-ss',f'{start:.6f}','-t',f'{duration+0.1:.6f}','-i',source]
            label=f's{clip_no}_{segment_no}'
            filters.append(
                f'[{input_index}:v]trim=duration={duration+0.05:.8f},setpts=PTS-STARTPTS,'
                f'{repair}scale=1080:1920:force_original_aspect_ratio=increase,'
                f'crop=1080:1920,setsar=1,setpts=PTS/{speed:.8f},fps=30,'
                f'trim=end_frame={segment_frames},setpts=PTS-STARTPTS[{label}]'
            )
            segment_labels.append(f'[{label}]'); input_index+=1
        shot_label=f'v{clip_no}'
        if len(segment_labels)==1:
            filters.append(f'{segment_labels[0]}null[{shot_label}]')
        else:
            filters.append(''.join(segment_labels)+f'concat=n={len(segment_labels)}:v=1:a=0[{shot_label}]')
        shot_labels.append(f'[{shot_label}]')
    if not shot_labels: raise ValueError('variant has no clips')
    total=round(frame_cursor/30,6); inputs += ['-i',narr['voiceover_path']]; audio_index=input_index
    if bgm:
        inputs += ['-stream_loop','-1','-i',bgm['path']]
        bgm_index=audio_index+1
    style=','.join([
        f"FontName={cfg['subtitle_font_name']}",f"FontSize={ass_metric(cfg['subtitle_font_size']):.2f}",
        f"PrimaryColour={ass_colour(cfg['subtitle_text_color'])}",f"OutlineColour={ass_colour(cfg['subtitle_outline_color'])}",'BorderStyle=1',
        f"Outline={ass_metric(cfg['subtitle_outline']):.2f}",f"Shadow={ass_metric(cfg['subtitle_shadow']):.2f}",
        f"Bold={-1 if cfg['subtitle_bold'] else 0}",'Alignment=2',f"MarginV={ass_metric(cfg['subtitle_margin_v']):.2f}",'WrapStyle=0'
    ])
    filters.append(''.join(shot_labels)+f'concat=n={len(shot_labels)}:v=1:a=0,trim=end_frame={frame_cursor},setpts=PTS-STARTPTS[base]')
    filters.append(f"[base]subtitles=filename='{esc(srt)}':fontsdir='{esc(cfg['subtitle_fonts_dir'])}':original_size=1080x1920:force_style='{style}'[vout]")
    audio_map=f'{audio_index}:a:0'
    if bgm:
        # The BGM gain is constant for the full program. Do not add sidechain
        # compression, speech-triggered ducking, fades, or volume automation.
        filters += [
            f'[{audio_index}:a:0]aformat=sample_rates=48000:channel_layouts=stereo[voice]',
            f'[{bgm_index}:a:0]aformat=sample_rates=48000:channel_layouts=stereo,volume={bgm["volume"]:.6f},atrim=duration={total:.6f},asetpts=PTS-STARTPTS[bgm]',
            '[voice][bgm]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,alimiter=limit=0.98[aout]',
        ]
        audio_map='[aout]'
    enc,enc_name=encoder_args(cfg)
    cmd=['ffmpeg','-hide_banner','-loglevel','error','-y',*inputs,'-filter_complex',';'.join(filters),'-map','[vout]','-map',audio_map,*enc,'-r','30','-fps_mode','cfr','-c:a','aac','-b:a','192k','-t',f'{total:.6f}','-movflags','+faststart',dest]
    result=run(cmd,check=False)
    if result.returncode and enc_name=='h264_videotoolbox':
        pos=cmd.index('-c:v'); cmd=cmd[:pos]+['-c:v','libx264','-preset','veryfast','-crf','22']+cmd[pos+6:]; result=run(cmd,check=False); enc_name='libx264'
    if result.returncode: raise RuntimeError(result.stderr.strip())
    return {'variant_id':variant['variant_id'],'output':str(Path(dest).resolve()),'encoder':enc_name,'formal_encode_count':1,'source_kind':'source_time_ranges','caption_repaired_shot_ids':repaired,'background_music':None if not bgm else {'path':bgm['path'],'volume':bgm['volume'],'mix_mode':'constant'}}


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--variants-dir',default='work/variants'); ap.add_argument('--library',default='work/selected_shot_library.json'); ap.add_argument('--config',required=True); ap.add_argument('--narration',default='work/narration_manifest.json'); ap.add_argument('--subtitles-dir',default='work/subtitles'); ap.add_argument('--output-dir',required=True); ap.add_argument('--report',default='work/render_report.json'); a=ap.parse_args(); require('ffmpeg'); cfg=config(a.config); music=bgm_tracks(cfg,Path(__file__).resolve().parents[1])
    shots={x['shot_id']:x for x in load_json(a.library,{}).get('shots',[])}; narr=load_json(a.narration,{}); out=Path(a.output_dir); out.mkdir(parents=True,exist_ok=True); rows=[]; variants=[load_json(x,{}) for x in sorted(Path(a.variants_dir).glob('variant_*.json'))]
    if not variants: raise ValueError('no variants to render')
    with ThreadPoolExecutor(max_workers=min(int(cfg['max_render_workers']),len(variants))) as pool:
        jobs={pool.submit(build,v,shots,cfg,narr,Path(a.subtitles_dir)/(v['variant_id']+'.srt'),out/(v['variant_id']+'.mp4'),music[i%len(music)] if music else None):v['variant_id'] for i,v in enumerate(variants)}
        for job in as_completed(jobs): rows.append(job.result())
    rows.sort(key=lambda x:x['variant_id'])
    dump_json(a.report,{'renders':rows,'formal_encode_count':len(rows),'intermediate_shot_encode_count':0}); print(out)


if __name__=='__main__': main()
