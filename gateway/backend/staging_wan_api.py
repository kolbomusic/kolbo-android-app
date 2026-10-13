"""Kolbo Video v4.1.6 isolated staging API for the ONE-image public Wan demo.

Speaks the existing Android PrivateRenderClient protocol. No production
deployment, no database, no durable storage, no commercial right/voice/duo
claim. Strict opt-in and no automatic retries of uncertain vendor jobs.
"""
from __future__ import annotations
import base64, binascii, hashlib, hmac, io, json, os, secrets, shutil, threading, time, uuid, logging
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
import free_gpu_journal as gpu_journal
import longform_av
import experimental_ltx25_native_av as ltx
import experimental_scene_builder_v433 as stage_builder
import scene_integrity_v433 as scene_integrity
import identity_guard_v435 as identity_gate
import local_face_repair_v435 as face_repair
import native_av_failure_codes_v436 as failure_codes
import stage_provider_cooldown_v438 as scene_cooldown

APP_TITLE = "Kolbo Video Experimental Wan Gateway (NOT production)"
app = FastAPI(title=APP_TITLE, docs_url=None, redoc_url=None, openapi_url=None)
ROOT = Path(os.getenv("KOLBO_V416_WORK_DIR", "/tmp/kolbo-v416-worker"))
MAX_IMAGE = 5_000_000
TTL = 3600
LIMIT = 1
LOCK = threading.RLock()
POOL = ThreadPoolExecutor(max_workers=LIMIT, thread_name_prefix="kolbo-v416")
LOG = logging.getLogger("kolbo.native_av")
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

class NativeAVJob(BaseModel):
    """Actual submit: must provide the image bytes selected during preflight."""
    prompt: str = Field(min_length=5, max_length=3000)
    seconds: float = Field(ge=1, le=15)
    images: list[Picture] = Field(default_factory=list,max_length=1)
    third_party_transfer_consent: bool = False
    commercial_use: bool = False
    requires_shared_stage_scene: bool = False

class NativeAVPlan(BaseModel):
    """Metadata ONLY: no photo upload, GPU job or quota charge.

    Installed Android v4.3.3 posts image_count=1 but intentionally omits
    images until POST /v1/native-av/jobs after preflight approval. Using
    NativeAVJob for /plan silently ignored image_count, causing the
    erroneous combined_two_person_reference_required blocker.
    """
    prompt: str = Field(min_length=5, max_length=3000)
    seconds: float = Field(ge=1, le=15)
    image_count: int | None = Field(default=None, ge=0, le=1)
    images: list[Picture] = Field(default_factory=list,max_length=1)
    third_party_transfer_consent: bool = False
    commercial_use: bool = False
    requires_shared_stage_scene: bool = False

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

def configured_free_gpu_journal():
    """Experimental persistence only: an operator must verify a PRIVATE durable volume.

    Does not enable GPU, alter anonymous limits, or make /tmp durable.
    """
    path=os.getenv("KOLBO_FREE_GPU_JOURNAL_PATH","")
    if not path:
        return None
    if os.getenv("KOLBO_FREE_GPU_PERSISTENT_VOLUME_VERIFIED")!="EXPLICITLY_ENABLED":
        raise HTTPException(503,"אין אחסון מתמיד מאומת להפעלת היומן")
    # Metadata and media must be colocated on the same explicitly verified
    # private durable root. SQLite alone cannot make ephemeral MP4 persistent.
    if Path(path).parent.resolve()!=ROOT.resolve() or ROOT.is_symlink():
        raise HTTPException(503,"יומן המשימות וקובצי הווידאו חייבים אחסון מתמיד משותף")
    try:
        return gpu_journal.FreeGpuJournal(path)
    except (gpu_journal.JournalError,OSError) as exc:
        raise HTTPException(503,"יומן משימות GPU אינו זמין") from exc


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

def _work(job_id: str, *, image: Path, prompt: str, seconds: float,
          journal=None, owner_hash=None) -> None:
    with LOCK:
        if job_id not in JOBS:return
        JOBS[job_id]["state"]="running"
    folder=ROOT/job_id
    try:
        # Persist uncertainty before any upload or network submission.
        if journal is not None:
            journal.change(job_id,owner_hash,"submitting",provider="wan_fast")
        dst=folder/"draft.mp4"
        receipt=provider.submit_one(reference=image,prompt=prompt,seconds=seconds,
            destination=dst,consent=True,commercial=False,wants_audio=False,wants_lipsync=False)
        if journal is not None:
            journal.change(job_id,owner_hash,"result_received")
        # Output validated by provider.ffprobe then again by decoded-frame QA.
        visual=visual_quality.inspect_mp4(dst,audio_required=False)
        sound=audio_evidence.inspect_mp4(dst,audio_required=False)
        # A valid MP4 with nearly identical frames is NOT successful AI.
        if visual.pixel_change_fraction < 0.012:
            raise ValueError("Output is visually frozen: no measurable motion")
        if journal is not None:
            journal.change(job_id,owner_hash,"validating")
            with dst.open("rb") as proof:
                media_hash=hashlib.file_digest(proof,"sha256").hexdigest()
            if receipt.sha256!=media_hash:
                raise ValueError("GPU output digest mismatch")
            journal.change(job_id,owner_hash,"completed",verified_media_digest=media_hash)
        with LOCK:
            JOBS[job_id].update(state="completed",detail="התקבלה טיוטת וידאו לא מאומתת",
                size=receipt.bytes,sha256=receipt.sha256,has_audio=receipt.audio,
                quality={'visual':visual.as_dict(),'audio':sound.as_dict(),
                         'requires_semantic_review':True,
                         'motion_measured':True,'voice_verified':False})
    except Exception as exc:
        # No automatic resend: provider might have accepted and spent quota.
        kind="acceptance_unknown" if isinstance(exc,provider.UnknownAcceptance) else "generation_failed"
        if journal is not None:
            try:
                record=journal.get(job_id,owner_hash)
                if record.state=="submitting":
                    journal.change(job_id,owner_hash,"acceptance_unknown")
                elif record.state in ("result_received","validating","accepted"):
                    journal.change(job_id,owner_hash,"failed_unverified")
            except gpu_journal.JournalError:
                LOG.warning("Free GPU journal needs operator reconciliation")
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
            "two_person_scene_builder":{
                "mode":"FLUX_Kontext_to_LTX_native_AV",
                "ready":os.getenv("KOLBO_SCENE_BUILDER_V433")=="EXPLICITLY_ENABLED"
                         and os.getenv("KOLBO_NATIVE_LTX25_TRIAL")=="EXPLICITLY_ENABLED"
                         and ai_trials.enabled() and enabled()
                         and scene_cooldown.FLUX_COOLDOWN.remaining()==0,
                "recent_quota_denial_observed":scene_cooldown.FLUX_COOLDOWN.remaining()>0,
                "retry_after_seconds":scene_cooldown.FLUX_COOLDOWN.remaining(),
                "provider_global_availability_verified":False,
                "requires_two_sequential_public_gpu_inferences":True,
                "split_screen_is_valid_success":False,
                "accepts_one_combined_reference":True,
                "two_person_identity_verified":False,
                "automated_face_similarity_guard_ready":identity_gate.configured(),
                "face_similarity_check_mandatory":True,
                "local_original_face_pixel_repair_enabled":face_repair.enabled(),
                "identity_guaranteed":False,
                "crowd_and_stage_semantics_verified":False,
                "language_and_lip_sync_verified":False,
                "free_gpu_availability_guaranteed":False},
            "native_audio_video_trial":{
                "mode":"native_ltx25_av_trial",
                "ready":os.getenv("KOLBO_NATIVE_LTX25_TRIAL")=="EXPLICITLY_ENABLED"
                   and ai_trials.enabled() and enabled(),
                "supported_image_counts":[0,1],
                "min_seconds":1,"max_seconds":15,
                "generates_visual_motion":True,"native_audio":True,
                "speech_language_verified":False,
                "singing_lipsync_verified":False,
                "two_people_identity_verified":False,
                "external_transfer_consent_required":True,
                "shared_public_gpu_with_quotas":True,
                "global_daily_trial_submissions":ai_trials.GLOBAL_PER_UTC_DAY,
                "per_install_daily_submissions":ai_trials.PER_INSTALL_PER_UTC_DAY,
                "availability_guaranteed":False,
                "commercial_rights_verified":False,
                "no_paid_provider_fallback":True},
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
    journal=configured_free_gpu_journal()
    owner_hash=owner.removeprefix("guest:")
    with LOCK:
        if journal is not None:
            try:
                record=journal.reserve(owner_hash,digest,digest,
                    max_daily_owner=ai_trials.PER_INSTALL_PER_UTC_DAY,
                    max_daily_global=ai_trials.GLOBAL_PER_UTC_DAY)
            except gpu_journal.QuotaExceeded as exc:
                raise HTTPException(429,"מכסת ניסוי GPU משותפת נוצלה להיום",
                                    headers={"Retry-After":"3600"}) from exc
            except gpu_journal.JournalError as exc:
                raise HTTPException(503,"יומן הניסויים המתמיד אינו זמין") from exc
            if not record.created_new:
                # On restart 'submitting' must never be POSTed again.
                state=("acceptance_unknown" if record.state=="submitting" else record.state)
                return {"job_id":record.job_id,"state":state,
                        "deduplicated":True,"mode":"ai_one_image_trial",
                        "needs_operator_reconciliation":record.state in
                            ("submitting","acceptance_unknown")}
            job_id=record.job_id
        else:
            existing=DIGESTS.get(digest)
            if existing in JOBS:
                return {"job_id":existing,"state":JOBS[existing]["state"],
                        "deduplicated":True,"mode":"ai_one_image_trial"}
            job_id=str(uuid.uuid4())
        try:
            if sum(job["state"] in ("running","queued")
                   for job in JOBS.values()) >= LIMIT:
                raise HTTPException(503,"מנוע הווידאו נמצא בשימוש כרגע",
                                    headers={"Retry-After":"60"})
            ai_trials.reserve(owner_hash)
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
                        seconds=payload.seconds,journal=journal,owner_hash=owner_hash)
        except Exception:
            if journal is not None:
                try:journal.change(job_id,owner_hash,"rejected_before_submission")
                except gpu_journal.JournalError:pass
            raise
        return {"job_id":job_id,"state":"queued","mode":"ai_one_image_trial",
                "journal_enabled":journal is not None}

@app.post("/v1/native-av/plan")
def native_av_preflight(payload: NativeAVPlan,
                        authorization: str | None=Header(default=None)):
    """No upload, no provider call, no credits deducted.

    Preflight checks the declared image count without requiring bytes.
    The actual submission validates and decodes the image separately.
    """
    studio_owner(authorization)
    supplied_count=len(payload.images)
    count=supplied_count if payload.image_count is None else payload.image_count
    blockers=[]
    if payload.image_count is not None and supplied_count and supplied_count!=count:
        blockers.append("image_count_and_supplied_images_disagree")
    if not payload.third_party_transfer_consent:
        blockers.append("external_prompt_and_image_transfer_consent_required")
    if payload.commercial_use:
        blockers.append("commercial_use_unverified")
    if os.getenv("KOLBO_NATIVE_LTX25_TRIAL")!="EXPLICITLY_ENABLED" or not ai_trials.enabled() or not enabled():
        blockers.append("public_native_audio_video_model_not_available")
    if count>1:
        blockers.append("at_most_one_start_image")
    if payload.requires_shared_stage_scene:
        if count!=1:
            blockers.append("combined_two_person_reference_required")
        if os.getenv("KOLBO_SCENE_BUILDER_V433")!="EXPLICITLY_ENABLED":
            blockers.append("two_person_scene_builder_unavailable")
        if not identity_gate.configured():
            blockers.append("local_face_similarity_guard_unavailable")
        if scene_cooldown.FLUX_COOLDOWN.remaining()>0:
            blockers.append("מנוע FLUX בהמתנה לאחר מגבלת GPU ציבורית; אין צורך לשלוח את התמונות שוב כרגע")
    remaining=(scene_cooldown.FLUX_COOLDOWN.remaining()
               if payload.requires_shared_stage_scene else 0)
    return {"status":"eligible_for_attempt" if not blockers else "blocked",
        "blockers":blockers,
        "cooldown_reason":"recent_public_quota_rejection" if remaining else None,
        "retry_after_seconds":remaining,
        "provider_global_availability_verified":False,
        "supported_duration_seconds":[1,15],
        "source":"external_public_LTX25_demo",
        "native_audio_expected":True,
        "speech_singing_lipsync_quality_not_guaranteed":True,
        "free_compute_unlimited":False,
        "commercial_rights_verified":False,
        "credits_spent":0}

def _work_native_av(job_id:str,reference:Path|None,prompt:str,seconds:float,
                    requires_shared_stage_scene:bool=False) -> None:
    with LOCK:
        if job_id not in JOBS:return
        JOBS[job_id]["state"]="running"
        JOBS[job_id]["phase"]="source_face_check" if requires_shared_stage_scene else "native_video_audio_generation"
    phase="source_face_check" if requires_shared_stage_scene else "native_video_audio_generation"
    guard=None
    def next_phase(name:str,detail:str):
        nonlocal phase
        phase=name
        with LOCK:
            if job_id in JOBS:
                JOBS[job_id].update(phase=phase,detail=detail)
    started=time.monotonic()
    try:
        folder=ROOT/job_id
        model_reference=reference
        scene_receipt=None
        face_still_evidence=None
        face_video_evidence=[]
        if requires_shared_stage_scene:
            if reference is None:
                raise ValueError("Missing combined two-person source reference")
            # Before spending ANY free GPU time: require TWO distinct source
            # faces and available local (not third-party) identity verifier.
            guard=identity_gate.JobIdentityGuard(reference)
            next_phase("shared_stage_generation","יוצר במת הופעה משותפת משתי הדמויות...")
            if scene_cooldown.FLUX_COOLDOWN.remaining()>0:
                raise stage_builder.SceneUnavailable(
                    "Public FLUX quota cooldown observed on this process",
                    reason="public_gpu_quota_or_busy")
            stage=folder/"generated-shared-stage.png"
            scene_receipt=stage_builder.build(
                source=reference,prompt=prompt,destination=stage,
                consent=True,commercial=False)
            model_reference=stage
            next_phase("shared_stage_face_check","בודק את פני שתי הדמויות בתמונת הבמה...")
            try:
                face_still_evidence=guard.verify_still(stage)
            except identity_gate.IdentityMismatch:
                # One optional LOCAL repair from the user's original face
                # pixels. It spends no extra external GPU credits. The
                # repaired stage MUST pass the same strict SFace identity
                # gate; otherwise no LTX movie is sent or marked success.
                if not face_repair.enabled():
                    raise
                next_phase("local_face_repair","מנסה לשפר את התאמת הפנים באופן מקומי...")
                corrected=folder/"local-face-restored-stage.png"
                face_repair.reconstruct(reference,stage,corrected)
                face_still_evidence=guard.verify_still(corrected)
                model_reference=corrected
        next_phase("native_video_audio_generation","מנוע הווידאו והשמע מפיק תנועה ופס קול...")
        receipt=ltx.generate(prompt=prompt,seconds=seconds,
            reference=model_reference,
            destination=folder/"draft.mp4",consent=True,commercial=False)
        next_phase("video_media_quality_check","בודק שהסרטון כולל תנועה תקינה ושמע...")
        scene=scene_integrity.inspect_video(folder/"draft.mp4")
        if scene.output_is_split_layout:
            raise ValueError("Rejected picture-in-picture or persistent split portrait output")
        if scene.near_static_frames:
            raise ValueError("Rejected nearly frozen output despite valid audio/metadata")
        if guard is not None:
            next_phase("video_face_check","בודק שהפנים נשמרו בשלושה שלבים לאורך הסרטון...")
            # Three sampled frames: reject when either face drifts, vanishes,
            # merges or swaps. Similarity is NOT perfect identity proof.
            face_video_evidence=guard.verify_video(folder/"draft.mp4")
        quality={**receipt.as_dict(),"scene_audit":scene.as_dict(),
            "shared_scene_generated_by_image_model":scene_receipt is not None,
            "stage_builder_quality":scene_receipt.as_dict() if scene_receipt else None,
            "face_similarity_check_passed":(
                face_still_evidence is not None and len(face_video_evidence)==3
                if requires_shared_stage_scene else False),
            "face_stage_scores":face_still_evidence.as_dict()
                 if face_still_evidence is not None else None,
            "face_video_scores":[x.as_dict() for x in face_video_evidence],
            "all_actors_identity_unchanged_verified":False,
            "automated_face_similarity_is_identity_guarantee":False,
            "duet_singing_verified":False,
            "audience_10k_verified":False,
            "requires_manual_scene_and_voice_review":True}
        next_phase("publishing","מפרסם את הטיוטה לאחר בדיקות התקינות...")
        with LOCK:
            JOBS[job_id].update(state="completed",phase="completed",
                detail="טיוטת AI עם תנועה ושמע; נדרשת בדיקת שתי הדמויות, הבמה והשירה.",
                mode="native_ltx25_av_trial",
                media_kind="native_ltx25_av_trial",
                size=receipt.size_bytes,sha256=receipt.sha256,
                has_audio=True,quality=quality)
    except Exception as exc:
        safe=failure_codes.classify(exc,phase)
        if (safe.error=="stage_public_gpu_quota_or_busy"
                and phase=="shared_stage_generation"):
            scene_cooldown.FLUX_COOLDOWN.record_quota_failure()
        # Never log raw exceptions, images, prompts, auth, or face vectors.
        LOG.warning("native_ai_job_failed diagnostic=%s phase=%s code=%s elapsed_s=%d",
                    job_id[:8],safe.phase,safe.error,
                    int(time.monotonic()-started))
        with LOCK:
            if job_id in JOBS:
                JOBS[job_id].update(state="failed",phase=safe.phase,
                    error=safe.error,detail=safe.detail,
                    diagnostic_id=job_id[:8])
    finally:
        if guard is not None:guard.discard()
        # Failed or unverified drafts must never stay downloadable. Source
        # embeddings are kept solely in memory; source file is removed.
        with LOCK:
            approved=JOBS.get(job_id,{}).get("state")=="completed"
        if not approved:
            try:(ROOT/job_id/"draft.mp4").unlink(missing_ok=True)
            except OSError:pass
        if reference is not None:
            try:reference.unlink(missing_ok=True)
            except OSError:pass
        try:(ROOT/job_id/"generated-shared-stage.png").unlink(missing_ok=True)
        except OSError:pass
        try:(ROOT/job_id/"local-face-restored-stage.png").unlink(missing_ok=True)
        except OSError:pass

@app.post("/v1/native-av/jobs", status_code=202)
def new_native_av_job(payload: NativeAVJob,
                      authorization: str | None=Header(default=None)):
    """Explicitly opt-in to one free public model with natural motion+sound.

    This demo is neither guaranteed free forever nor a production model SLA.
    Quotas are per-process and stop double submits; they aren't a paid GPU pool.
    """
    owner=studio_owner(authorization)
    if not owner.startswith("guest:"):
        raise HTTPException(401,"חיבור אורח מוגבל בלבד למסלול הווידאו החינמי")
    expire_old()
    try:
        ltx.validate(prompt=payload.prompt,seconds=payload.seconds,
            references=len(payload.images),
            consent=payload.third_party_transfer_consent,
            commercial=payload.commercial_use)
    except ltx.Unsupported as exc:
        raise HTTPException(422,str(exc)) from exc
    except ltx.Unavailable as exc:
        raise HTTPException(503,"מנוע הווידאו והשמע אינו זמין כעת") from exc
    if not payload.third_party_transfer_consent:
        raise HTTPException(422,"נדרש אישור להעברת ההנחיה והמדיה לשירות הציבורי")
    if payload.requires_shared_stage_scene:
        if len(payload.images)!=1:
            raise HTTPException(422,"שתי דמויות מחייבות תמונת מקור משולבת אחת")
        if os.getenv("KOLBO_SCENE_BUILDER_V433")!="EXPLICITLY_ENABLED":
            raise HTTPException(503,
                "הקמת במה משותפת לשתי דמויות עדיין אינה זמינה; לא נשלח וידאו חלקי",
                headers={"Retry-After":"300"})
        if not identity_gate.configured():
            raise HTTPException(503,
                "בדיקת שמירת שתי הדמויות אינה זמינה כרגע. לא נתחיל הפקה שעלולה להחליף פנים.",
                headers={"Retry-After":"300"})
        remaining=scene_cooldown.FLUX_COOLDOWN.remaining()
        if remaining>0:
            raise HTTPException(503,
                "מנוע FLUX הציבורי דחה לאחרונה בקשה בגלל מכסת GPU או עומס. "
                "ממתינים לפני ניסיון נוסף כדי לא לשלוח תמונות לשווא.",
                headers={"Retry-After":str(remaining)})
    images=[decode_picture(pic) for pic in payload.images]
    digest=hashlib.sha256(
        (owner+":ltx_native:"+str(payload.seconds)+":"+
         str(payload.requires_shared_stage_scene)+":"+payload.prompt).encode()
        +b"".join(blob for blob,_ in images)).hexdigest()
    with LOCK:
        old=DIGESTS.get(digest)
        if old in JOBS:
            return {"job_id":old,"state":JOBS[old]["state"],
                "deduplicated":True,"mode":"native_ltx25_av_trial"}
        if sum(job["state"] in ("queued","running") for job in JOBS.values())>=LIMIT:
            raise HTTPException(503,"תור הפקת AI כרגע מלא",
                                headers={"Retry-After":"60"})
        ai_trials.reserve(owner.removeprefix("guest:"))
        job_id=str(uuid.uuid4())
        folder=ROOT/job_id
        folder.mkdir(parents=True,exist_ok=False,mode=0o700)
        ref=None
        if images:
            image_bytes,ext=images[0]
            ref=folder/f"reference.{ext}"
            try:
                ref.write_bytes(image_bytes)
                ref.chmod(0o600)
            except OSError:
                shutil.rmtree(folder,ignore_errors=True)
                raise HTTPException(500,"הכנת תמונת המקור נכשלה")
        JOBS[job_id]={"state":"queued","phase":"queued",
            "created_at":time.time(),"digest":digest,"owner":owner,
            "mode":"native_ltx25_av_trial",
            "detail":"מכין את הפקת הווידאו והשמע; עדיין לא בוצעה בדיקת פנים"}
        DIGESTS[digest]=job_id
        POOL.submit(_work_native_av,job_id,ref,payload.prompt,
                    payload.seconds,payload.requires_shared_stage_scene)
        return {"job_id":job_id,"state":"queued","mode":"native_ltx25_av_trial"}

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
        if not job:
            journal=configured_free_gpu_journal()
            if journal is None or not owner.startswith("guest:"):
                raise HTTPException(404,"העבודה אינה קיימת")
            try:
                record=journal.get(job_id,owner.removeprefix("guest:"))
            except gpu_journal.JournalError:
                raise HTTPException(404,"העבודה אינה קיימת")
            state="acceptance_unknown" if record.state=="submitting" else record.state
            media_file=ROOT/job_id/"draft.mp4"
            if state=="completed" and (media_file.is_symlink() or
                    not media_file.is_file() or (ROOT/job_id).is_symlink()):
                state="result_unavailable"
            return {"state":state,"owner":owner,"mode":"ai_one_image_trial",
                    "detail":"התאוששות ממשימה קודמת — אין שליחה אוטומטית נוספת ל־GPU",
                    "sha256":record.media_sha256,"has_audio":False,"quality":None,
                    "size":(ROOT/job_id/"draft.mp4").stat().st_size
                          if state=="completed" else 0}
        if owner!="master" and (job.get("mode") not in (
                "cpu_photo_motion","ai_one_image_trial","native_ltx25_av_trial")
                or job.get("owner")!=owner):
            raise HTTPException(404,"העבודה אינה קיימת")
        return dict(job)

@app.get("/v1/jobs/{job_id}")
def status(job_id: str, authorization: str | None=Header(default=None)):
    job=owned(job_id,authorization)
    return {"job_id":job_id,"state":job["state"],
            "detail":job.get("detail",""),
            "error":job.get("error"),
            "phase":job.get("phase"),
            "diagnostic_id":job.get("diagnostic_id"),
            "has_audio":job.get("has_audio",False),
            "quality":job.get("quality") if job["state"]=="completed" else None}

@app.get("/v1/jobs/{job_id}/result")
def download(job_id: str, authorization: str | None=Header(default=None)):
    job=owned(job_id,authorization)
    if job["state"]!="completed":
        raise HTTPException(409,"הסרטון עדיין אינו זמין")
    file=ROOT/job_id/"draft.mp4"
    if file.is_symlink() or (ROOT/job_id).is_symlink() or not file.is_file() or file.stat().st_size!=job["size"]:
        raise HTTPException(409,"לא ניתן לאמת את שלמות הסרטון")
    with file.open("rb") as f:
        if hashlib.file_digest(f,"sha256").hexdigest()!=job["sha256"]:
            raise HTTPException(409,"בדיקת שלמות הסרטון נכשלה")
    return FileResponse(file,media_type="video/mp4",filename="kolbo-ai-draft.mp4",
                        headers={"Cache-Control":"private, no-store"})
