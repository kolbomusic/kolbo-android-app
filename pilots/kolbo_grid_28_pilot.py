#!/usr/bin/env python3
"""Kolbo Grid pilot: one image -> 8s visuals -> ball-specific sound -> independent quality check.

Fixture mode is offline and proves orchestration, not AI rendering. Live mode sends
ONLY a synthetic generated image to public Hugging Face Gradio, with explicit opt-in;
no user uploads, access keys or personal media. No infinite retries or automatic fees.
"""
from __future__ import annotations
import argparse, hashlib, json, math, os, subprocess, sys, time
from pathlib import Path
import shutil


def generate_synthetic_ball_video(target:Path, seconds:int=8, *, fps:int=24)->dict:
    """Deterministic visual fixture containing an orange bouncing ball, no sound."""
    import cv2
    import numpy as np
    if seconds not in (3,6,8):raise ValueError('UNSUPPORTED_DURATION')
    target.parent.mkdir(parents=True,exist_ok=True)
    temp=target.with_suffix('.avi')
    w,h=512,288
    writer=cv2.VideoWriter(str(temp),cv2.VideoWriter_fourcc(*'MJPG'),fps,(w,h))
    if not writer.isOpened():raise RuntimeError('FIXTURE_ENCODER_FAILED')
    try:
        for i in range(seconds*fps):
            t=i/fps
            frame=np.zeros((h,w,3),dtype=np.uint8)
            frame[:215]=(219,173,119)  # BGR sky
            frame[215:]=(76,145,76)  # BGR green meadow
            # Multiple visually measurable contacts, with a short rebound after each.
            y=int(round(186-72*abs(math.sin(math.pi*(t-1.2)/2.15))))
            x=int(round(73+(355 * i/(seconds*fps-1))))
            cv2.circle(frame,(x,y),36,(35,111,236),-1,lineType=cv2.LINE_AA)
            writer.write(frame)
    finally:writer.release()
    subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-nostdin','-y','-i',str(temp),
                    '-an','-c:v','libx264','-preset','veryfast','-crf','21','-pix_fmt','yuv420p','-movflags','+faststart',str(target)],
                   check=True,timeout=80,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
    temp.unlink(missing_ok=True)
    return {'fixture':'synthetic_bouncing_ball','frames':seconds*fps,'ai_generated':False}


def generate_reference_image(path:Path):
    from PIL import Image, ImageDraw
    image=Image.new('RGB',(512,512),(144,189,219))
    d=ImageDraw.Draw(image)
    d.rectangle((0,385,512,512),fill=(98,154,88))
    d.ellipse((135,318,235,418),fill=(235,115,35))
    image.save(path,format='PNG')


def run(out:Path, mode:str='fixture',duration:int=8,allow_external:bool=False,source_video:Path|None=None):
    from kolbo_cloud.foley import render_ball_foley
    from kolbo_cloud.qa import quality_check
    out.mkdir(parents=True,exist_ok=True)
    report={'name':'Kolbo Grid 2.8 private pilot','pipeline':'visuals -> motion Foley -> QA',
            'mode':mode,'requested_seconds':duration,'third_party_media_uploaded':False,
            'ai_visual_generation_verified':False,'native_ai_audio_verified':False,
            'semantic_prompt_fidelity_verified':False,'subtitle_absence_verified':False,
            'service_is_public':False,'output_verified':False,'status':'started',
            'assumptions':['Only orange-ball-meadow scenes are sound-supported in this pilot',
                           'This is not unlimited cloud GPU or a production backend']}
    p=out/'report.json'
    def write():p.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    try:
        if duration not in (3,6,8):raise ValueError('UNSUPPORTED_DURATION')
        if mode not in ('fixture','live','existing'):raise ValueError('UNSUPPORTED_MODE')
        visual=out/'visual.mp4';final=out/'kolbo-pilot.mp4'
        if mode=='fixture':
            report['visual_source']=generate_synthetic_ball_video(visual,duration)
        elif mode=='existing':
            if source_video is None or not source_video.is_file():raise ValueError('SOURCE_VIDEO_REQUIRED')
            if source_video.stat().st_size>120*1024*1024:raise ValueError('SOURCE_VIDEO_TOO_LARGE')
            if source_video.resolve()==visual.resolve():raise ValueError('SOURCE_DESTINATION_COLLISION')
            shutil.copyfile(source_video,visual)
            report['visual_source']={'type':'existing_visual_clip','ai_render_verified_in_this_run':False}
        else:
            if not allow_external:raise ValueError('PUBLIC_HF_UPLOAD_OPT_IN_REQUIRED')
            # Opt-in uploads *only* an impersonal synthetic image, NOT media supplied by users.
            from kolbo_cloud.provider import render_video
            image=out/'synthetic.png';generate_reference_image(image)
            report['third_party_media_uploaded']=True
            report['visual_source']=render_video(image,
                'A bright orange ball rolls left to right over a meadow and bounces twice. '
                'Grass rustles, quiet natural wind. Do not include text, titles, captions, '
                'subtitles, trademarks, logos or watermarks.', duration,visual)
            report['ai_visual_generation_verified']=True
        from pilots.ball_action_gate import detect_bounces
        visual_actions=detect_bounces(visual,expected_minimum=2)
        report['visual_action_check']=visual_actions
        if not visual_actions.get('pass'):
            raise ValueError('BOUNCE_ACTION_NOT_VERIFIED')
        report['status']='foley_processing';write()
        details=render_ball_foley(visual,final,duration,'orange_ball_meadow',out)
        # A second, independent QA that checks sound strength, motion and exact duration.
        qa=quality_check(final,duration,require_motion=True)
        report['qa']=qa
        report['foley_events']=details['event_count']
        report['visual_sha256']=hashlib.sha256(visual.read_bytes()).hexdigest()
        report['output_sha256']=hashlib.sha256(final.read_bytes()).hexdigest()
        report['output_verified']=bool(qa['status']=='PASS')
        report['status']='PASS' if report['output_verified'] else 'QA_FAILED'
        report['native_ai_audio_verified']=False
        report['warning']='Ball-scene procedural Foley; not native AI audio, not semantic proof'
    except Exception as e:
        from kolbo_cloud.foley import RenderError
        from kolbo_cloud.provider import ProviderError
        if isinstance(e,ProviderError):code=e.code
        elif isinstance(e,RenderError):code=e.code
        elif isinstance(e,ValueError):code=str(e)[:90]
        else:code='PROCESSING_FAILED_'+type(e).__name__.upper()
        report['status']='BLOCKED';report['reason_code']=code
    finally:write()
    return report


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--mode',choices=['fixture','live','existing'],default='fixture')
    ap.add_argument('--duration',choices=[3,6,8],type=int,default=8)
    ap.add_argument('--out',type=Path,default=Path('pilot-output'))
    ap.add_argument('--source-video',type=Path)
    ap.add_argument('--allow-external-synthetic-upload',action='store_true',default=False)
    args=ap.parse_args()
    result=run(args.out,args.mode,args.duration,args.allow_external_synthetic_upload,args.source_video)
    print(json.dumps({k:v for k,v in result.items() if k not in ('qa','visual_source')},indent=2,ensure_ascii=False),flush=True)
    sys.exit(0 if result['status']=='PASS' else 2)

if __name__=='__main__':main()