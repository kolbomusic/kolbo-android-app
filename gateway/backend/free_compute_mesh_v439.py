"""Kolbo Video 4.3.9: free-only, evidence-gated compute mesh routing.

A *decision layer*, not a GPU, job store or public worker registry. No quotas,
credit issuance, app cooldowns or paid fallbacks. An operator must separately
verify/approve each donated worker. A donor's own capacity can still be finite.

The caller must maintain the durable job ledger and private media separately.
Never send personal images to any worker without the user's informed consent
for that exact destination; never infer consent from an uploaded file.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Iterable, Literal
import math
import re

ID = re.compile(r"^[a-z][a-z0-9_-]{2,63}$")
HASH = re.compile(r"^[0-9a-f]{64}$")
MAX_PROOF_AGE_SECONDS = 300

class NoFreeWorker(RuntimeError):
    """No independently verified, currently compatible donated capacity."""

class UnknownSubmission(RuntimeError):
    """The remote worker may already have accepted; do not re-submit."""

class ExplicitRejection(RuntimeError):
    """The worker definitively did not create a task."""

@dataclass(frozen=True)
class GenerationRequest:
    digest: str
    duration_seconds: float
    reference_count: int
    needs_audio: bool = True
    needs_singing: bool = False
    needs_two_people: bool = False
    needs_lipsync: bool = False
    commercial: bool = False
    user_consented_to_external_worker: bool = False

    def __post_init__(self):
        if not isinstance(self.digest, str) or not HASH.fullmatch(self.digest):
            raise ValueError("Bad opaque request digest")
        if not isinstance(self.duration_seconds, (int, float)) or isinstance(self.duration_seconds, bool) or not math.isfinite(self.duration_seconds) or not 1 <= self.duration_seconds <= 15:
            raise ValueError("Video length must be 1 to 15 seconds")
        if type(self.reference_count) is not int or self.reference_count not in (0, 1, 2):
            raise ValueError("Zero, one or two independent references are allowed")
        for name in ("needs_audio","needs_singing","needs_two_people","needs_lipsync","commercial","user_consented_to_external_worker"):
            if type(getattr(self,name)) is not bool:raise ValueError("Boolean capability required: "+name)
        if self.needs_two_people and self.reference_count != 2:
            raise ValueError("Independent two-person identity needs two references")
        if (self.needs_singing or self.needs_lipsync) and not self.needs_audio:
            raise ValueError("Singing / lipsync requires audio")

@dataclass(frozen=True)
class VerifiedWorker:
    name: str
    operator_approved: bool
    authenticated_transport: bool
    tested_at: float
    zero_user_cost_verified: bool
    can_accept_private_media: bool
    available_slots: int
    waiting_jobs: int
    max_video_seconds: float
    max_independent_references: int
    generates_real_motion: bool
    supports_audio: bool
    supports_singing: bool
    supports_lipsync: bool
    supports_independent_two_person_identity: bool
    identity_qa_available: bool
    supports_commercial_use: bool
    # Each proof is operator-attested from a real synthetic video+audio test,
    # not from self-assertions in HTTP response metadata.
    synthetic_output_verified: bool

    def __post_init__(self):
        if not isinstance(self.name,str) or not ID.fullmatch(self.name):raise ValueError("Bad worker name")
        if type(self.available_slots) is not int or self.available_slots < 0:raise ValueError("Bad capacity")
        if type(self.waiting_jobs) is not int or self.waiting_jobs < 0:raise ValueError("Bad queue depth")
        if type(self.max_independent_references) is not int or self.max_independent_references not in (0,1,2):raise ValueError("Bad reference capability")
        if not isinstance(self.tested_at,(int,float)) or not math.isfinite(self.tested_at):raise ValueError("Bad verification time")
        if not isinstance(self.max_video_seconds,(int,float)) or not math.isfinite(self.max_video_seconds) or self.max_video_seconds<=0:raise ValueError("Bad duration")
        for key in ("operator_approved","authenticated_transport","zero_user_cost_verified","can_accept_private_media","generates_real_motion","supports_audio","supports_singing","supports_lipsync","supports_independent_two_person_identity","identity_qa_available","supports_commercial_use","synthetic_output_verified"):
            if type(getattr(self,key)) is not bool:raise ValueError("Bad proof field: "+key)

def compatible(req: GenerationRequest,worker: VerifiedWorker,*,now:float)->bool:
    """Compatibility claims do not establish absolute fidelity or availability."""
    if not math.isfinite(now) or not 0<=now-worker.tested_at<=MAX_PROOF_AGE_SECONDS:return False
    if not all((worker.operator_approved,worker.authenticated_transport,
                worker.zero_user_cost_verified,worker.synthetic_output_verified,
                worker.generates_real_motion)):return False
    if worker.available_slots < 1 or worker.max_video_seconds < req.duration_seconds:return False
    if req.reference_count > worker.max_independent_references:return False
    if req.reference_count and not (req.user_consented_to_external_worker and worker.can_accept_private_media):return False
    if req.needs_audio and not worker.supports_audio:return False
    if req.needs_singing and not worker.supports_singing:return False
    if req.needs_lipsync and not worker.supports_lipsync:return False
    if req.needs_two_people and not (worker.supports_independent_two_person_identity and worker.identity_qa_available):return False
    if req.commercial and not worker.supports_commercial_use:return False
    return True

def candidates(req:GenerationRequest,workers:Iterable[VerifiedWorker],*,now:float)->list[VerifiedWorker]:
    """Only eligible and free workers; no hidden timed lock or app daily quota."""
    unique={}
    for worker in workers:
        if worker.name in unique:raise ValueError("Duplicate worker ID")
        unique[worker.name]=worker
    return sorted((w for w in unique.values() if compatible(req,w,now=now)),
                  key=lambda w:(w.waiting_jobs,w.name))

@dataclass(frozen=True)
class RouteDecision:
    state: Literal["waiting_for_free_compute","worker_accepted","acceptance_unknown"]
    worker_name: str|None
    worker_task_id: str|None
    attempted: tuple[str,...]
    output_verified: bool=False
    credits_spent: int=0
    user_charged: bool=False
    free_compute_guaranteed: bool=False

def dispatch(req:GenerationRequest,workers:Iterable[VerifiedWorker],*,now:float,
             submit:Callable[[VerifiedWorker,GenerationRequest],str])->RouteDecision:
    """Caller must mark job submitting durably BEFORE invoking this method.

    Explicit no-task rejection permits fallback. All other exceptions mean
    UNKNOWN acceptance; never dispatch again until reconciled by task ID.
    """
    tried=[]
    for worker in candidates(req,workers,now=now):
        tried.append(worker.name)
        try:
            task=submit(worker,req)
        except ExplicitRejection:
            continue
        except Exception:
            return RouteDecision("acceptance_unknown",worker.name,None,tuple(tried))
        if not isinstance(task,str) or not re.fullmatch(r"[A-Za-z0-9_-]{4,150}",task):
            return RouteDecision("acceptance_unknown",worker.name,None,tuple(tried))
        return RouteDecision("worker_accepted",worker.name,task,tuple(tried))
    return RouteDecision("waiting_for_free_compute",None,None,tuple(tried))

@dataclass(frozen=True)
class QualityEvidence:
    duration_seconds: float
    visual_motion_verified: bool
    audio_stream_verified: bool
    audible_audio_verified: bool
    two_identity_matches_verified: bool
    story_adherence_verified: bool
    singing_verified: bool=False
    lipsync_verified: bool=False
    # Evidence must come from independent model/QA checks, not worker metadata.
    independently_checked: bool=False

def publish_gate(req:GenerationRequest,proof:QualityEvidence)->tuple[bool,tuple[str,...]]:
    reasons=[]
    if not proof.independently_checked:reasons.append("independent_quality_check_missing")
    if not isinstance(proof.duration_seconds,(int,float)) or not math.isfinite(proof.duration_seconds) or abs(proof.duration_seconds-req.duration_seconds)>0.4:
        reasons.append("wrong_duration")
    if not proof.visual_motion_verified:reasons.append("no_verified_real_motion")
    if not proof.story_adherence_verified:reasons.append("prompt_not_verified")
    if req.needs_audio and not (proof.audio_stream_verified and proof.audible_audio_verified):reasons.append("audio_missing_or_silent")
    if req.needs_two_people and not proof.two_identity_matches_verified:reasons.append("two_person_identity_mismatch")
    if req.needs_singing and not proof.singing_verified:reasons.append("singing_unverified")
    if req.needs_lipsync and not proof.lipsync_verified:reasons.append("lipsync_unverified")
    return (not reasons,tuple(reasons))
