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

def require_token(authorization: str | None) -> None:
    secret=os.getenv("KOLBO_V416_API_TOKEN","")
    if len(secret)<32 or not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "נדרש חיבור מאובטח", headers={"WWW-Authenticate":"Bearer"})
    if not hmac.compare_digest(authorization[7:].encode(),secret.encode()):
        raise HTTPException(401, "הרשאה לא תקינה", headers={"WWW-Authenticate":"Bearer"})

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
        with LOCK:
            JOBS[job_id].update(state="completed",detail="התקבלה טיוטת וידאו לא מאומתת",
                size=receipt.bytes,sha256=receipt.sha256,has_audio=receipt.audio,
                quality={'visual':visual.as_dict(),'audio':sound.as_dict()})
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
    require_token(authorization)
    expire_old()
    return {"status":"ready" if enabled() else "not_ready",
            "provider":"zerogpu-wan2.2-experimental",
            "supported_image_counts":[1],
            "min_seconds":1,"max_seconds":5,
            "supports_audio":False,"supports_lipsync":False,
            "supports_two_independent_people":False,
            "commercial_rights_verified":False,
            "storage_durable":False,
            "free_unlimited":False,
            "detail":"ניסוי בתמונת ייחוס אחת בלבד; ללא שמע; אישור ידני נדרש"}

@app.post("/v1/jobs", status_code=202)
def new_job(payload: NewJob, authorization: str | None=Header(default=None)):
    require_token(authorization)
    expire_old()
    if not enabled():
        raise HTTPException(503,"שרת הניסוי אינו מופעל; נדרשים אישור, כלי וידאו והרשאות")
    if not payload.third_party_transfer_consent:
        raise HTTPException(422,"נדרשת הסכמה מפורשת להעברת תמונה לספק חיצוני")
    # Fail before decoding and submitting any private image.
    try:
        provider.validate(references=len(payload.images),seconds=payload.seconds,
             wants_audio=False,wants_lipsync=False,commercial=False,consent=True)
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
    require_token(authorization)
    expire_old()
    try:uuid.UUID(job_id)
    except (ValueError,TypeError):raise HTTPException(404,"העבודה אינה קיימת")
    with LOCK:
        job=JOBS.get(job_id)
        if not job:raise HTTPException(404,"העבודה אינה קיימת")
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
