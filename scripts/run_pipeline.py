#!/usr/bin/env python3
"""Two-input narration pipeline with one server-side edit-planning call."""
import argparse, subprocess, sys, time
from datetime import datetime
from pathlib import Path
from utils import config, dump_json, fingerprint, load_json, video_count

ROOT=Path(__file__).resolve().parents[1]; S=ROOT/'scripts'; WORK=ROOT/'work'
STAGES=['check_cache','prepare','analyze_and_build_library','narration','remote_edit_strategy','apply_strategy','validate','extract_selected_shots','render_variants','quality','package']

def call(name,*args): subprocess.check_call([sys.executable,S/name,*map(str,args)])

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--config',default='input/config.json')
    ap.add_argument('--library-response')
    ap.add_argument('--narration-response',default='work/narration_response.json')
    a=ap.parse_args()
    config_path=Path(a.config); config_path=config_path if config_path.is_absolute() else ROOT/config_path
    cfg=config(config_path); WORK.mkdir(parents=True,exist_ok=True); timings=[]

    script_path=ROOT/'input/voiceover_script.txt'; script_text=script_path.read_text(encoding='utf-8').strip() if script_path.exists() else ''
    voice=Path(cfg['voiceover_path']); voice=voice if voice.is_absolute() else ROOT/voice
    if cfg['narrationMode']=='audio':
        if not voice.is_file(): raise SystemExit('audio narrationMode requires a supplied voiceover audio file')
        if script_text: raise SystemExit('choose exactly one narration input: remove input/voiceover_script.txt when using audio mode')
    else:
        if not script_text: raise SystemExit('script narrationMode requires input/voiceover_script.txt')
        if voice.is_file(): raise SystemExit('choose exactly one narration input: remove the supplied voiceover audio when using script mode')

    def stage(name,fn):
        start=time.monotonic(); fn(); timings.append({'stage':name,'seconds':round(time.monotonic()-start,3)})

    stage('check_cache',lambda:call('check_cache.py','--config',config_path,'--input-dir',ROOT/'input','--videos-dir',ROOT/'input/videos','--work-dir',WORK))
    cache=load_json(WORK/'cache_state.json',{}); hit=bool(cache.get('all_hit'))
    if not hit:
        if not a.library_response: raise SystemExit('--library-response is required when one or more source videos are not cached')
        stage('prepare',lambda:call('prepare_materials.py','--config',config_path,'--input-dir',ROOT/'input','--videos-dir',ROOT/'input/videos','--work-dir',WORK))
        stage('analyze_and_build_library',lambda:call('analyze_and_build_library.py','--config',config_path,'--metadata',WORK/'metadata/videos.json','--frames',WORK/'frames/frame_manifest.json','--cache-state',WORK/'cache_state.json','--response-file',a.library_response,'--work-dir',WORK))
    else:
        timings += [{'stage':'prepare','seconds':0,'cached':True},{'stage':'analyze_and_build_library','seconds':0,'cached':True}]

    library=load_json(WORK/'shot_library.json',{}); eligible=sum(1 for x in library.get('shots',[]) if x.get('eligible_for_edit')); effective_count=video_count(cfg,eligible)
    dump_json(WORK/'generation_context.json',{
        'narrationMode':cfg['narrationMode'],'voiceStyle':cfg['voiceStyle'],
        'tts_voice':None if cfg['narrationMode']=='audio' else str(cfg.get('tts_voice') or cfg.get('default_tts_voice')),
        'requested_videoCount':cfg['videoCount'],'effectiveVideoCount':effective_count,
        'eligible_shot_count':eligible,'strategyContractVersion':1
    })

    narration_response=Path(a.narration_response); narration_response=narration_response if narration_response.is_absolute() else ROOT/narration_response
    narration_inputs=[script_path,config_path]+([narration_response] if narration_response.exists() else [])+([voice] if voice.exists() else [])
    narration_key=fingerprint(narration_inputs,{'stage':'v5-two-input-narration','mode':cfg['narrationMode']})
    narration_stamp=load_json(WORK/'narration_cache.json',{})
    if narration_stamp.get('fingerprint')==narration_key and (WORK/'narration_manifest.json').is_file():
        timings.append({'stage':'narration','seconds':0,'cached':True})
    else:
        if not narration_response.is_file(): raise SystemExit(f'GPT narration response is required at {narration_response}; create it from references/narration-ugc-prompt.md')
        stage('narration',lambda:call('prepare_narration.py','--config',config_path,'--script',script_path,'--response-file',narration_response,'--library',WORK/'shot_library.json','--output-dir',WORK/'narration','--output',WORK/'narration_manifest.json'))
        dump_json(WORK/'narration_cache.json',{'fingerprint':narration_key})

    # Intentionally do not cache the server decision. This lets old Skill clients
    # pick up compatible strategy-engine upgrades without shipping a new client.
    stage('remote_edit_strategy',lambda:call('remote_edit_strategy.py','--config',config_path,'--library',WORK/'shot_library.json','--narration',WORK/'narration_manifest.json','--generation-context',WORK/'generation_context.json','--output',WORK/'strategy_response.json'))
    stage('apply_strategy',lambda:call('apply_remote_strategy.py','--response-file',WORK/'strategy_response.json','--config',config_path,'--library',WORK/'shot_library.json','--narration',WORK/'narration_manifest.json','--output-dir',WORK/'variants'))
    stage('validate',lambda:call('validate_edit_plan.py','--variants-dir',WORK/'variants','--library',WORK/'shot_library.json','--config',config_path,'--narration',WORK/'narration_manifest.json','--output',WORK/'validation_report.json','--subtitles-dir',WORK/'subtitles'))
    stage('extract_selected_shots',lambda:call('extract_selected_shots.py','--variants-dir',WORK/'variants','--library',WORK/'shot_library.json','--config',config_path,'--output',WORK/'selected_shot_library.json'))

    batch=ROOT/'output'/('real_shot_batch_'+datetime.now().strftime('%Y%m%d_%H%M%S')); videos=batch/'videos'; videos.mkdir(parents=True,exist_ok=True)
    stage('render_variants',lambda:call('render_variants.py','--variants-dir',WORK/'variants','--library',WORK/'selected_shot_library.json','--config',config_path,'--narration',WORK/'narration_manifest.json','--subtitles-dir',WORK/'subtitles','--output-dir',videos,'--report',WORK/'render_report.json'))
    stage('quality',lambda:call('quality_gate.py','--videos-dir',videos,'--variants-dir',WORK/'variants','--library',WORK/'shot_library.json','--narration',WORK/'narration_manifest.json','--config',config_path,'--output',WORK/'quality_report.json','--qa-dir',batch/'qa_frames'))
    stage('package',lambda:None)
    dump_json(WORK/'timings.json',{'mode':'advertisement_generation' if hit else 'asset_build_and_generation','cache_hit':hit,'strategy_workflow_id':cfg['strategy_workflow_id'],'batch_dir':str(batch.resolve()),'stages':timings})
    print(batch)

if __name__=='__main__': main()
