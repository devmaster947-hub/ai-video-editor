#!/usr/bin/env python3
"""Prepare narration from exactly one input: supplied audio or supplied script."""
import argparse,difflib,re,shutil,subprocess,tempfile,sys
from pathlib import Path
from utils import VISUAL_FACET_KEYS,config,duration,dump_json,load_json,normalize_shot,run,shot_covers_requirements,visual_requirements

PUNCT='，。！？；,.!?;:：'
def display_text(s): return re.sub(r'[，。！？；,.!?;:：]+$','',re.sub(r'\s+',' ',str(s or ''))).strip(PUNCT+' ')
def text_units(text): return sum(2 if '\u4e00'<=c<='\u9fff' else 1 for c in str(text or '').replace('\n',''))
def caption_chunks(text,segment_id,max_line_units=28,max_lines=2):
    shown=display_text(text); tokens=re.findall(r'[\u4e00-\u9fff]|[A-Za-z0-9]+(?:[\'’-][A-Za-z0-9]+)*|[^\s]',shown); cues=[]; lines=[]; line=''
    for token in tokens:
        spacer=' ' if line and re.fullmatch(r'[A-Za-z0-9]',token[0]) and re.fullmatch(r'[A-Za-z0-9]',line[-1]) else ''
        candidate=line+spacer+token
        if line and text_units(candidate)>max_line_units:
            lines.append(line); line=token
            if len(lines)==max_lines:
                cues.append({'text':'\n'.join(lines),'semantic_id':segment_id}); lines=[]
        else: line=candidate
    if line: lines.append(line)
    if lines: cues.append({'text':'\n'.join(lines),'semantic_id':segment_id})
    if not cues: raise ValueError(f'{segment_id}: narration segment contains no displayable text')
    if any(len(x['text'].splitlines())>max_lines or any(text_units(line)>max_line_units for line in x['text'].splitlines()) for x in cues): raise ValueError(f'{segment_id}: caption wrapping exceeds configured safe width')
    return cues
def phrases(text,segment_id,pause_after_ms=180,limit=28):
    """Backward-compatible caption chunk entry point; never drives TTS synthesis."""
    return caption_chunks(text,segment_id,limit,2)
def spoken_alias(text,cfg):
    result=str(text or '')
    for source,target in sorted(cfg.get('tts_pronunciation_lexicon',{}).items(),key=lambda x:-len(str(x[0]))): result=result.replace(str(source),str(target))
    return result
AREA_PATTERNS={
  'side_waist':r'侧腰|侧边|side\s*waist', 'waist':r'裤腰|腰围|\bwaist(?:band)?\b',
  'chest':r'胸口|胸前|\bchest\b', 'neckline':r'领口|低领|\bneckline\b', 'sleeve':r'袖口|袖子|\bsleeve\b'
}
def validate_visual_focus(text,requirements,segment_id):
    found={name for name,pattern in AREA_PATTERNS.items() if re.search(pattern,text,re.I)}
    if 'side_waist' in found: found.discard('waist')
    if len(found)>1: raise ValueError(f'{segment_id}: one narration segment may describe only one visible garment area: {sorted(found)}')
    req=visual_requirements(requirements)
    if any(len(req[k])!=1 for k in VISUAL_FACET_KEYS): raise ValueError(f'{segment_id}: visual_requirements must contain exactly one garment_area, action, and result')
    return req
def load_optimized_response(path,cfg,script_path,library_path):
    response=load_json(path,{}) or {}; mode=cfg['narrationMode']; source=Path(script_path).read_text(encoding='utf-8').strip() if Path(script_path).exists() else ''
    if mode=='script' and not source: raise ValueError('script narrationMode requires input/voiceover_script.txt')
    if response.get('narrationMode',mode)!=mode: raise ValueError('narration response mode does not match config narrationMode')
    rows=response.get('segments',[])
    if not rows: raise ValueError('GPT narration response must contain semantic segments')
    library={x.get('shot_id'):normalize_shot(x) for x in load_json(library_path,{}).get('shots',[])}
    segments=[]; seen=set()
    for i,row in enumerate(rows,1):
        sid=str(row.get('segment_id') or f'segment_{i:03d}')
        if sid in seen: raise ValueError(f'duplicate narration segment_id: {sid}')
        text=display_text(row.get('text','')); spoken=display_text(row.get('spoken_text','')); evidence=[str(x) for x in row.get('evidence_shot_ids',[]) if str(x)]
        unknown=[x for x in evidence if x not in library]
        if unknown: raise ValueError(f'{sid}: unknown evidence shot_ids: {unknown}')
        if not evidence: raise ValueError(f'{sid}: narration requires visible evidence_shot_ids')
        if mode=='script' and not spoken: raise ValueError(f'{sid}: script narration requires spoken_text')
        if not text: raise ValueError(f'{sid}: empty narration text')
        requirements=validate_visual_focus(text,row.get('visual_requirements'),sid)
        for shot_id in evidence:
            covered,missing=shot_covers_requirements(library[shot_id],requirements)
            if requirements and not covered: raise ValueError(f'{sid}: evidence shot {shot_id} does not cover visual requirements: {missing}')
        pause=max(120,min(280,int(row.get('pause_after_ms',180))))
        segments.append({'segment_id':sid,'text':text,'spoken_text':spoken or text,'pause_after_ms':pause,'visual_requirements':requirements,'evidence_shot_ids':evidence})
        seen.add(sid)
    optimized=display_text(response.get('optimized_script')) or ' '.join(x['text'] for x in segments)
    if mode=='audio': source=display_text(response.get('source_transcript')) or optimized
    return source,optimized,segments

def normalized_speech_text(text):
    return re.sub(r'[^\w\u4e00-\u9fff]+','',str(text or '')).lower()

def verify_audio_transcript(transcript,segments):
    heard=normalized_speech_text(transcript); planned=normalized_speech_text(''.join(x['text'] for x in segments))
    if not heard or not planned: raise RuntimeError('audio mode requires a non-empty transcript and narration segments')
    ratio=difflib.SequenceMatcher(None,heard,planned).ratio()
    if ratio<0.72: raise ValueError(f'audio narration response does not match the supplied audio transcript (similarity={ratio:.2f})')
def supplied_timings(path):
    d=load_json(path,{}); rows=d.get('cues',d if isinstance(d,list) else [])
    return [{'start':float(x['start']),'end':float(x['end']),'text':display_text(x['text'])} for x in rows if display_text(x.get('text',''))]
def whisper_words(audio,language,outdir,model='small'):
    exe=shutil.which('whisper') or str(Path(sys.executable).resolve().parent/'whisper')
    if not Path(exe).exists(): raise RuntimeError('supplied narration requires Whisper word timestamps or caption_timing_path')
    cmd=[exe,str(audio),'--model',model,'--output_format','json','--output_dir',str(outdir),'--word_timestamps','True']
    if language: cmd += ['--language',language]
    run(cmd); data=load_json(outdir/(Path(audio).stem+'.json'),{}); words=[]
    for seg in data.get('segments',[]):
        if seg.get('words'): words += seg['words']
        else: words.append({'word':seg.get('text',''),'start':seg['start'],'end':seg['end']})
    return words
def align(chunks,words,audio_duration):
    words=[w for w in words if display_text(w.get('word',''))]
    if not words: raise RuntimeError('Whisper returned no timed speech')
    weights=[max(1,len(display_text(w['word']))) for w in words]; total=sum(weights); boundaries=[]; acc=0
    for w,n in zip(words,weights): acc+=n; boundaries.append((acc/total,float(w['end'])))
    result=[]; chars=sum(len(x['text']) for x in chunks); acc=0; start=max(0,float(words[0]['start']))
    for i,c in enumerate(chunks):
        acc+=len(c['text']); ratio=acc/max(1,chars); end=next((t for r,t in boundaries if r>=ratio),float(words[-1]['end']))
        if i==len(chunks)-1: end=min(audio_duration,max(end,float(words[-1]['end'])))
        result.append({'start':round(start,3),'end':round(max(start+.08,end),3),'text':c['text'],'semantic_id':c['semantic_id']}); start=end
    return result
def assign_semantics(cues,chunks):
    ids=[]
    for chunk in chunks: ids.extend([chunk['semantic_id']]*max(1,len(chunk['text'])))
    cursor=0
    for cue in cues:
        cue['semantic_id']=ids[min(cursor,len(ids)-1)]; cursor+=max(1,len(cue['text']))
    return cues
def tts(segments,cfg,outdir):
    if not shutil.which('say'): raise RuntimeError('script-only mode requires macOS say or a supplied narration audio file')
    voice=str(cfg.get('tts_voice') or cfg.get('default_tts_voice') or 'Tingting').strip(); rate=max(120,int(cfg.get('tts_rate',230))); parts=[]; cues=[]; cursor=0
    for i,row in enumerate(segments):
        raw=outdir/f'segment_{i:03d}.aiff'; clean=outdir/f'segment_{i:03d}_clean.wav'; padded=outdir/f'segment_{i:03d}_padded.wav'
        subprocess.check_call(['say','-v',voice,'-r',str(rate),'-o',str(raw),spoken_alias(row['spoken_text'],cfg)])
        trim_filter='silenceremove=start_periods=1:start_duration=0.02:start_threshold=-50dB,areverse,silenceremove=start_periods=1:start_duration=0.08:start_threshold=-50dB,areverse'
        trimmed=run(['ffmpeg','-hide_banner','-loglevel','error','-y','-i',raw,'-af',trim_filter,'-ar','48000','-ac','1',clean],check=False)
        if trimmed.returncode or not clean.exists() or duration(clean)<=.05: run(['ffmpeg','-hide_banner','-loglevel','error','-y','-i',raw,'-ar','48000','-ac','1',clean])
        d=duration(clean)
        if d<=.05: raise RuntimeError('TTS produced empty audio; rerun where the macOS speech service is available or supply recorded narration')
        chunks=caption_chunks(row['text'],row['segment_id'],int(cfg['subtitle_max_line_units']),int(cfg['subtitle_max_lines'])); weights=[max(1,text_units(x['text'])) for x in chunks]; total=sum(weights); start=cursor; acc=0
        for chunk,weight in zip(chunks,weights):
            acc+=weight; end=cursor+d*acc/total; cues.append({'start':round(start,3),'end':round(end,3),'text':chunk['text'],'semantic_id':row['segment_id']}); start=end
        pause=0 if i==len(segments)-1 else max(120,min(320,int(row.get('pause_after_ms',180))))/1000
        run(['ffmpeg','-hide_banner','-loglevel','error','-y','-i',clean,'-af',f'apad=pad_dur={pause:.3f}','-t',f'{d+pause:.3f}','-ar','48000','-ac','1',padded])
        cursor+=d+pause; parts.append(padded)
    listing=outdir/'concat.txt'; listing.write_text('\n'.join("file '"+str(x.resolve()).replace("'","'\\''")+"'" for x in parts)+'\n',encoding='utf-8')
    voiceout=outdir/'voiceover.wav'; run(['ffmpeg','-y','-f','concat','-safe','0','-i',listing,'-ar','48000','-ac','1',voiceout])
    if duration(voiceout)<=.05: raise RuntimeError('concatenated TTS audio is empty')
    return voiceout,cues
def semantic_segments(cues,source_segments,audio_duration):
    source={x['segment_id']:x for x in source_segments}; groups=[]
    ids=[x['segment_id'] for x in source_segments]
    for index,sid in enumerate(ids):
        group=[x for x in cues if x.get('semantic_id')==sid]
        if not group: raise ValueError(f'{sid}: no aligned narration cues')
        row=source[sid]
        start=0.0 if index==0 else float(group[0]['start']); next_group=[x for x in cues if x.get('semantic_id')==ids[index+1]] if index+1<len(ids) else []
        end=float(next_group[0]['start']) if next_group else audio_duration
        groups.append({'script_id':sid,'start':round(start,3),'end':round(end,3),'duration':round(end-start,3),'text':row['text'],'spoken_text':row['spoken_text'],'cue_ids':[x['cue_id'] for x in group],'visual_requirements':row['visual_requirements'],'evidence_shot_ids':row['evidence_shot_ids']})
    return groups
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--config',required=True); ap.add_argument('--script',required=True); ap.add_argument('--response-file',required=True); ap.add_argument('--library',default='work/shot_library.json'); ap.add_argument('--output-dir',default='work/narration'); ap.add_argument('--output',default='work/narration_manifest.json'); a=ap.parse_args(); cfg=config(a.config); out=Path(a.output_dir); out.mkdir(parents=True,exist_ok=True)
    voice=Path(cfg['voiceover_path']); voice=voice if voice.is_absolute() else Path(a.config).resolve().parents[1]/voice; timing=cfg.get('caption_timing_path')
    script_text=Path(a.script).read_text(encoding='utf-8').strip() if Path(a.script).exists() else ''
    if cfg['narrationMode']=='audio':
        if not voice.is_file(): raise ValueError('audio narrationMode requires a supplied voiceover audio file')
        if script_text: raise ValueError('audio narrationMode is mutually exclusive with input/voiceover_script.txt')
    else:
        if not script_text: raise ValueError('script narrationMode requires input/voiceover_script.txt')
        if voice.is_file(): raise ValueError('script narrationMode is mutually exclusive with a supplied voiceover audio file')
        if timing: raise ValueError('caption_timing_path is only valid in audio narrationMode')
    source,optimized,source_segments=load_optimized_response(a.response_file,cfg,a.script,a.library)
    chunks=[]
    for row in source_segments: chunks.extend(caption_chunks(row['text'],row['segment_id'],int(cfg['subtitle_max_line_units']),int(cfg['subtitle_max_lines'])))
    if timing:
        timing=Path(timing); timing=timing if timing.is_absolute() else Path(a.config).resolve().parents[1]/timing
        if not voice.exists(): raise RuntimeError('caption_timing_path requires supplied narration audio')
        supplied=supplied_timings(timing); verify_audio_transcript(' '.join(x['text'] for x in supplied),source_segments); cues=assign_semantics(supplied,chunks); source=' '.join(x['text'] for x in supplied)
    elif cfg['narrationMode']=='audio':
        with tempfile.TemporaryDirectory() as td:
            words=whisper_words(voice,cfg.get('whisper_language'),Path(td),cfg.get('whisper_model','small'))
            transcript=' '.join(display_text(x.get('word','')) for x in words); verify_audio_transcript(transcript,source_segments); cues=align(chunks,words,duration(voice)); source=transcript
    else: voice,cues=tts(source_segments,cfg,out)
    if any(not x['text'] or re.fullmatch(r'[\W_]+',x['text']) for x in cues): raise RuntimeError('punctuation-only caption cue rejected')
    for i,cue in enumerate(cues,1): cue['cue_id']=f'cue_{i:03d}'
    d=duration(voice); segments=semantic_segments(cues,source_segments,d)
    dump_json(a.output,{'mode':'supplied_audio' if cfg['narrationMode']=='audio' else 'generated_segment_tts','narrationMode':cfg['narrationMode'],'voiceStyle':cfg['voiceStyle'],'tts_voice':None if cfg['narrationMode']=='audio' else str(cfg.get('tts_voice') or cfg.get('default_tts_voice') or 'Tingting'),'source_script':source,'optimized_script':optimized,'voiceover_path':str(voice.resolve()),'duration':d,'script_segments':segments,'cues':cues,'max_sync_error_ms':150}); print(a.output)
if __name__=='__main__': main()
