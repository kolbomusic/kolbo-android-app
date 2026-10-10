"""Staged authenticated planning API: zero provider submissions, zero credit movement.

The planning endpoint receives only required capability metadata, not media or
prompts. All provider proofs are SERVER-SIDE, and conservatively unverified.
Activating it does not activate real multi-provider rendering or billing.
"""
from __future__ import annotations
import os
from decimal import Decimal
from fastapi import APIRouter,HTTPException
from pydantic import BaseModel,Field
import execution_guard as guard
import provider_router

router=APIRouter()

class PlanRequest(BaseModel):
    seconds:int=Field(ge=1,le=60)
    independent_people:int=Field(ge=0,le=2)
    audio:bool=True
    lip_sync:bool=False
    consistent_people:bool=True
    source_image_consent:bool=False
    commercial_use:bool=False

def server_owned_proofs():
    """No supplier status, price, rights or quality guarantees are fabricated."""
    # Even an accepted read-only /v1/models credential probe cannot prove
    # live GPU queue availability or account-specific price.
    return [guard.ProviderProof(
        name='agnes_video_2_5_flash',
        max_independent_people=2,
        supported_durations=tuple(range(4,13)),
        can_sync_requested_language=False,
        supports_audio=False,
        keyframe_continuity=False,
        has_live_capacity=False,
        account_price_verified=False,
        unit_cost_usd=None,
        is_active=True,
        terms_permit_requested_use=False
    )]

def plan(body:PlanRequest, *,enabled:bool=False)->dict:
    if not enabled:
        raise HTTPException(404,'Orchestrator preview not enabled')
    request=guard.VideoRequest(
        seconds=body.seconds,
        distinct_people=body.independent_people,
        needs_audio=body.audio,
        needs_lip_sync=body.lip_sync,
        requires_consistent_people=body.consistent_people,
        quality_preset='draft',
        max_authorized_spend_usd=Decimal('0'),
        explicit_image_consent=body.source_image_consent,
        commercial_use=body.commercial_use
    )
    checks={}
    for provider in server_owned_proofs():
        blockers=guard.assess_provider(request,provider)
        checks[provider.name]={
          'ready':len(blockers)==0,
          'reasons':list(blockers),
          'cost_verified':provider.account_price_verified,
          'capacity_verified':provider.has_live_capacity,
        }
    approved=guard.choose_eligible(request,server_owned_proofs())
    return {
        'kind':'read_only_preflight',
        'can_submit':False,
        'live_provider_count':len(approved),
        'invoice_amount_usd':None,
        'price_verified':False,
        'work_persisted':False,
        'providers':checks,
        'message':'This preview does not start a video, reserve credits or promise a zero-price API.'
    }
