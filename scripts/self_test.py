#!/usr/bin/env python3
"""Fast regression checks for visual matching, captions, and creator TTS."""
import json,os,re,shutil,tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from lingzhi_task import API_KEY_GUIDANCE,CredentialConfigError,CredentialNotFoundError,_run_cli,require_valid_api_key,resolve_api_key,validate_api_key
from prepare_narration import caption_chunks,spoken_alias,tts,validate_visual_focus,verify_audio_transcript
from render_variants import ass_colour,ass_metric,bgm_tracks
from utils import config,duration,shot_covers_requirements,run

def check(condition,message):
    if not condition: raise AssertionError(message)

def test_visual_matching():
    req={'garment_area':['side_waist'],'action':['gather'],'result':['shaped']}
    shot={'visual_facts':{'garment_area':['side_waist'],'action':['gather'],'result':['shaped']}}
    covered,missing=shot_covers_requirements(shot,req); check(covered and not missing,'exact visual coverage should pass')
    bad={'visual_facts':{'garment_area':['chest'],'action':['fasten'],'result':['fixed']}}
    covered,missing=shot_covers_requirements(bad,req); check(not covered and 'garment_area' in missing,'unrelated visual evidence must fail')
    try: validate_visual_focus('T恤在侧边、胸口或袖口收一点',req,'segment_test')
    except ValueError: pass
    else: raise AssertionError('multi-area narration must be rejected')

def test_caption_layout():
    cfg=config(); cues=caption_chunks('这件T恤在侧腰轻轻收一下，版型看起来就利落很多了','segment_test',cfg['subtitle_max_line_units'],cfg['subtitle_max_lines'])
    check(all(len(x['text'].splitlines())<=2 for x in cues),'captions must stay within two lines')
    check(all(not re.search(r'[\u4e00-\u9fff] [\u4e00-\u9fff]',x['text']) for x in cues),'Chinese captions must not contain artificial character spacing')
    check(cfg['subtitle_font_size']==68 and cfg['subtitle_margin_v']==220,'bottom-safe subtitle defaults changed unexpectedly')
    check(cfg['subtitle_font_name']=='Hiragino Sans GB W6' and cfg['subtitle_fonts_dir']=='/System/Library/Fonts' and cfg['subtitle_bold'],'reference subtitle must use the loadable bold Chinese sans font')
    check(cfg['subtitle_outline']==4 and cfg['subtitle_shadow']==0,'reference subtitle must use a crisp four-pixel black outline')
    check(ass_colour(cfg['subtitle_text_color'])=='&H0000D8FF' and ass_colour(cfg['subtitle_outline_color'])=='&H00000000','reference yellow/black colors changed unexpectedly')
    check(abs(ass_metric(68)*1920/288-68)<.01 and abs(ass_metric(220)*1920/288-220)<.01,'ASS subtitle metrics must preserve output-pixel intent')

def test_narration_inputs():
    with tempfile.TemporaryDirectory() as td:
        root=Path(td)
        for mode in ('audio','script'):
            path=root/f'{mode}.json'; path.write_text(json.dumps({'narrationMode':mode,'tts_voice':''}),encoding='utf-8')
            cfg=config(path); check(cfg['narrationMode']==mode,f'{mode} narration mode must be accepted')
            check(cfg['default_tts_voice'],'empty optional tts_voice must retain a usable default voice')
        legacy=root/'legacy.json'; legacy.write_text(json.dumps({'narrationMode':'auto'}),encoding='utf-8')
        try: config(legacy)
        except ValueError: pass
        else: raise AssertionError('legacy auto narration mode must be rejected')
    segments=[{'text':'裤腰大了往下掉'},{'text':'在侧面别一下就合身'}]
    verify_audio_transcript('裤腰大了往下掉，在侧面别一下就合身。',segments)
    try: verify_audio_transcript('这是完全不同的口播内容',segments)
    except ValueError: pass
    else: raise AssertionError('audio mode must reject a rewritten narration response')

def test_constant_bgm_config():
    cfg=config(); check(cfg['bgm_mix_mode']=='constant','background music must default to constant gain')
    check(cfg['bgm_tracks']==[],'background music must remain optional')
    with tempfile.TemporaryDirectory() as td:
        root=Path(td); track=root/'music.mp3'; track.touch()
        path=root/'config.json'; path.write_text(json.dumps({'bgm_tracks':[{'path':'music.mp3','volume':0.18}]}),encoding='utf-8')
        loaded=config(path); rows=bgm_tracks(loaded,root)
        check(rows==[{'path':str(track.resolve()),'volume':0.18}],'per-track constant BGM volume must be preserved')
        path.write_text(json.dumps({'bgm_mix_mode':'ducking'}),encoding='utf-8')
        try: config(path)
        except ValueError: pass
        else: raise AssertionError('speech-triggered BGM ducking must be rejected')

def test_api_key_gate():
    with patch('lingzhi_task.find_cli',return_value=Path('/mock/lzstudio')), patch('lingzhi_task.api_key',return_value='secret'), patch('lingzhi_task._run_cli',return_value={'credits':0}) as run_cli:
        result=validate_api_key(); check(result=={'credits':0},'valid API key should pass the gate')
        args=run_cli.call_args.args; check(args[1]==['account','--credits','--api-key','secret'],'API key validation must use the read-only account credits request')
    with patch('lingzhi_task.find_cli',return_value=Path('/mock/lzstudio')), patch('lingzhi_task.api_key',return_value='secret'), patch('lingzhi_task._run_cli',side_effect=RuntimeError('Unauthorized')):
        try: require_valid_api_key()
        except RuntimeError as exc: check(str(exc)==API_KEY_GUIDANCE,'failed validation must show the acquisition guidance')
        else: raise AssertionError('invalid API key must stop skill execution')

def test_api_key_discovery():
    names=('LZSTUDIO_API_KEY','RECREATE_VIDEO_API_KEY','LINGZHI_API_KEY','LZSTUDIO_CONFIG')
    with tempfile.TemporaryDirectory() as td:
        root=Path(td); shared=root/'shared.json'; alternate=root/'alternate.json'; broken=root/'broken.json'
        shared.write_text(json.dumps({'apiKey':'config-secret'}),encoding='utf-8')
        alternate.write_text(json.dumps({'apiKey':'alternate-secret'}),encoding='utf-8')
        broken.write_text('{broken',encoding='utf-8')
        with patch.dict(os.environ,{name:'' for name in names},clear=False):
            key,source=resolve_api_key('   ',config_paths=[shared])
            check(key=='config-secret' and source.startswith('config:'),'blank explicit input must fall back to a known config')
            key,_=resolve_api_key(config_paths=[broken,alternate])
            check(key=='alternate-secret','a broken earlier config must not hide a later valid allowlisted config')
            try: resolve_api_key(config_paths=[broken])
            except CredentialConfigError: pass
            else: raise AssertionError('a malformed known config must be reported distinctly')
            try: resolve_api_key(config_paths=[root/'missing.json'])
            except CredentialNotFoundError: pass
            else: raise AssertionError('missing credentials must be reported distinctly')
        with patch.dict(os.environ,{'LZSTUDIO_API_KEY':'primary','RECREATE_VIDEO_API_KEY':'secondary','LINGZHI_API_KEY':'tertiary'},clear=False):
            key,source=resolve_api_key(config_paths=[shared])
            check(key=='primary' and source=='env:LZSTUDIO_API_KEY','environment credential priority changed unexpectedly')
    leaked='lzs-never-log-this'
    fake=SimpleNamespace(returncode=1,stderr=f'failed command --api-key {leaked}',stdout='')
    with patch('lingzhi_task.platform.system',return_value='Darwin'), patch('lingzhi_task.subprocess.run',return_value=fake):
        try: _run_cli(Path('/mock/lzstudio'),['account','--api-key',leaked,'--credits'])
        except RuntimeError as exc: check(leaked not in str(exc) and '[REDACTED]' in str(exc),'CLI errors must redact API keys')
        else: raise AssertionError('failed CLI call must raise')

def test_pronunciation_and_pause():
    cfg=config(); check(spoken_alias('这件T恤很合身',cfg)=='这件踢恤很合身','T恤 pronunciation alias must stay continuous')
    if not shutil.which('say') or not shutil.which('ffmpeg'): return
    segment={'segment_id':'segment_test','text':'这件T恤很合身','spoken_text':'这件T恤很合身','pause_after_ms':180,'visual_requirements':{},'evidence_shot_ids':[]}
    with tempfile.TemporaryDirectory() as td:
        try: voice,_=tts([segment],cfg,Path(td))
        except RuntimeError: return  # Speech service can be unavailable in a headless validation environment.
        total=duration(voice)
        result=run(['ffmpeg','-hide_banner','-i',voice,'-af','silencedetect=noise=-40dB:d=0.25','-f','null','-'],check=False)
        intervals=[]; starts=[float(x) for x in re.findall(r'silence_start:\s*([\d.]+)',result.stderr)]; ends=[float(x) for x in re.findall(r'silence_end:\s*([\d.]+)',result.stderr)]
        for i,start in enumerate(starts):
            end=ends[i] if i<len(ends) else total
            if start>.15 and end<total-.15: intervals.append((start,end))
        check(not intervals,f'lexical TTS contains internal silence longer than 250 ms: {intervals}')
        punctuated=dict(segment,text='裤腰一松，走路总想往上提。我把两边并起来，再轻轻扣好。',spoken_text='裤腰一松，走路总想往上提。我把两边并起来，再轻轻扣好。')
        punctuated_dir=Path(td)/'punctuated'; punctuated_dir.mkdir(); full,_=tts([punctuated],cfg,punctuated_dir); check(duration(full)>2.0,'tail-silence cleanup must not truncate speech at an internal comma')

def main():
    test_visual_matching(); test_caption_layout(); test_narration_inputs(); test_constant_bgm_config(); test_api_key_gate(); test_api_key_discovery(); test_pronunciation_and_pause(); print('self_test: passed')

if __name__=='__main__': main()
