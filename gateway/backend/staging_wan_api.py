"""Kolbo Video v4.1.6 isolated staging API for the ONE-image public Wan demo.

Speaks the existing Android PrivateRenderClient protocol. No production
deployment, no database, no durable storage, no commercial right/voice/duo
claim. Strict opt-in and no automatic retries of uncertain vendor jobs.
"""
from __future__ import annotations
import base64, binascii, hashlib, hmac, io, json, os, secrets, shutil, threading, time, uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from PIL import Image, UnidentifiedImageError

import experimental_zerogpu_adapter as provider
import visual_quality
import audio_evidence
import creative_intent_guard as intents
import cpu_photo_studio as studio
import procedural_sfx
import guest_sessions as guests
import compute_supervisor as compute
import ai_trial_guards as ai_trials
import longform_av

APP_TITLE = "Kolbo Video Experimental Wan Gateway (NOT production)"
app = FastAPI(title=APP_TITLE, docs_url=None, redoc_url=None, openapi_url=None)
ROOT = Path(os.getenv("KOLBO_V416_WORK_DIR", "/tmp/kolbo-v416-worker"))
MAX_IMAGE = 5_000_000
TTL = 3600
LIMIT = 1
LOCK = threading.RLock()
POOL = ThreadPoolExecutor(max_workers=LIMIT, thread_name_prefix="kolbo-v416")
JOBS: dict[str, dict] = {}
DIGESTS: dict[str, str] = {}

class Picture(BaseModel):
    mime_type: str
    data_base64: str = Field(min_length=32, max_length=7_000_000)

class NewJob(BaseModel):
    prompt: str = Field(min_length=5, max_length=3000)
    seconds: float = Field(ge=1, le=360)
    fps: int = Field(default=24, ge=1, le=60)
    images: list[Picture] = Field(min_length=0, max_length=2)
    third_party_transfer_consent: bool = False
    requires_audio: bool = False
    requires_lipsync: bool = False
    requires_two_independent_people: bool = False
    commercial_use: bool = False

class PhotoStudioJob(BaseModel):
    mode: str = "cpu_photo_motion"
    seconds: int = Field(ge=2,le=12)
    images: list[Picture] = Field(min_length=1,max_length=2)
    soundtrack_wav_base64: str | None = Field(default=None,max_length=9_500_000)
    media_rights_attested: bool = False
    sound_effect_description: str = Field(default="",max_length=3000)
    include_procedural_effect: bool = False

class LongformPreview(BaseModel):
    seconds: int = Field(ge=1,le=15)
    image_count: int = Field(ge=0,le=2)
    audio_source: str = Field(default="none",max_length=40)
    voice_requested: bool = False
    singing_requested: bool = False
    lipsync_requested: bool = False
    two_independent_people: bool = False
    third_party_transfer_consent: bool = False

class GuestBootstrapRequest(BaseModel):
    install_id: str = Field(min_length=32,max_length=32)

class CreativePreflight(BaseModel):
    prompt: str = Field(min_length=5, max_length=3000)
    seconds: float = Field(ge=1, le=360)
    image_count: int = Field(ge=0, le=2)
    third_party_transfer_consent: bool = False
    requires_audio: bool = False
    requires_lipsync: bool = False
    requires_two_independent_people: bool = False
    commercial_use: bool = False

def require_token(authorization: str | None) -> None:
    secret=os.getenv("KOLBO_V416_API_TOKEN","")
    if len(secret)<32 or not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "נדרש חיבור מאובטח", headers={"WWW-Authenticate":"Bearer"})
    if not hmac.compare_digest(authorization[7:].encode(),secret.encode()):
        raise HTTPException(401, "הרשאה לא תקינה", headers={"WWW-Authenticate":"Bearer"})

def studio_owner(authorization: str | None) -> str:
    if authorization is not None and authorization.startswith("Bearer g1."):
        return "guest:"+guests.verify(authorization).owner
    require_token(authorization)
    return "master"


def enabled() -> bool:
    import importlib.util
    return (len(os.getenv("KOLBO_V416_API_TOKEN",""))>=32
       and os.getenv("KOLBO_ALLOW_EXTERNAL_TEST_MEDIA")=="EXPLICITLY_ENABLED"
       and shutil.which("ffprobe") is not None
       and shutil.which("ffmpeg") is not None
       and importlib.util.find_spec("gradio_client") is not None)

def expire_old() -> None:
    now=time.time()
    with LOCK:
        for key, job in list(JOBS.items()):
            if job["state"] in ("queued","running"):
                continue
            if now - job["created_at"] < TTL:
                continue
            JOBS.pop(key,None)
            DIGESTS.pop(job["digest"],None)
            folder=ROOT/key
            if folder.is_dir():
                shutil.rmtree(folder,ignore_errors=True)

def decode_picture(pic: Picture) -> tuple[bytes,str]:
    mime={"image/png":"png","image/jpeg":"jpg","image/webp":"webp"}.get(pic.mime_type)
    if not mime:
        raise HTTPException(422, "סוג תמונה אינו נתמך")
    try:
        data=base64.b64decode(pic.data_base64,validate=True)
    except (ValueError,binascii.Error):
        raise HTTPException(422,"תמונה אינה מקודדת בצורה תקינה")
    if not 100<=len(data)<=MAX_IMAGE:
        raise HTTPException(422, "גודל התמונה אינו תקין")
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.format not in ("PNG","JPEG","WEBP") or image.width*image.height>15_000_000:
                raise HTTPException(422,"סוג התמונה או מימדיה אינם נתמכים")
            image.verify()
    except (UnidentifiedImageError,OSError,ValueError,Image.DecompressionBombError):
        raise HTTPException(422,"תוכן התמונה אינו קובץ תמונה תקין")
    return data,mime

def _work(job_id: str, *, image: Path, prompt: str, seconds: float) -> None:
    with LOCK:
        if job_id not in JOBS:return
        JOBS[job_id]["state"]="running"
    folder=ROOT/job_id
    try:
        dst=folder/"draft.mp4"
        receipt=provider.submit_one(reference=image,prompt=prompt,seconds=seconds,
            destination=dst,consent=True,commercial=False,wants_audio=False,wants_lipsync=False)
        # Output validated by provider.ffprobe then again by decoded-frame QA.
        visual=visual_quality.inspect_mp4(dst,audio_required=False)
        sound=audio_evidence.inspect_mp4(dst,audio_required=False)
        # A valid MP4 with nearly identical frames is NOT successful AI.
        if visual.pixel_change_fraction < 0.012:
            raise ValueError("Output is visually frozen: no measurable motion")
        with LOCK:
            JOBS[job_id].update(state="completed",detail="התקבלה טיוטת וידאו לא מאומתת",
                size=receipt.bytes,sha256=receipt.sha256,has_audio=receipt.audio,
                quality={'visual':visual.as_dict(),'audio':sound.as_dict(),
                         'requires_semantic_review':True,
                         'motion_measured':True,'voice_verified':False})
    except Exception as exc:
        # No automatic resend: provider might have accepted and spent quota.
        kind="acceptance_unknown" if isinstance(exc,provider.UnknownAcceptance) else "generation_failed"
        with LOCK:
            if job_id in JOBS:
                JOBS[job_id].update(state="failed",error=kind,
                    detail="ההפקה לא אומתה; אין ניסיון חוזר אוטומטי")
    finally:
        try:image.unlink(missing_ok=True)
        except OSError:pass
        # Do not persist the prompt or original image in job metadata.

@app.get("/healthz")
def healthz():
    return {"alive":True,"experimental":True}

@app.get("/v1/health")
def health(authorization: str | None = Header(default=None)):
    owner=studio_owner(authorization)
    expire_old()
    return {"status":"ready" if enabled() and owner=="master" else "not_ready",
            "provider":"zerogpu-wan2.2-experimental",
            "supported_image_counts":[1],
            "min_seconds":1,"max_seconds":5,
            "supports_audio":False,"supports_lipsync":False,
            "supports_two_independent_people":False,
            "commercial_rights_verified":False,
            "storage_durable":False,
            "free_unlimited":False,
            "zero_setup":guests.capabilities(),
            "experimental_ai_video":ai_trials.advertised(),
            "longform_15s_audio":{"supported_by_media_assembler":True,
                "ready_for_autonomous_generation":False,
                "supported_output_duration_seconds":[1,15],
                "segment_max_seconds":5,"max_segments":3,
                "requires_three_verified_video_submissions_for_15_seconds":True,
                "has_verified_free_three_segment_gpu_budget":False,
                "audio_modes":["authorized_wav","original_synthetic_sfx"],
                "automatic_singing":False,"voice_generation":False,
                "lip_sync":False,"works_without_output_verification":False,
                "no_unlicensed_media_submissions":True},
            "cpu_photo_studio":{"mode":"cpu_photo_motion",
                "endpoint":"/v1/studio/jobs","supported_image_counts":[1,2],
                "min_seconds":2,"max_seconds":12,
                "supports_user_owned_wav_audio":True,
                "generated_effects":["fart","rain","applause","bird"],
                "synthetic_effects_not_human_voice":True,
                "external_provider_calls":False,"ai_video":False,
                "ephemeral_storage":True},
            "detail":"ניסוי בתמונת ייחוס אחת בלבד; ללא שמע; אישור ידני נדרש"}

@app.get("/v1/compute/capacity")
def compute_capacity(authorization: str | None=Header(default=None)):
    """Live resource indicators: never a paid/GPU/unlimited compute promise."""
    studio_owner(authorization)
    expire_old()
    with LOCK:
        active=sum(v["state"]=="running" for v in JOBS.values())
        queued=sum(v["state"]=="queued" for v in JOBS.values())
    return compute.inspect(work_dir=ROOT,active_jobs=active,
                           queued_jobs=queued).public()

@app.post("/v1/longform/plan")
def longform_preflight(payload: LongformPreview,
                       authorization: str | None=Header(default=None)):
    """Read-only 15s audio + motion plan; no image or GPU calls."""
    studio_owner(authorization)
    result=longform_av.plan(seconds=payload.seconds,
        image_count=payload.image_count,
        voice_requested=payload.voice_requested,
        singing_requested=payload.singing_requested,
        lipsync_requested=payload.lipsync_requested,
        two_independent_people=payload.two_independent_people,
        audio_source=payload.audio_source,
        # Free public Wan access is 1 trial/install and at most 2
        # globally/day. Never infer 3 usable free submissions from 2.
        quota_remaining=0,
        licensed_provider=False,
        consent_to_external_transfer=payload.third_party_transfer_consent)
    return {**result.as_dict(),"media_assembler_implemented":True,
            "provider_submissions_performed":0,
            "autonomous_generating_ready":False}

@app.post("/v1/guest/bootstrap")
def guest_bootstrap(payload:GuestBootstrapRequest):
    return guests.issue(payload.install_id)

@app.post("/v1/ai/jobs", status_code=202)
def new_real_ai_motion_job(payload: NewJob,
                           authorization: str | None=Header(default=None)):
    """Generate actual AI video frames using a public free ZeroGPU demo.

    Explicit third-party photo consent; one image, 1–5s, silent, noncommercial,
    1 submission/install and 2 globally/day. No automatic retries.
    """
    owner=studio_owner(authorization)
    if not owner.startswith("guest:"):
        raise HTTPException(401,"נדרשת הרשאת אורח לניסוי מצומצם")
    expire_old()
    plan=intents.plan(prompt=payload.prompt,seconds=payload.seconds,
        image_count=len(payload.images),requires_audio=payload.requires_audio,
        requires_lipsync=payload.requires_lipsync,
        requires_two_independent_people=payload.requires_two_independent_people,
        commercial_use=payload.commercial_use,
        consent=payload.third_party_transfer_consent,
        compute_available=ai_trials.enabled() and enabled())
    if plan.status!="draft_possible":
        raise HTTPException(422,{
            "message":"מנוע הווידאו החינמי אינו תומך בבקשה הזאת",
            "blockers":list(plan.blockers),
            "alternative_cpu_editor_not_automatic":True})
    try:
        provider.validate(references=len(payload.images),
            seconds=payload.seconds,wants_audio=plan.needs_audio,
            wants_lipsync=plan.needs_lipsync,
            commercial=payload.commercial_use,consent=True)
    except (provider.ProviderUnavailable,provider.UnsupportedRequest) as exc:
        raise HTTPException(503,"מנוע הווידאו הניסיוני אינו זמין כעת") from exc
    data,ext=decode_picture(payload.images[0])
    digest=hashlib.sha256(
        (owner+":real_ai:"+str(payload.seconds)+payload.prompt).encode()
        +data).hexdigest()
    with LOCK:
        existing=DIGESTS.get(digest)
        if existing in JOBS:
            return {"job_id":existing,"state":JOBS[existing]["state"],
                    "deduplicated":True,"mode":"ai_one_image_trial"}
        if sum(job["state"] in ("running","queued")
               for job in JOBS.values()) >= LIMIT:
            raise HTTPException(503,"מנוע הווידאו נמצא בשימוש כרגע",
                                headers={"Retry-After":"60"})
        ai_trials.reserve(owner.removeprefix("guest:"))
        job_id=str(uuid.uuid4())
        folder=ROOT/job_id
        folder.mkdir(parents=True,exist_ok=False,mode=0o700)
        inp=folder/f"reference.{ext}"
        try:
            inp.write_bytes(data)
            inp.chmod(0o600)
        except OSError:
            shutil.rmtree(folder,ignore_errors=True)
            raise HTTPException(500,"לא ניתן להכין את התמונה להפקה")
        JOBS[job_id]={"state":"queued","created_at":time.time(),
            "digest":digest,"owner":owner,"mode":"ai_one_image_trial",
            "detail":"מפיק תנועה במנוע AI ניסיוני, ללא שמע"}
        DIGESTS[digest]=job_id
        POOL.submit(_work,job_id,image=inp,prompt=payload.prompt,
                    seconds=payload.seconds)
        return {"job_id":job_id,"state":"queued","mode":"ai_one_image_trial"}

@app.post("/v1/studio/jobs", status_code=202)
def new_photo_studio_job(payload: PhotoStudioJob,
                         authorization: str | None = Header(default=None)):
    """Actual CPU MP4 edit, separate from any external AI provider."""
    owner=studio_owner(authorization)
    expire_old()
    if payload.mode != "cpu_photo_motion":
        raise HTTPException(422,"מצב עריכה לא נתמך")
    if not payload.media_rights_attested:
        raise HTTPException(422,"חובה לאשר זכויות שימוש בתמונות ובפס הקול")
    images=[decode_picture(pic) for pic in payload.images]
    audio=None
    if payload.soundtrack_wav_base64 is not None:
        try:
            audio=base64.b64decode(payload.soundtrack_wav_base64,validate=True)
        except (binascii.Error,ValueError):
            raise HTTPException(422,"פס הקול אינו תקין")
        if not 100<=len(audio)<=7_000_000 or audio[:4]!=b"RIFF" or audio[8:12]!=b"WAVE":
            raise HTTPException(422,"נתמך קובץ WAV מקורי בלבד, עד 7MB")
    effect=procedural_sfx.recognize(payload.sound_effect_description) if payload.include_procedural_effect else "none"
    if audio is not None and effect!="none":
        raise HTTPException(422,"אי אפשר להחליף אודיו מקורי בלי בחירה מפורשת")
    digest=hashlib.sha256(
        (owner+":cpu_photo_motion:"+str(payload.seconds)+":"+effect).encode()
        +b"".join(blob for blob,_ in images)+(audio or b"")).hexdigest()
    with LOCK:
        existing=DIGESTS.get(digest)
        if existing in JOBS:
            return {"job_id":existing,"state":JOBS[existing]["state"],
                    "mode":"cpu_photo_motion","deduplicated":True}
        active=sum(job["state"]=="running" for job in JOBS.values())
        queued=sum(job["state"]=="queued" for job in JOBS.values())
        snapshot=compute.inspect(work_dir=ROOT,active_jobs=active,
                                 queued_jobs=queued)
        # The hard queue limit remains independently enforced, even if
        # resource telemetry is missing or one sample becomes stale.
        if active+queued>=LIMIT:
            raise HTTPException(503,"תור עריכה חינמי מלא",headers={"Retry-After":"30"})
        pixel_counts=tuple(
            (lambda frame: frame.size[0]*frame.size[1])(
                Image.open(io.BytesIO(blob))) for blob,_ in images)
        compute.admit(snapshot=snapshot,seconds=payload.seconds,
                      pixel_counts=pixel_counts)
        if owner.startswith("guest:"):
            guests.reserve_seconds(owner[6:],payload.seconds)
        job_id=str(uuid.uuid4())
        folder=ROOT/job_id
        folder.mkdir(parents=True,exist_ok=False,mode=0o700)
        photo_paths=[]
        wav=None
        try:
            for index,(blob,ext) in enumerate(images):
                path=folder/f"photo_{index}.{ext}"
                path.write_bytes(blob)
                path.chmod(0o600)
                photo_paths.append(path)
            if audio is not None:
                wav=folder/"user.wav"
                wav.write_bytes(audio)
                wav.chmod(0o600)
        except Exception:
            shutil.rmtree(folder,ignore_errors=True)
            raise HTTPException(500,"שמירת קובצי המקור לעריכה נכשלה")
        JOBS[job_id]={"state":"queued","created_at":time.time(),
             "digest":digest,"mode":"cpu_photo_motion","owner":owner,
             "detail":"עריכת תנועת מצלמה לתמונות, ללא יצירת משחק של דמויות AI"}
        DIGESTS[digest]=job_id
        POOL.submit(_work_photo_studio,job_id,photos=photo_paths,
                    soundtrack=wav,seconds=payload.seconds,effect=effect)
        return {"job_id":job_id,"state":"queued","mode":"cpu_photo_motion"}

def _work_photo_studio(job_id: str, *,
                       photos:list[Path],soundtrack:Path|None,seconds:int,
                       effect:str="none") -> None:
    with LOCK:
        if job_id not in JOBS:return
        JOBS[job_id]["state"]="running"
    try:
        folder=ROOT/job_id
        receipt=studio.render(photos=photos,seconds=seconds,
                 out=folder/"draft.mp4",user_wav=soundtrack,generated_sfx=effect)
        evidence=audio_evidence.inspect_mp4(folder/"draft.mp4",
                        audio_required=(soundtrack is not None or effect!="none"))
        if effect!="none" and evidence.verdict=="reject":
            raise ValueError("SFX audio not audible after processing")
        with LOCK:
            JOBS[job_id].update(state="completed",
                detail="נוצר סרטון עריכת תמונות אמיתי; לא AI וידאו",
                size=receipt.bytes,sha256=receipt.sha256,
                has_audio=receipt.has_audio_track,
                media_kind="cpu_photo_motion",
                quality={**receipt.as_dict(),"measured_audio":evidence.as_dict()})
    except Exception:
        with LOCK:
            if job_id in JOBS:
                JOBS[job_id].update(state="failed",error="cpu_edit_failed",
                    detail="הפקת סרטון עריכת התמונות לא הצליחה")
    finally:
        for item in [*photos,soundtrack]:
            if item is not None:
                try:item.unlink(missing_ok=True)
                except OSError:pass

@app.post("/v1/creative/plan")
def creative_preflight(payload: CreativePreflight,
                       authorization: str | None=Header(default=None)):
    """Read-only plan. No images, provider calls or quota use."""
    studio_owner(authorization)
    result=intents.plan(prompt=payload.prompt,seconds=payload.seconds,
        image_count=payload.image_count, requires_audio=payload.requires_audio,
        requires_lipsync=payload.requires_lipsync,
        requires_two_independent_people=payload.requires_two_independent_people,
        commercial_use=payload.commercial_use,
        consent=payload.third_party_transfer_consent,
        compute_available=enabled() and ai_trials.enabled())
    return result.as_dict()

@app.post("/v1/jobs", status_code=202)
def new_job(payload: NewJob, authorization: str | None=Header(default=None)):
    require_token(authorization)
    expire_old()
    # Diagnose expected scene, speech, identity and duration BEFORE decoding
    # or forwarding private media. Never substitute a shorter silent video.
    readiness=intents.plan(prompt=payload.prompt,seconds=payload.seconds,
         image_count=len(payload.images), requires_audio=payload.requires_audio,
         requires_lipsync=payload.requires_lipsync,
         requires_two_independent_people=payload.requires_two_independent_people,
         commercial_use=payload.commercial_use,
         consent=payload.third_party_transfer_consent,compute_available=enabled())
    if readiness.status != "draft_possible":
        code=503 if "no_enabled_verified_free_gpu_route" in readiness.blockers else 422
        raise HTTPException(code,
           {"message":"ההפקה אינה נתמכת במנוע הנוכחי ללא שינוי בתוכן",
            "blockers":list(readiness.blockers),
            "available":list(readiness.limits)})
    # Fail before decoding and submitting any private image.
    try:
        provider.validate(references=len(payload.images),seconds=payload.seconds,
             wants_audio=readiness.needs_audio,
             wants_lipsync=readiness.needs_lipsync,
             commercial=payload.commercial_use,consent=True)
    except (provider.UnsupportedRequest, provider.ProviderUnavailable) as exc:
        raise HTTPException(422,str(exc)) from exc
    data,ext=decode_picture(payload.images[0])
    fingerprint=hashlib.sha256(
       payload.prompt.encode()+repr(payload.seconds).encode()+data).hexdigest()
    with LOCK:
        if fingerprint in DIGESTS and DIGESTS[fingerprint] in JOBS:
            return {"job_id":DIGESTS[fingerprint],
                    "state":JOBS[DIGESTS[fingerprint]]["state"],
                    "detail":"בקשה זהה כבר נרשמה; לא נשלחה שוב"}
        if sum(j["state"] in ("queued","running") for j in JOBS.values()) >= LIMIT:
            raise HTTPException(503,"תור הניסוי מלא",headers={"Retry-After":"90"})
        job_id=str(uuid.uuid4())
        folder=ROOT/job_id
        folder.mkdir(parents=True,exist_ok=False,mode=0o700)
        image=folder/f"reference.{ext}"
        try:
            image.write_bytes(data)
            image.chmod(0o600)
        except Exception:
            shutil.rmtree(folder,ignore_errors=True)
            raise HTTPException(500,"לא ניתן להכין קובץ מקור")
        JOBS[job_id]={"state":"queued","created_at":time.time(),"digest":fingerprint,
            "detail":"נשלח לתור מנוע ניסיוני; תוצאת AI אינה מובטחת"}
        DIGESTS[fingerprint]=job_id
        POOL.submit(_work,job_id,image=image,prompt=payload.prompt,seconds=payload.seconds)
        return {"job_id":job_id,"state":"queued"}

def owned(job_id: str, authorization: str | None):
    owner=studio_owner(authorization)
    expire_old()
    try:uuid.UUID(job_id)
    except (ValueError,TypeError):raise HTTPException(404,"העבודה אינה קיימת")
    with LOCK:
        job=JOBS.get(job_id)
        if not job:raise HTTPException(404,"העבודה אינה קיימת")
        if owner!="master" and (job.get("mode") not in (
                "cpu_photo_motion","ai_one_image_trial")
                or job.get("owner")!=owner):
            raise HTTPException(404,"העבודה אינה קיימת")
        return dict(job)

@app.get("/v1/jobs/{job_id}")
def status(job_id: str, authorization: str | None=Header(default=None)):
    job=owned(job_id,authorization)
    return {"job_id":job_id,"state":job["state"],
            "detail":job.get("detail",""),
            "error":job.get("error"),
            "has_audio":job.get("has_audio",False),
            "quality":job.get("quality") if job["state"]=="completed" else None}

@app.get("/v1/jobs/{job_id}/result")
def download(job_id: str, authorization: str | None=Header(default=None)):
    job=owned(job_id,authorization)
    if job["state"]!="completed":
        raise HTTPException(409,"הסרטון עדיין אינו זמין")
    file=ROOT/job_id/"draft.mp4"
    if not file.is_file() or file.stat().st_size!=job["size"]:
        raise HTTPException(409,"לא ניתן לאמת את שלמות הסרטון")
    with file.open("rb") as f:
        if hashlib.file_digest(f,"sha256").hexdigest()!=job["sha256"]:
            raise HTTPException(409,"בדיקת שלמות הסרטון נכשלה")
    return FileResponse(file,media_type="video/mp4",filename="kolbo-ai-draft.mp4",
                        headers={"Cache-Control":"private, no-store"})
