"""Kolbo Video guarded planning, dispatch and release contract. STAGING ONLY.

This module is pure policy: it neither calls a provider nor charges a user.
It is intentionally stricter than a generic generation queue. Unverified
$0 pricing, ambiguous provider acceptance, identity drift and mismatched
durations cannot be converted into success by a fallback/retry loop.
"""
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Literal

class GateRejected(ValueError): pass

class SubmissionOutcome(str,Enum):
    REJECTED_BEFORE_ACCEPTANCE='rejected_before_acceptance'
    ACCEPTED_WITH_ID='accepted_with_id'
    UNKNOWN_AFTER_SUBMISSION='unknown_after_submission'

class PublishVerdict(str,Enum):
    ACCEPT='accept'
    NEEDS_REVIEW='needs_review'
    REJECT='reject'

@dataclass(frozen=True)
class ProviderProof:
    name:str
    max_independent_people:int
    supported_durations:tuple[int,...]
    can_sync_requested_language:bool
    supports_audio:bool
    keyframe_continuity:bool
    has_live_capacity:bool
    account_price_verified:bool
    unit_cost_usd:Decimal|None
    is_active:bool
    terms_permit_requested_use:bool

@dataclass(frozen=True)
class VideoRequest:
    seconds:int
    distinct_people:int
    needs_audio:bool
    needs_lip_sync:bool
    requires_consistent_people:bool
    quality_preset:Literal['draft','standard','premium']
    max_authorized_spend_usd:Decimal
    explicit_image_consent:bool
    commercial_use:bool

@dataclass(frozen=True)
class ProviderChoice:
    name:str
    max_cost_usd:Decimal
    reasons:tuple[str,...]

def _money(value):
    try: n=Decimal(str(value))
    except (TypeError,InvalidOperation,ValueError) as e:
        raise GateRejected('Invalid monetary value') from e
    if not n.is_finite() or n<0: raise GateRejected('Invalid monetary value')
    return n

def assess_provider(request:VideoRequest,proof:ProviderProof)->tuple[str,...]:
    """Empty tuple means eligible. Optimistic assumptions never count as proof."""
    if isinstance(request.seconds,bool) or not 1<=request.seconds<=360:
        raise GateRejected('Invalid duration')
    if request.distinct_people not in (0,1,2):
        raise GateRejected('At most two independent people')
    budget=_money(request.max_authorized_spend_usd)
    reasons=[]
    if not proof.is_active: reasons.append('provider_disabled')
    if not proof.has_live_capacity: reasons.append('capacity_not_verified')
    if request.distinct_people>proof.max_independent_people:
        reasons.append('independent_person_reference_unsupported')
    if request.seconds not in proof.supported_durations:
        reasons.append('requested_duration_unsupported')
    if request.needs_audio and not proof.supports_audio:
        reasons.append('audio_unsupported')
    if request.needs_lip_sync and not proof.can_sync_requested_language:
        reasons.append('lip_sync_language_unverified')
    if request.requires_consistent_people and not proof.keyframe_continuity:
        reasons.append('identity_continuity_unverified')
    if request.distinct_people and not request.explicit_image_consent:
        reasons.append('reference_image_consent_missing')
    if request.commercial_use and not proof.terms_permit_requested_use:
        reasons.append('commercial_use_unverified')
    if not proof.account_price_verified or proof.unit_cost_usd is None:
        reasons.append('provider_price_unverified')
    else:
        charge=_money(proof.unit_cost_usd)*request.seconds
        if charge>budget:reasons.append('owner_spend_limit_exceeded')
    return tuple(reasons)

def choose_eligible(request:VideoRequest,providers:list[ProviderProof])->list[ProviderChoice]:
    """Rank only truly eligible offers; deterministic stable order on equal cost."""
    options=[]
    for proof in providers:
        reasons=assess_provider(request,proof)
        if not reasons:
            cost=_money(proof.unit_cost_usd)*request.seconds
            options.append(ProviderChoice(proof.name,cost,reasons))
    return sorted(options,key=lambda p:(p.max_cost_usd,p.name))

def may_resubmit(outcome:SubmissionOutcome, *,provider_task_id:str|None)->bool:
    """Never switch provider after acceptance or uncertain network timeout."""
    if outcome is not SubmissionOutcome.REJECTED_BEFORE_ACCEPTANCE:
        return False
    return not provider_task_id

@dataclass(frozen=True)
class SegmentResult:
    index:int
    start_ms:int
    end_ms:int
    measured_ms:int
    container_valid:bool
    audio_present:bool
    source_identities_reviewed:bool
    lips_and_language_reviewed:bool
    continuity_with_previous_reviewed:bool
    signed_render_receipt:bool
    # For safety: never store actual face embeddings or source image data here.

@dataclass(frozen=True)
class QualityReport:
    verdict:PublishVerdict
    blockers:tuple[str,...]
    warnings:tuple[str,...]
    verified_duration_ms:int

def assess_output(request:VideoRequest,segments:list[SegmentResult],
                  *,tolerance_ms:int=500)->QualityReport:
    if not segments:return QualityReport(PublishVerdict.REJECT,
        ('no_video_segments',),(),0)
    reasons=[]
    warnings=[]
    expected_total=request.seconds*1000
    previous_end=0
    for expected_index,item in enumerate(sorted(segments,key=lambda x:x.index)):
        if item.index!=expected_index:reasons.append('missing_or_duplicate_scene_index')
        if item.start_ms!=previous_end:reasons.append('scene_gap_or_overlap')
        if item.end_ms<=item.start_ms:reasons.append('bad_scene_range')
        if abs((item.end_ms-item.start_ms)-item.measured_ms)>tolerance_ms:
            reasons.append('scene_duration_mismatch')
        if not item.container_valid:reasons.append('invalid_video_file')
        if not item.signed_render_receipt:reasons.append('render_receipt_missing')
        if request.needs_audio and not item.audio_present:reasons.append('missing_audio')
        if request.requires_consistent_people and not item.source_identities_reviewed:
            warnings.append('character_identity_unverified')
        if request.needs_lip_sync and not item.lips_and_language_reviewed:
            warnings.append('lip_sync_or_language_unverified')
        if expected_index>0 and not item.continuity_with_previous_reviewed:
            warnings.append('cross_scene_continuity_unverified')
        previous_end=item.end_ms
    if abs(previous_end-expected_total)>tolerance_ms:
        reasons.append('total_duration_mismatch')
    if reasons:return QualityReport(PublishVerdict.REJECT,
        tuple(dict.fromkeys(reasons)),tuple(dict.fromkeys(warnings)),previous_end)
    if warnings:return QualityReport(PublishVerdict.NEEDS_REVIEW,
        (),tuple(dict.fromkeys(warnings)),previous_end)
    return QualityReport(PublishVerdict.ACCEPT,(),(),previous_end)

@dataclass(frozen=True)
class LaunchEvidence:
    job_state_is_durable:bool
    provider_task_ids_persisted:bool
    output_storage_is_durable:bool
    provider_live_test_passed:bool
    cost_policy_authorized:bool
    credit_ledger_is_atomic:bool
    payment_verification_live:bool
    fraud_controls_active:bool
    privacy_and_consent_ready:bool
    support_and_refund_process_ready:bool

def launch_gates(e:LaunchEvidence)->dict:
    checks={
        'durable_work_queue':e.job_state_is_durable,
        'accepted_provider_task_ids':e.provider_task_ids_persisted,
        'durable_video_output':e.output_storage_is_durable,
        'end_to_end_video_verified':e.provider_live_test_passed,
        'account_billing_verified':e.cost_policy_authorized,
        'atomic_credits':e.credit_ledger_is_atomic,
        'real_payment_verification':e.payment_verification_live,
        'fraud_protection':e.fraud_controls_active,
        'image_consent_and_privacy':e.privacy_and_consent_ready,
        'customer_support_and_refunds':e.support_and_refund_process_ready,
    }
    missing=tuple(k for k,passed in checks.items() if not passed)
    return {'can_sell_video_credits':not missing,
            'missing':missing,'all':checks}
