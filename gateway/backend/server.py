"""Kolbo Video independent render gateway.

A local GPU/ComfyUI worker is required. This gateway is not itself a video model.
Run only behind HTTPS reverse proxy; never expose raw ComfyUI to the Internet.
"""
from __future__ import annotations
import base64, binascii, hmac, io, json, os, pathlib, secrets, subprocess, threading, time, uuid, ipaddress
from urllib.parse import urlsplit
import agnes_adapter
import device_pairing
from dataclasses import dataclass, field
from typing import Literal
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

BASE = pathlib.Path(__file__).resolve().parent
WORK_DIR = pathlib.Path(os.environ.get('KOLBO_WORK_DIR', str(BASE/'work')))
WORKFLOW_PATH = pathlib.Path(os.environ.get('KOLBO_WORKFLOW',str(BASE/'workflow_api.json')))
WORKFLOW_BY_IMAGE_COUNT = {
    i: pathlib.Path(os.environ.get(name,'')) if os.environ.get(name) else WORKFLOW_PATH
    for i,name in enumerate(('KOLBO_WORKFLOW_TEXT','KOLBO_WORKFLOW_ONE','KOLBO_WORKFLOW_TWO'))
}

COMFY = os.environ.get('KOLBO_COMFY_URL','http://127.0.0.1:8188').rstrip('/')
# Operator-selected provider. Agnes uses a third-party API, not independent GPU.
RENDER_PROVIDER = os.environ.get('KOLBO_RENDER_PROVIDER','comfy').lower()
AGNES_KEY = os.environ.get('AGNES_API_KEY','').strip()
PUBLIC_BASE = os.environ.get('KOLBO_PUBLIC_BASE_URL','').rstrip('/')
# Confirmation is NOT a technical price-lock: provider billing can change.
AGNES_PROMO_ACK = os.environ.get('KOLBO_AGNES_PROMO_ACK','') == 'CURRENT_ZERO_PRICE_CHECKED'
REFERENCE_TTL_SECONDS = 60 * 45
TOKEN = os.environ.get('KOLBO_API_TOKEN','')
TIMEOUT = int(os.environ.get('KOLBO_RENDER_TIMEOUT_SECONDS','1200'))
MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_VIDEO_BYTES = 300 * 1024 * 1024
MAX_PENDING = 20
# Results are private and temporary; file retention defaults to one day.
JOB_TTL_SECONDS = int(os.environ.get('KOLBO_JOB_TTL_SECONDS', '86400'))
# LTX-2.5 requires 1 + a multiple of 8 frames; ComfyUI workflows using
# other backbones can request exact frame counts in the server config.
FRAME_MODE = os.environ.get('KOLBO_FRAME_MODE','ltx_8n_plus_1')
app = FastAPI(title='Kolbo Video Gateway · independent GPU or Agnes Flash',version='0.3.0',docs_url=None,redoc_url=None)
app.include_router(device_pairing.router)
lock = threading.RLock()
worker_semaphore = threading.Semaphore(1)

@dataclass
class Job:
    id: str
    state: Literal['queued','running','completed','failed'] = 'queued'
    detail: str = 'ממתין לתור המחשב'
    output: pathlib.Path | None = None
    error: str | None = None
    created_at: float = field(default_factory=time.time)

jobs:dict[str,Job] = {}
@dataclass
class Reference:
    path: pathlib.Path
    mime: str
    owner_job_id: str
    expires: float
refs: dict[str,Reference] = {}

def agnes_api_key_state():
    """Non-sensitive startup diagnostic: never disclose, hash, or log the API key."""
    raw=os.environ.get('AGNES_API_KEY')
    if raw is None:return 'missing_variable'
    if not raw.strip():return 'empty_value'
    if len(raw.strip())<12:return 'too_short'
    return 'configured_not_authenticated'

def agnes_config_errors():
    issues=[]
    if not AGNES_KEY or len(AGNES_KEY)<12:issues.append('חסר מפתח Agnes API')
    if not AGNES_PROMO_ACK:issues.append('לא אושר שמחיר Agnes Flash בחשבון עדיין $0')
    try:
        parsed=urlsplit(PUBLIC_BASE)
        if parsed.scheme!='https' or not parsed.hostname or parsed.path not in ('','/') or parsed.query or parsed.fragment or parsed.username or parsed.password:
            raise ValueError('invalid URL')
        host=parsed.hostname.lower()
        if parsed.port not in (None,443) or host in ('localhost','127.0.0.1') or host.endswith(('.test','.local','.internal')):
            raise ValueError('not publicly reachable')
        try:
            ip=ipaddress.ip_address(host)
            if not ip.is_global:raise ValueError('not public')
        except ValueError:
            # If hostname is a literal invalid IP string, it will fail during the real HTTPS fetch.
            if host.replace('.','').isdigit():raise
    except (ValueError,TypeError):issues.append('נדרשת כתובת HTTPS ציבורית של שרת הווידאו')
    return issues

def stage_reference(jobid:str,index:int,data:bytes,mime:str)->tuple[str,str]:
    if agnes_config_errors():raise ValueError('שער Agnes אינו מוגדר כראוי')
    extension={'image/jpeg':'jpg','image/png':'png','image/webp':'webp'}[mime]
    token=secrets.token_urlsafe(32)
    folder=WORK_DIR/'refs'
    folder.mkdir(parents=True,exist_ok=True,mode=0o700)
    path=folder/(token+'.'+extension)
    with os.fdopen(os.open(str(path),os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'wb') as out:
        out.write(data)
    with lock:refs[token]=Reference(path,mime,jobid,time.monotonic()+REFERENCE_TTL_SECONDS)
    return token,PUBLIC_BASE+'/v1/media/'+token

def remove_job_references(job_id:str):
    with lock:
        gone=[(token,ref.path) for token,ref in refs.items() if ref.owner_job_id==job_id]
        for token,_ in gone:refs.pop(token,None)
    for _,path in gone:
        try:path.unlink(missing_ok=True)
        except OSError:pass

# Log ONLY discrete, non-secret readiness states after every Render redeployment.
print('KOLBO_AGNES_CONFIG: api_key_state='+agnes_api_key_state()
      +' price_confirmation='+('present' if AGNES_PROMO_ACK else 'missing')
      +' provider='+RENDER_PROVIDER,flush=True)

def _probe_agnes_without_generation_once():
    # GET /v1/models only. No video creation or provider credit usage.
    if RENDER_PROVIDER!='agnes' or agnes_api_key_state()!='configured_not_authenticated':
        return
    try:
        result=agnes_adapter.inspect_access_without_generation(AGNES_KEY)
        state=result.get('credential_state','unverified')
        if state not in ('accepted','rejected','missing','unverified'):
            state='unverified'
        print('KOLBO_AGNES_READ_ONLY_PROBE: credential_state='+state
              +' flash_model_visible='+str(bool(result.get('model_visible')))
              +' zero_price_verified=false',flush=True)
    except Exception:
        print('KOLBO_AGNES_READ_ONLY_PROBE: credential_state=unverified'
              +' flash_model_visible=false zero_price_verified=false',flush=True)

# Starts after import and logs an enumeration only; never keys, model lists,
# provider errors, URLs, account identifiers, or response content.
threading.Thread(target=_probe_agnes_without_generation_once,daemon=True).start()

@app.get('/healthz')
def infrastructure_health():
    # For Render port/health checking only. Does not imply that Agnes credentials,
    # zero-price status, provider quota or GPU execution are available.
    return {'service':'kolbo-video-gateway','alive':True,'render_ready':False}

@app.get('/v1/media/{token}')
def public_reference(token:str):
    # Publicly fetchable ONLY through unguessable, short-lived URLs.
    # The provider cannot provide the Android bearer token.
    if len(token)>150 or not all(c.isalnum() or c in '-_' for c in token):
        raise HTTPException(404,'תמונה לא זמינה')
    with lock:reference=refs.get(token)
    if not reference or time.monotonic()>=reference.expires or not reference.path.is_file():
        raise HTTPException(404,'תמונת הייחוס אינה זמינה עוד')
    return FileResponse(reference.path,media_type=reference.mime,
        headers={'Cache-Control':'no-store, max-age=0','X-Robots-Tag':'noindex, nofollow'})


class Picture(BaseModel):
    mime_type: Literal['image/jpeg','image/png','image/webp']
    data_base64: str = Field(min_length=128, max_length=14_000_000)

class JobSpec(BaseModel):
    prompt: str = Field(min_length=3,max_length=4000)
    seconds: int = Field(ge=1,le=60)
    images: list[Picture] = Field(default_factory=list,min_length=0,max_length=2)
    fps: int = Field(default=24,ge=8,le=60)

def require_auth(authorization:str | None):
    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(401,'לא התקבלה הרשאת מכשיר',headers={'WWW-Authenticate':'Bearer'})
    provided=authorization[7:]
    legacy=bool(TOKEN and len(TOKEN)>=24 and hmac.compare_digest(provided,TOKEN))
    device=not legacy and device_pairing.is_authorized_session(provided)
    if not (legacy or device):
        raise HTTPException(401,'ההרשאה פגה או שהמכשיר לא אושר',headers={'WWW-Authenticate':'Bearer'})

def frame_count(seconds:int,fps:int)->int:
    target=round(seconds*fps)
    if FRAME_MODE=='exact':return target
    if FRAME_MODE=='ltx_8n_plus_1':return max(9, 1 + 8*round((target-1)/8))
    raise ValueError('KOLBO_FRAME_MODE חייב להיות exact או ltx_8n_plus_1')


def template_available(image_count:int=0):
    try:
        if image_count not in range(3):return False
        wf=json.loads(WORKFLOW_BY_IMAGE_COUNT[image_count].read_text('utf-8'))
        if not isinstance(wf,dict) or not wf:return False
        nodes=list(wf.values())
        if not all(isinstance(n,dict) and isinstance(n.get('class_type'),str)
                   and n['class_type'].strip() and not n['class_type'].startswith('YOUR_')
                   and isinstance(n.get('inputs'),dict) for n in nodes):return False
        json_body=json.dumps(wf)
        required={'__KOLBO_PROMPT__','__KOLBO_FRAMES__'}
        required.update('__KOLBO_IMAGE'+str(i)+'__' for i in range(1,image_count+1))
        return all(k in json_body for k in required)
    except (OSError,ValueError):return False


def prune_expired_jobs():
    now=time.time()
    removed=0
    with lock:
        for key,job in list(jobs.items()):
            if job.state in ('completed','failed') and now-job.created_at>JOB_TTL_SECONDS:
                if job.output is not None:
                    try:job.output.unlink(missing_ok=True)
                    except OSError:pass
                jobs.pop(key,None)
                removed+=1
    with lock:
        expired=[(token,ref.path) for token,ref in refs.items() if time.monotonic()>=ref.expires]
        for token,_ in expired:refs.pop(token,None)
    for _,path in expired:
        try:path.unlink(missing_ok=True)
        except OSError:pass
    return removed

def comfy_request(method:str,path:str,data:bytes|None=None,ctype:str|None=None,timeout:int=25)->bytes:
    req=Request(COMFY+path,data=data,method=method,headers={
        'User-Agent':'KolboVideoGateway/0.1', **({'Content-Type':ctype} if ctype else {})})
    with urlopen(req,timeout=timeout) as res:
        data=res.read(MAX_VIDEO_BYTES+1 if path.startswith('/view') else 5_000_000)
        if len(data)>MAX_VIDEO_BYTES:raise RuntimeError('קובץ גדול מדי')
        return data

def gpu_available():
    try:
        payload=json.loads(comfy_request('GET','/system_stats',timeout=2))
        return bool(payload.get('system'))
    except Exception:return False

@app.get('/v1/agnes/access')
def agnes_access(authorization:str|None=Header(default=None)):
    """Explicit, read-only provider check; never creates a billable video job."""
    require_auth(authorization)
    if RENDER_PROVIDER!='agnes':
        return {'credential_state':'provider_not_selected','model_visible':False,
                'pricing_verified':False,'generation_permitted':False}
    result=agnes_adapter.inspect_access_without_generation(AGNES_KEY)
    result['local_zero_price_gate']=AGNES_PROMO_ACK
    # local approval is not provider price evidence; never label the two equivalent
    result['provider_account_price_verified']=False
    result['generation_permitted']=False
    return result

@app.get('/v1/health')
def health(authorization:str|None=Header(default=None)):
    require_auth(authorization)
    prune_expired_jobs()
    ffprobe_installed=bool(__import__('shutil').which('ffprobe'))
    if RENDER_PROVIDER=='agnes':
        issues=agnes_config_errors()
        if not ffprobe_installed:issues.append('FFprobe אינו מותקן')
        return {'status':'ready' if not issues else 'not_ready',
            'provider':'agnes-video-2.5-flash','supported_image_counts':[0,1,2],
            'min_seconds':4,'max_seconds':12,'requires_public_reference_urls':True,
            'unlimited_credits':False,'unlimited_compute':False,
            'price_promotion_verified_live':False,
            'agnes_api_key_state':agnes_api_key_state(),
            'agnes_api_key_verified_live':False,
            'operator_price_confirmation':AGNES_PROMO_ACK,
            'detail':'מוכן להגשת בקשה ניסיונית ל־Agnes. זמינות ומחיר בחשבון לא אומתו בפועל.'
                     if not issues else '; '.join(issues)}
    if RENDER_PROVIDER!='comfy':
        return {'status':'not_ready','provider':RENDER_PROVIDER,'detail':'ספק הפקה לא נתמך',
                'unlimited_credits':False,'unlimited_compute':False}
    available={str(n):template_available(n) for n in range(3)}
    duo_ready=available['2']
    connected=gpu_available()
    return {'supported_image_counts':[n for n in range(3) if available[str(n)]],
            'status':'ready' if duo_ready and connected and ffprobe_installed else 'not_ready',
            'provider':'comfy','workflow_configured':duo_ready,'comfyui_connected':connected,
            'ffprobe_available':ffprobe_installed,'duo_workflow_configured':duo_ready,
            'frame_mode':FRAME_MODE,'job_retention_seconds':JOB_TTL_SECONDS,
            'unlimited_credits':True,'unlimited_compute':False,
            'detail':'שרת GPU עצמאי מוכן' if duo_ready and connected and ffprobe_installed else
            'נדרש מחשב GPU עם ComfyUI ותבנית Workflow מתאימה'}

def validate_image(pic:Picture)->bytes:
    try:data=base64.b64decode(pic.data_base64,validate=True)
    except(binascii.Error,ValueError):raise ValueError('קידוד תמונה אינו תקין')
    if len(data)>MAX_IMAGE_BYTES:raise ValueError('תמונה גדולה מדי')
    valid=(pic.mime_type=='image/jpeg' and data[:3]==b'\xff\xd8\xff') or \
          (pic.mime_type=='image/png' and data[:8]==b'\x89PNG\r\n\x1a\n') or \
          (pic.mime_type=='image/webp' and data[:4]==b'RIFF' and data[8:12]==b'WEBP')
    if not valid: raise ValueError('תוכן התמונה אינו תואם לסוג הקובץ')
    return data

def upload_image(img:bytes,mime:str,jobid:str,index:int)->str:
    boundary='kolbo-'+secrets.token_hex(12)
    name=f'kolbo_{jobid}_{index}.'+({'image/jpeg':'jpg','image/png':'png','image/webp':'webp'}[mime])
    part=(f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="{name}"\r\n'
          f'Content-Type: {mime}\r\n\r\n').encode()+img+f'\r\n--{boundary}--\r\n'.encode()
    output=json.loads(comfy_request('POST','/upload/image',part,'multipart/form-data; boundary='+boundary))
    result=output.get('name','')
    if not isinstance(result,str) or not result or '/' in result or '..' in result:raise RuntimeError('שם תמונה לא חוקי')
    return result

def prepare_workflow(spec:JobSpec,reference_names:list[str])->dict:
    workflow=json.loads(WORKFLOW_BY_IMAGE_COUNT[len(reference_names)].read_text('utf-8'))
    if not isinstance(workflow,dict) or not workflow:raise ValueError('תבנית Workflow חסרה או ריקה')
    replacements={'__KOLBO_PROMPT__':spec.prompt,'__KOLBO_FRAMES__':frame_count(spec.seconds,spec.fps),
                  '__KOLBO_FPS__':spec.fps}
    for i,name in enumerate(reference_names,1):replacements[f'__KOLBO_IMAGE{i}__']=name
    found=set()
    def recurse(v):
        if isinstance(v,dict):return {k:recurse(value) for k,value in v.items()}
        if isinstance(v,list):return [recurse(t) for t in v]
        if isinstance(v,str) and v in replacements:
            found.add(v);return replacements[v]
        if isinstance(v,str) and v.startswith('__KOLBO_'):
            raise ValueError('ה־Workflow דורש קלט שאין לבקשה זו: '+v)
        return v
    patched=recurse(workflow)
    required={'__KOLBO_PROMPT__','__KOLBO_FRAMES__'}
    required.update(f'__KOLBO_IMAGE{i}__' for i in range(1,len(reference_names)+1))
    if not required.issubset(found):raise ValueError('תבנית המודל חסרה חיבור לשדות: '+', '.join(sorted(required-found)))
    return patched

def get_video(history:dict, prompt_id:str)->dict:
    outputs=history.get(prompt_id,{}).get('outputs',{})
    for node in outputs.values():
        for field in ('videos','gifs','files'):
            for item in node.get(field,[]):
                if isinstance(item,dict) and str(item.get('filename','')).lower().endswith('.mp4'):
                    return item
    raise ValueError('ה־Workflow הושלם בלי קובץ MP4. יש להגדיר צומת שמירת וידאו.')

def verify_video(output:pathlib.Path,seconds:int):
    p=subprocess.run(['ffprobe','-v','error','-show_entries','format=duration','-of','default=nw=1:nk=1',str(output)],
                     capture_output=True,text=True,timeout=30)
    if p.returncode:raise ValueError('קובץ וידאו פגום או FFprobe לא מותקן')
    actual=float(p.stdout.strip())
    if abs(actual-seconds)>0.5:raise ValueError(f'המנוע הפיק {actual:.2f} שניות במקום {seconds}; פלט קצר אינו מסומן כהצלחה')

def execute_agnes(job:Job,spec:JobSpec,images:list[bytes]):
    # Do not silently switch to paid Agnes 2.5 or to MSR if Flash fails.
    with worker_semaphore:
        try:
            with lock:job.state='running';job.detail='מכינים תמונות ייחוס זמניות'
            if not 4<=spec.seconds<=12:raise ValueError('Agnes Flash מאפשר 4–12 שניות')
            links=[]
            for i,(raw,picture) in enumerate(zip(images,spec.images),1):
                _,url=stage_reference(job.id,i,raw,picture.mime_type)
                links.append(url)
            video_id=agnes_adapter.submit(spec.prompt,spec.seconds,links,AGNES_KEY)
            with lock:job.detail='Agnes מעבד את הסרטון (ייתכן תור שרת עמוס)'
            def update(text):
                with lock:job.detail=text
            url=agnes_adapter.poll(video_id,AGNES_KEY,time.monotonic()+TIMEOUT,update)
            data=agnes_adapter.download_mp4(url)
            WORK_DIR.mkdir(parents=True,exist_ok=True)
            output=WORK_DIR/(job.id+'.mp4')
            output.write_bytes(data)
            verify_video(output,spec.seconds)
            with lock:job.output=output;job.state='completed';job.detail='הסרטון הוחזר לבדיקה'
        except Exception as e:
            candidate=WORK_DIR/(job.id+'.mp4')
            try:candidate.unlink(missing_ok=True)
            except OSError:pass
            with lock:job.state='failed';job.detail='ההפקה לא הושלמה';job.error=str(e)[:280]
        finally:
            remove_job_references(job.id)

def execute(job:Job,spec:JobSpec,images:list[bytes]):
    if RENDER_PROVIDER=='agnes':return execute_agnes(job,spec,images)
    with worker_semaphore:
        try:
            with lock:job.state='running';job.detail='מכינים מקורות ותוכנית הפקה'
            names=[upload_image(img,src.mime_type,job.id,i) for i,(img,src) in enumerate(zip(images,spec.images),1)]
            workflow=prepare_workflow(spec,names)
            payload=json.dumps({'prompt':workflow,'client_id':'kolbo-'+job.id}).encode('utf8')
            answer=json.loads(comfy_request('POST','/prompt',payload,'application/json'))
            prompt_id=answer.get('prompt_id','')
            if not isinstance(prompt_id,str) or not prompt_id:raise ValueError('ComfyUI דחה את תכנית ההפקה')
            deadline=time.monotonic()+TIMEOUT
            while time.monotonic()<deadline:
                with lock:job.detail='מנוע הווידאו מעבד את הסרטון'
                history=json.loads(comfy_request('GET','/history/'+prompt_id))
                if prompt_id in history:
                    error=history[prompt_id].get('status',{})
                    if error.get('status_str')=='error':raise RuntimeError('ComfyUI דיווח על כשל בהרצת מודל')
                    fileinfo=get_video(history,prompt_id)
                    filename=fileinfo.get('filename','')
                    query=urlencode({'filename':filename,'subfolder':fileinfo.get('subfolder',''),'type':fileinfo.get('type','output')})
                    data=comfy_request('GET','/view?'+query,timeout=120)
                    if len(data)>MAX_VIDEO_BYTES:raise ValueError('הסרטון חורג מגודל הקובץ המרבי')
                    if len(data)<10000 or data[4:8]!=b'ftyp':raise ValueError('ספק המודל לא החזיר MP4 תקין')
                    WORK_DIR.mkdir(parents=True,exist_ok=True)
                    file=WORK_DIR/(job.id+'.mp4');file.write_bytes(data)
                    verify_video(file,spec.seconds)
                    with lock:job.output=file;job.state='completed';job.detail='הסרטון מוכן לבדיקה'
                    return
                time.sleep(2)
            raise TimeoutError('תם הזמן להפקה במנוע הפרטי')
        except Exception as e:
            if job.output and job.output.exists():
                try:job.output.unlink()
                except OSError:pass
            with lock:job.state='failed';job.detail='ההפקה לא הושלמה';job.error=str(e)[:350]

@app.post('/v1/jobs',status_code=202)
def submit(spec:JobSpec,authorization:str|None=Header(default=None)):
    require_auth(authorization)
    prune_expired_jobs()
    if RENDER_PROVIDER=='agnes':
        issues=agnes_config_errors()
        if issues:raise HTTPException(503,'שער Agnes אינו מוכן: '+'; '.join(issues))
        if not 4<=spec.seconds<=12:
            raise HTTPException(422,'Agnes Flash מוגבל ל־4–12 שניות; לא ניתן להגיש אורך שגוי')
        if len(spec.images)>2:raise HTTPException(422,'נדרשות לכל היותר שתי תמונות')
        if not __import__('shutil').which('ffprobe'):raise HTTPException(503,'חסר FFprobe')
    elif RENDER_PROVIDER=='comfy':
        if not template_available(len(spec.images)) or not gpu_available():
            raise HTTPException(503,'מנוע ComfyUI או תבנית ההפקה למספר התמונות המבוקש אינם זמינים')
    else:raise HTTPException(503,'ספק הפקה לא נתמך')
    images=[]
    try:
        for photo in spec.images:images.append(validate_image(photo))
        if RENDER_PROVIDER=='comfy':
            # Only a local ComfyUI GPU requires placeholder-based workflows.
            prepare_workflow(spec,[f'image{i}.png' for i in range(1,len(images)+1)])
    except ValueError as e:raise HTTPException(422,str(e))
    with lock:
        active=sum(1 for j in jobs.values() if j.state in ('running','queued'))
        if active>=MAX_PENDING:raise HTTPException(503,'תור מחשוב מלא. נסה מאוחר יותר',headers={'Retry-After':'120'})
        job=Job(id=str(uuid.uuid4()))
        jobs[job.id]=job
    threading.Thread(target=execute,args=(job,spec,images),daemon=True).start()
    return {'job_id':job.id,'state':job.state}

def lookup(job_id:str)->Job:
    prune_expired_jobs()
    try:uuid.UUID(job_id)
    except ValueError:raise HTTPException(404,'עבודה אינה קיימת')
    with lock:
        job=jobs.get(job_id)
    if not job:raise HTTPException(404,'עבודה אינה קיימת')
    return job

@app.get('/v1/jobs/{job_id}')
def status(job_id:str,authorization:str|None=Header(default=None)):
    require_auth(authorization)
    job=lookup(job_id)
    return {'job_id':job.id,'state':job.state,'detail':job.detail,'error':job.error}

@app.get('/v1/jobs/{job_id}/result')
def result(job_id:str,authorization:str|None=Header(default=None)):
    require_auth(authorization)
    job=lookup(job_id)
    if job.state!='completed' or not job.output or not job.output.is_file():
        raise HTTPException(409,'הסרטון עדיין לא מוכן')
    return FileResponse(job.output,media_type='video/mp4',filename=f'kolbo-{job.id}.mp4')
