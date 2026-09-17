#!/usr/bin/env python3
import hashlib,json,re,shutil,subprocess,time
from pathlib import Path

VIDEO_EXTS={'.mp4','.mov','.mkv','.m4v','.avi','.webm'}
USABLE_POSITIONS={'opening','product_intro','demo','detail','reaction','result','ending'}
PRODUCT_INTERACTIONS={'none','holding','showing','using','testing','comparing','result_show'}
PRODUCT_STATES={'unknown','before','during','after'}
CONTINUITY_RELATIONS={'independent','action_continue','product_continue','scene_continue','state_change'}
DEFAULT_CONFIG={
  'platform':'TikTok','target_country':'美国','target_language':'英语',
  'videoCount':5,'target_duration':25,'generate_subtitles':True,
  'narrationMode':'script','voiceStyle':'ugc_creator',
  'voiceover_path':'input/voiceover.wav','render_encoder':'auto',
  'bgm_tracks':[],'bgm_volume':0.12,'bgm_mix_mode':'constant',
  'min_speed_ratio':0.92,'max_speed_ratio':1.30,'subtitle_style':'bottom_safe',
  'subtitle_font_name':'Hiragino Sans GB W6','subtitle_fonts_dir':'/System/Library/Fonts','subtitle_font_size':68,
  'subtitle_text_color':'#FFD800','subtitle_outline_color':'#000000','subtitle_bold':True,
  'subtitle_margin_v':220,'subtitle_max_line_units':28,'subtitle_max_lines':2,
  'subtitle_outline':4,'subtitle_shadow':0,
  'tts_voice':'','default_tts_voice':'Tingting','tts_rate':230,'whisper_model':'small',
  'tts_pronunciation_lexicon':{'T恤':'踢恤'},
  'frame_interval':1.0,'short_shot_threshold':2.0,
  'merge_target_duration':4.0,'merge_min_duration':3.5,
  'merge_max_duration':4.5,'max_render_workers':3,
  'cache_dir':'cache/videos','repair_burned_captions':True,
  'strategy_workflow_id':'VideoEditingPolicyV1','strategy_timeout_seconds':180,
  'strategy_poll_seconds':1.5,'lzstudio_cli_path':''
}

def load_json(path,default=None):
    p=Path(path); return json.loads(p.read_text(encoding='utf-8')) if p.exists() else default
def dump_json(path,data):
    p=Path(path); p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); return p
def seconds(value,default=0.0):
    if isinstance(value,(int,float)): return float(value)
    if isinstance(value,str):
        try:
            parts=[float(x) for x in value.strip().split(':')]
            if len(parts)<=3: return sum(x*(60**i) for i,x in enumerate(reversed(parts)))
        except ValueError: pass
    return float(default)
def timestamp(value):
    total=max(0.0,seconds(value)); whole=int(total); fraction=total-whole; h,rem=divmod(whole,3600); m,s=divmod(rem,60)
    base=f'{h:02d}:{m:02d}:{s:02d}' if h else f'{m:02d}:{s:02d}'
    return base if fraction<.0005 else f'{base}.{round(fraction*1000):03d}'
def normalize_shot(shot):
    """Add V4 semantic fields while preserving operational/legacy metadata."""
    row=dict(shot or {}); old_type=row.get('shot_type','')
    if old_type in ('original','merged'):
        row.setdefault('merge_type',old_type); row['shot_type']=''
    time_value=row.get('time') if isinstance(row.get('time'),dict) else {}
    start=seconds(time_value.get('start',row.get('start',0))); end=seconds(time_value.get('end',row.get('end',start)))
    duration=seconds(time_value.get('duration',row.get('duration',max(0,end-start))),max(0,end-start))
    if end<=start and duration>0: end=start+duration
    row['time']={'start':timestamp(start),'end':timestamp(end),'duration':round(duration,3)}
    if 'start' in row: row['start']=round(start,3)
    if 'end' in row: row['end']=round(end,3)
    if 'duration' in row: row['duration']=round(duration,3)
    row['description']=str(row.get('description') or row.get('visual_summary') or '')
    person=row.get('person') if isinstance(row.get('person'),dict) else {}
    row['person']={k:str(person.get(k,'') or '') for k in ('person_id','appearance','action','emotion')}
    product=row.get('product') if isinstance(row.get('product'),dict) else {}
    interaction=str(product.get('interaction','none') or 'none'); state=str(product.get('state','unknown') or 'unknown')
    row['product']={'visible':bool(product.get('visible',False)),'name':str(product.get('name','') or ''),'interaction':interaction if interaction in PRODUCT_INTERACTIONS else 'none','state':state if state in PRODUCT_STATES else 'unknown'}
    row['scene']=str(row.get('scene','') or '')
    row['shot_type']=str(row.get('shot_type','') or '')
    positions=row.get('usable_position',[]); positions=[positions] if isinstance(positions,str) else positions
    row['usable_position']=[x for x in positions if x in USABLE_POSITIONS]
    continuity=row.get('continuity') if isinstance(row.get('continuity'),dict) else {}
    row['continuity']={k:(str(continuity.get(k,'independent')) if str(continuity.get(k,'independent')) in CONTINUITY_RELATIONS else 'independent') for k in ('previous_relation','next_relation')}
    tags=row.get('tags',[]); row['tags']=[str(x) for x in ([tags] if isinstance(tags,str) else tags) if str(x).strip()]
    row['visual_facts']=normalize_visual_facets(row.get('visual_facts'),row)
    edit=row.get('edit') if isinstance(row.get('edit'),dict) else {}
    selectable=bool(edit.get('selectable',row.get('eligible_for_edit',True)))
    row['edit']={'merge_allowed':bool(edit.get('merge_allowed',True)),'selectable':selectable}
    row['eligible_for_edit']=bool(row.get('eligible_for_edit',selectable) and selectable)
    row.setdefault('visual_summary',row['description'])
    return row
def run(cmd,check=True):
    r=subprocess.run([str(x) for x in cmd],text=True,capture_output=True)
    if check and r.returncode: raise RuntimeError(r.stderr.strip() or 'command failed: '+' '.join(map(str,cmd)))
    return r
def require(*names):
    missing=[x for x in names if not shutil.which(x)]
    if missing: raise RuntimeError('Missing required tools: '+', '.join(missing))
def videos(path): return sorted(p for p in Path(path).iterdir() if p.is_file() and p.suffix.lower() in VIDEO_EXTS)
def config(path=None):
    raw=load_json(path,{}) if path else {}; d=dict(DEFAULT_CONFIG); d.update(raw)
    requested=raw.get('videoCount',raw.get('variant_count',d['videoCount']))
    if isinstance(requested,str) and requested.lower()=='auto':
        d['_video_count_explicit']=False; requested=5
    else: d['_video_count_explicit']='videoCount' in raw or 'variant_count' in raw
    d['videoCount']=int(requested); d['variant_count']=d['videoCount']
    if d['videoCount']<1 or d['videoCount']>10: raise ValueError('videoCount must be 1..10')
    if d.get('narrationMode') not in ('audio','script'): raise ValueError('narrationMode must be audio or script')
    if d.get('voiceStyle')!='ugc_creator': raise ValueError('voiceStyle must be ugc_creator')
    if d.get('bgm_mix_mode')!='constant': raise ValueError('bgm_mix_mode must be constant; automatic ducking is not supported')
    if not 0<float(d.get('bgm_volume',0.12))<=1: raise ValueError('bgm_volume must be greater than 0 and no more than 1')
    if not isinstance(d.get('bgm_tracks'),list): raise ValueError('bgm_tracks must be a list')
    for track in d['bgm_tracks']:
        if isinstance(track,str):
            if not track.strip(): raise ValueError('bgm track paths must be non-empty strings')
        elif isinstance(track,dict):
            if not isinstance(track.get('path'),str) or not track['path'].strip(): raise ValueError('each bgm track object requires a non-empty path')
            if not 0<float(track.get('volume',d['bgm_volume']))<=1: raise ValueError('each bgm track volume must be greater than 0 and no more than 1')
        else: raise ValueError('bgm_tracks entries must be path strings or objects with path and optional volume')
    if int(d['max_render_workers'])<1: raise ValueError('max_render_workers must be positive')
    if not 0<float(d['min_speed_ratio'])<=1: raise ValueError('min_speed_ratio must be 0..1')
    if not 1<=float(d['max_speed_ratio'])<=1.3: raise ValueError('max_speed_ratio must be 1..1.3')
    if not 0<float(d['short_shot_threshold'])<=float(d['merge_min_duration'])<=float(d['merge_target_duration'])<=float(d['merge_max_duration']): raise ValueError('invalid short-shot merge thresholds')
    if d.get('subtitle_style') not in ('bottom_safe','bottom_clean'): raise ValueError('subtitle_style must be bottom_safe')
    if not 20<=int(d['subtitle_font_size'])<=80: raise ValueError('subtitle_font_size must be 20..80')
    if not isinstance(d.get('subtitle_fonts_dir'),str) or not d['subtitle_fonts_dir'].strip(): raise ValueError('subtitle_fonts_dir must be a non-empty path')
    if any(not re.fullmatch(r'#[0-9A-Fa-f]{6}',str(d[k])) for k in ('subtitle_text_color','subtitle_outline_color')): raise ValueError('subtitle colors must use #RRGGBB')
    if not isinstance(d.get('subtitle_bold'),bool): raise ValueError('subtitle_bold must be boolean')
    if not 180<=int(d['subtitle_margin_v'])<=360: raise ValueError('subtitle_margin_v must stay inside the lower safe area (180..360)')
    if not 20<=int(d['subtitle_max_line_units'])<=40 or int(d['subtitle_max_lines']) not in (1,2): raise ValueError('invalid subtitle line limits')
    if not isinstance(d.get('tts_pronunciation_lexicon'),dict): raise ValueError('tts_pronunciation_lexicon must be an object')
    if not isinstance(d.get('tts_voice'),str): raise ValueError('tts_voice must be a string; leave it empty to use the default voice')
    if not isinstance(d.get('strategy_workflow_id'),str) or not d['strategy_workflow_id'].strip(): raise ValueError('strategy_workflow_id must be a non-empty string')
    if float(d.get('strategy_timeout_seconds',180))<10: raise ValueError('strategy_timeout_seconds must be at least 10')
    if not .2<=float(d.get('strategy_poll_seconds',1.5))<=10: raise ValueError('strategy_poll_seconds must be 0.2..10')
    if not isinstance(d.get('lzstudio_cli_path',''),str): raise ValueError('lzstudio_cli_path must be a string')
    if not isinstance(d.get('default_tts_voice'),str) or not d['default_tts_voice'].strip(): raise ValueError('default_tts_voice must be a non-empty string')
    return d

VISUAL_FACET_KEYS=('garment_area','action','result')
VISUAL_ALIASES={
  'garment_area':{
    'side waist':'side_waist','side_waist':'side_waist','waist side':'side_waist',
    'waist':'waist','waistband':'waist','pants waist':'waist','pants_waist':'waist',
    'chest':'chest','neckline':'neckline','low neckline':'neckline','low_neckline':'neckline',
    'sleeve':'sleeve','product':'product','full body':'full_body','full_body':'full_body',
  },
  'action':{
    'gathering':'gather','gathered':'gather','gathers':'gather','tightening':'tighten','tightened':'tighten',
    'fastening':'fasten','fastened':'fasten','pinning':'fasten','pinned':'fasten','fixing':'fasten','fixed':'fasten',
    'holding':'holding','showing':'showing','using':'using','testing':'testing','comparing':'comparing',
    'result_show':'result_show','result show':'result_show','display':'showing','decorating':'decorate','decoration':'decorate',
  },
  'result':{
    'loose':'loose','tightened':'tightened','tight':'tightened','gathered':'gathered','fixed':'fixed',
    'secured':'fixed','shaped':'shaped','visible':'visible','before':'before','during':'during','after':'after',
  },
}
def _facet_token(value):
    return re.sub(r'[^a-z0-9_]+','_',str(value or '').strip().lower().replace('-',' ')).strip('_')
def normalize_visual_facets(value,shot=None):
    src=value if isinstance(value,dict) else {}; shot=shot or {}; tags=shot.get('tags',[]); tags=[tags] if isinstance(tags,str) else tags
    candidates={k:list(src.get(k,[]) if isinstance(src.get(k,[]),list) else [src.get(k,'')]) for k in VISUAL_FACET_KEYS}
    if not value:
        description=str(shot.get('description') or shot.get('visual_summary') or '')
        candidates['garment_area'] += tags
        candidates['action'] += tags
        candidates['result'] += tags
        for key in VISUAL_FACET_KEYS: candidates[key].append(description)
        product=shot.get('product',{}) if isinstance(shot.get('product',{}),dict) else {}
        person=shot.get('person',{}) if isinstance(shot.get('person',{}),dict) else {}
        candidates['action'] += [product.get('interaction',''),person.get('action','')]
        candidates['result'] += [product.get('state','')]
    out={}
    for key,items in candidates.items():
        aliases=VISUAL_ALIASES[key]; values=[]
        for raw in items:
            plain=str(raw or '').strip().lower().replace('_',' ')
            token=aliases.get(plain)
            if not token:
                for alias in sorted(aliases,key=len,reverse=True):
                    if re.search(r'(?<![a-z])'+re.escape(alias)+r'(?![a-z])',plain): token=aliases[alias]; break
            if not token:
                normalized=_facet_token(raw)
                token=normalized if normalized in set(aliases.values()) else ''
            if token and token not in values: values.append(token)
        out[key]=values
    return out
def visual_requirements(value):
    return normalize_visual_facets(value or {})
def shot_covers_requirements(shot,requirements):
    facts=normalize_visual_facets(shot.get('visual_facts'),shot); needed=visual_requirements(requirements)
    missing={k:[x for x in needed[k] if x not in facts[k]] for k in VISUAL_FACET_KEYS}
    missing={k:v for k,v in missing.items() if v}
    return not missing,missing
def video_count(cfg,eligible_shot_count):
    """Resolve explicit videoCount or conservatively suggest 3/5/5-10 from material depth."""
    if cfg.get('_video_count_explicit'): return int(cfg['videoCount'])
    count=int(eligible_shot_count)
    if count<12: return 3
    if count<30: return 5
    return min(10,max(5,count//6))
def speed_bounds(cfg):
    """Keep the 1.3x ceiling hard even when a legacy config requests more."""
    return float(cfg.get('min_speed_ratio',.92)),min(1.3,float(cfg.get('max_speed_ratio',1.3)))
def safe_name(name): return ''.join(c if c.isalnum() or c in '-_' else '_' for c in Path(name).stem)
def ffprobe(path):
    if shutil.which('ffprobe'): return json.loads(run(['ffprobe','-v','error','-show_entries','format=duration:stream=index,codec_type,width,height,avg_frame_rate','-of','json',path]).stdout)
    require('ffmpeg'); result=run(['ffmpeg','-hide_banner','-i',path],check=False); info=result.stderr
    dm=re.search(r'Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)',info); dur=(int(dm.group(1))*3600+int(dm.group(2))*60+float(dm.group(3))) if dm else 0; streams=[]
    vm=re.search(r'Video:.*?(\d{2,5})x(\d{2,5}).*?(\d+(?:\.\d+)?)\s*fps',info)
    if vm: streams.append({'index':0,'codec_type':'video','width':int(vm.group(1)),'height':int(vm.group(2)),'avg_frame_rate':f'{vm.group(3)}/1'})
    if re.search(r'Audio:',info): streams.append({'index':len(streams),'codec_type':'audio'})
    return {'format':{'duration':str(dur)},'streams':streams}
def duration(path): return float(ffprobe(path).get('format',{}).get('duration') or 0)
def fingerprint(paths,extra=None):
    h=hashlib.sha256()
    for p in sorted(map(Path,paths),key=str):
        if p.exists(): h.update(str(p.resolve()).encode()); h.update(file_sha256(p).encode())
    h.update(json.dumps(extra or {},sort_keys=True,ensure_ascii=False).encode()); return h.hexdigest()
def file_sha256(path,chunk_size=1024*1024):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(chunk_size),b''): h.update(chunk)
    return h.hexdigest()
def video_cache_key(path):
    """Stable cache key required by V3: content hash + duration + byte size."""
    p=Path(path); sha=file_sha256(p); dur=round(duration(p),3); size=p.stat().st_size
    raw=f'{sha}:{dur:.3f}:{size}'.encode()
    return hashlib.sha256(raw).hexdigest(),{'source_sha256':sha,'duration':dur,'size':size}
def detect_unsafe_ranges(path,black_duration=.15,freeze_duration=.8):
    require('ffmpeg'); r=run(['ffmpeg','-hide_banner','-i',path,'-vf',f'blackdetect=d={black_duration}:pix_th=0.10,freezedetect=n=-60dB:d={freeze_duration}','-an','-f','null','-'],check=False); s=r.stderr; total=duration(path); rows=[]
    for m in re.finditer(r'black_start:([\d.]+)\s+black_end:([\d.]+)',s): rows.append({'type':'black','start':float(m.group(1)),'end':float(m.group(2))})
    starts=[float(x) for x in re.findall(r'freeze_start:\s*([\d.]+)',s)]; ends=[float(x) for x in re.findall(r'freeze_end:\s*([\d.]+)',s)]
    for i,st in enumerate(starts): rows.append({'type':'freeze','start':st,'end':ends[i] if i<len(ends) else total})
    return sorted(rows,key=lambda x:(x['start'],x['end']))
def overlaps(start,end,ranges,tolerance=.08): return [r for r in ranges if min(end,float(r['end']))-max(start,float(r['start']))>tolerance]
def rate(value):
    try: a,b=value.split('/'); return float(a)/float(b)
    except Exception: return 0
def encoder_args(cfg):
    want=cfg.get('render_encoder','auto'); encoders=run(['ffmpeg','-hide_banner','-encoders']).stdout
    if want in ('auto','h264_videotoolbox') and 'h264_videotoolbox' in encoders: return ['-c:v','h264_videotoolbox','-b:v','8M','-realtime','true'],'h264_videotoolbox'
    return ['-c:v','libx264','-preset','veryfast','-crf','22'],'libx264'
class Timer:
    def __init__(self,name,rows): self.name=name; self.rows=rows
    def __enter__(self): self.start=time.monotonic(); return self
    def __exit__(self,*_): self.rows.append({'stage':self.name,'seconds':round(time.monotonic()-self.start,3),'cached':False})
