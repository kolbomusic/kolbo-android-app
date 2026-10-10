"""One bounded synthetic proof from a discovered Gradio adapter.

Does not take user media or credentials. Results become *technical* evidence only.
Every HTTP target is a vetted public *.hf.space HTTPS host, and redirects are off.
"""
from __future__ import annotations
import hashlib
import json
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.parse import quote,urlparse
import requests
from PIL import Image,ImageDraw
from .adapter import plan_from_public
from .scout import safe_space_host, ALLOWED_LICENSES

MAX_BYTES=30*1024*1024

class ProbeError(Exception):pass


def generate_synthetic(path: Path):
    img=Image.new('RGB',(384,384),(152,197,225))
    d=ImageDraw.Draw(img)
    d.rectangle((0,248,384,384),fill=(57,137,60))
    d.ellipse((158,182,225,249),fill=(250,122,25))
    img.save(path,'PNG')


def _response(session, method, url, **kwargs):
    # Caller must pass URL derived solely from the vetted HF Spaces subdomain.
    kwargs.setdefault('timeout',(8,40))
    kwargs['allow_redirects']=False
    res=session.request(method,url,**kwargs)
    if res.is_redirect:raise ProbeError('REMOTE_REDIRECT_REJECTED')
    res.raise_for_status()
    return res


def _output_pointer(obj):
    if isinstance(obj,dict):
        for k in ('video','url','path','name'):
            if isinstance(obj.get(k),str) and ('.mp4' in obj[k].lower() or k=='video'):return obj[k]
        for k in ('data','value','files','output'):
            if k in obj:
                v=_output_pointer(obj[k])
                if v:return v
        for v in obj.values():
            if isinstance(v,(dict,list)):
                x=_output_pointer(v)
                if x:return x
    if isinstance(obj,list):
        for v in obj:
            x=_output_pointer(v)
            if x:return x
    if isinstance(obj,str) and obj.endswith('.mp4'):return obj
    return None


def _video_url(pointer,base):
    if not isinstance(pointer,str) or len(pointer)>1500:raise ProbeError('MEDIA_POINTER_INVALID')
    # Model output may point at its own Space's file endpoint; reject external domains.
    u=urlparse(pointer)
    if u.scheme:
        if not pointer.startswith(base+'/'):raise ProbeError('UNTRUSTED_MEDIA_URL')
        return pointer
    if pointer.startswith('/gradio_api/file=') or pointer.startswith('/file='):
        return base+pointer
    # Gradio returns file paths from the Space's own temp directory.
    if pointer.startswith('/') and not pointer.startswith('//'):
        return base+'/gradio_api/file='+quote(pointer,safe='')
    raise ProbeError('MEDIA_POINTER_NOT_SUPPORTED')


def _ffprobe(path,requested_duration:int):
    cmd=['ffprobe','-v','error','-show_entries','format=duration:stream=codec_type,codec_name',
         '-of','json',str(path)]
    try: f=json.loads(subprocess.check_output(cmd,timeout=15))
    except (OSError,subprocess.CalledProcessError,subprocess.TimeoutExpired,ValueError) as exc:
        raise ProbeError('INVALID_VIDEO_CONTENT') from exc
    sec=float(f.get('format',{}).get('duration',0))
    if not (requested_duration-0.4 <= sec <= requested_duration+0.4):raise ProbeError('WRONG_VIDEO_DURATION')
    streams=f.get('streams',[])
    if not any(s.get('codec_type')=='video' for s in streams):raise ProbeError('NO_VIDEO_STREAM')
    return {'seconds':round(sec,3),'has_video':True,
            'has_audio_stream':any(s.get('codec_type')=='audio' for s in streams)}


def _read_sse(session,url,deadline):
    r=_response(session,'GET',url,stream=True,headers={'Accept':'text/event-stream'},timeout=(8,60))
    event='';pieces=[]
    try:
        for row in r.iter_lines(decode_unicode=True):
            if time.monotonic()>deadline:raise ProbeError('PROBE_TIMEOUT')
            if not row: # completion separated by empty line
                if event=='error':raise ProbeError('PROVIDER_ERROR')
                if event=='complete':
                    joined='\n'.join(pieces)
                    if len(joined)>200_000:raise ProbeError('RESULT_TOO_LARGE')
                    return json.loads(joined)
                event='';pieces=[];continue
            if isinstance(row,bytes):row=row.decode('utf8','replace')
            if row.startswith('event:'):event=row[6:].strip()
            elif row.startswith('data:'):pieces.append(row[5:].strip())
    finally:r.close()
    raise ProbeError('PROVIDER_NO_COMPLETION')


def probe_one(candidate:dict,output_dir:Path, seconds=8, session=None) -> dict:
    """Probe ONLY when plan & public terms meet strict guardrails.

    Every probe uses a local generated cartoon fixture. Execution may fail due to
    provider restrictions and does not certify semantic match or permanent capacity.
    """
    if candidate.get('status')!='schema_matched':raise ProbeError('PROVIDER_NOT_INTROSPECTED')
    if not candidate.get('automated_public_demo_probe_candidate'):raise ProbeError('UNVERIFIED_LICENSE')
    if candidate.get('license_declared') not in ALLOWED_LICENSES:raise ProbeError('UNVERIFIED_LICENSE')
    # Caller should also check provider's automation terms. For safety this demo
    # requires explicit individual allowlist before executing any discovered Space.
    approved={x.strip() for x in os.environ.get('KOLBO_SYNTHETIC_PROBE_ALLOWLIST','').split(',') if x.strip()}
    if candidate.get('id') not in approved:raise ProbeError('NOT_APPROVED_FOR_AUTOMATED_PROBE')
    host=candidate.get('api_host')
    if not isinstance(host,str) or not re.fullmatch(r'https://[a-z0-9-]{1,127}\.hf\.space',host):raise ProbeError('UNTRUSTED_HOST')
    safe_space_host(host.split('//')[1].removesuffix('.hf.space'))
    plans=candidate.get('capabilities') or []
    if not plans:raise ProbeError('NO_COMPATIBLE_API')
    plan=plan_from_public(plans[0])
    output_dir=Path(output_dir)
    output_dir.mkdir(parents=True,exist_ok=True)
    fixture=output_dir/'synthetic-orange-ball.png'
    result_file=output_dir/'synthetic-provider-result.mp4'
    generate_synthetic(fixture)
    sess=session or requests.Session()
    started=time.monotonic()
    try:
        with fixture.open('rb') as stream:
            up=_response(sess,'POST',host+'/gradio_api/upload',files={'files':('synthetic-orange-ball.png',stream,'image/png')})
        uploaded=up.json()
        if not isinstance(uploaded,list) or not uploaded or not isinstance(uploaded[0],str):raise ProbeError('INVALID_UPLOAD_RESULT')
        u=uploaded[0]
        if len(u)>1200 or not u.startswith('/') or '..' in u:raise ProbeError('UNEXPECTED_UPLOAD_PATH')
        descriptor={'path':u,'orig_name':fixture.name,'mime_type':'image/png','meta':{'_type':'gradio.FileData'}}
        args=plan.arguments('One orange ball makes exactly two bounces on a static meadow; '
            'fixed camera, no text, no captions, no fade to black.',seconds,descriptor)
        name=plan.api_name.removeprefix('/')
        if not re.fullmatch('[a-zA-Z0-9_-]{1,80}',name):raise ProbeError('BAD_API_NAME')
        kickoff=_response(sess,'POST',host+'/gradio_api/call/'+name,json={'data':args})
        job=kickoff.json().get('event_id')
        if not isinstance(job,str) or not re.fullmatch(r'[a-zA-Z0-9_-]{8,180}',job):raise ProbeError('BAD_REMOTE_JOB')
        output=_read_sse(sess,host+'/gradio_api/call/'+name+'/'+job,time.monotonic()+180)
        pointer=_output_pointer(output)
        if not pointer:raise ProbeError('PROVIDER_COMPLETED_WITHOUT_VIDEO')
        path=_video_url(pointer,host)
        with _response(sess,'GET',path,stream=True,timeout=(8,60)) as media:
            n=0
            with result_file.open('wb') as dest:
                for chunk in media.iter_content(65536):
                    if time.monotonic()-started>210:raise ProbeError('PROBE_WALL_TIME_EXCEEDED')
                    n+=len(chunk)
                    if n>MAX_BYTES:raise ProbeError('PROVIDER_VIDEO_TOO_LARGE')
                    dest.write(chunk)
        if n<1024:raise ProbeError('EMPTY_VIDEO')
        report=_ffprobe(result_file,seconds)
        report.update({'status':'verified_synthetic_video_only','provider_id':candidate['id'],
                       'api_name':plan.api_name,'result_sha256':hashlib.sha256(result_file.read_bytes()).hexdigest(),
                       'semantic_prompt_adherence':'not_verified','audible_audio':'not_verified',
                       'cost_and_future_availability':'not_guaranteed'})
        return report
    except Exception:
        result_file.unlink(missing_ok=True)
        raise
    finally:
        if session is None:sess.close()