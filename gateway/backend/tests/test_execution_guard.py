"""Negative-path regression tests: fail closed before provider/API/advertising spend."""
from dataclasses import replace
from decimal import Decimal as D
import pytest
import execution_guard as g

def req(**overrides):
    base=dict(seconds=8,distinct_people=2,needs_audio=True,needs_lip_sync=True,
      requires_consistent_people=True,quality_preset='premium',
      max_authorized_spend_usd=D('0'),explicit_image_consent=True,
      commercial_use=False)
    return g.VideoRequest(**(base|overrides))

def provider(**overrides):
    base=dict(name='approved_hypothetical_engine',max_independent_people=2,
      supported_durations=(4,8,10,12),can_sync_requested_language=True,
      supports_audio=True,keyframe_continuity=True,has_live_capacity=True,
      account_price_verified=True,unit_cost_usd=D('0'),
      is_active=True,terms_permit_requested_use=True)
    return g.ProviderProof(**(base|overrides))

def segment(**overrides):
    base=dict(index=0,start_ms=0,end_ms=8000,measured_ms=8000,
      container_valid=True,audio_present=True,
      source_identities_reviewed=True,lips_and_language_reviewed=True,
      continuity_with_previous_reviewed=True,signed_render_receipt=True)
    return g.SegmentResult(**(base|overrides))

def test_staged_provider_not_assumed_current_real_available():
    disabled=provider(is_active=False,has_live_capacity=False)
    assert not g.choose_eligible(req(),[disabled])

@pytest.mark.parametrize('change,blocker',[
    ({'is_active':False},'provider_disabled'),
    ({'has_live_capacity':False},'capacity_not_verified'),
    ({'max_independent_people':1},'independent_person_reference_unsupported'),
    ({'supported_durations':(4,6)},'requested_duration_unsupported'),
    ({'supports_audio':False},'audio_unsupported'),
    ({'can_sync_requested_language':False},'lip_sync_language_unverified'),
    ({'keyframe_continuity':False},'identity_continuity_unverified'),
    ({'account_price_verified':False},'provider_price_unverified'),
    ({'unit_cost_usd':None},'provider_price_unverified'),
    ({'unit_cost_usd':D('.01')},'owner_spend_limit_exceeded'),
])
def test_provider_failure_modes_block_generation(change,blocker):
    assert blocker in g.assess_provider(req(),provider(**change))

def test_no_personal_image_consent_or_commercial_rights():
    assert 'reference_image_consent_missing' in g.assess_provider(
        req(explicit_image_consent=False),provider())
    assert 'commercial_use_unverified' in g.assess_provider(
        req(commercial_use=True),provider(terms_permit_requested_use=False))

def test_lower_price_approved_engines_rank_before_costlier_engine():
    request=req(max_authorized_spend_usd=D('5'),distinct_people=0,
        needs_lip_sync=False,requires_consistent_people=False)
    prices=[provider(name='z',unit_cost_usd=D('.4')),
            provider(name='a',unit_cost_usd=D('0'))]
    assert [x.name for x in g.choose_eligible(request,prices)]==['a','z']

def test_explicit_rejection_only_allows_fallback():
    assert g.may_resubmit(g.SubmissionOutcome.REJECTED_BEFORE_ACCEPTANCE,provider_task_id=None)
    assert not g.may_resubmit(g.SubmissionOutcome.ACCEPTED_WITH_ID,provider_task_id='task')
    assert not g.may_resubmit(g.SubmissionOutcome.UNKNOWN_AFTER_SUBMISSION,provider_task_id=None)
    assert not g.may_resubmit(g.SubmissionOutcome.REJECTED_BEFORE_ACCEPTANCE,provider_task_id='task')

def test_good_clip_may_publish():
    report=g.assess_output(req(),[segment()])
    assert report.verdict is g.PublishVerdict.ACCEPT
    assert report.verified_duration_ms==8000

@pytest.mark.parametrize('change,blocker',[
    ({'measured_ms':3042},'scene_duration_mismatch'),
    ({'container_valid':False},'invalid_video_file'),
    ({'audio_present':False},'missing_audio'),
    ({'signed_render_receipt':False},'render_receipt_missing'),
    ({'end_ms':3000,'measured_ms':3000},'total_duration_mismatch'),
])
def test_invalid_or_short_clips_never_presented_as_complete(change,blocker):
    report=g.assess_output(req(),[segment(**change)])
    assert report.verdict is g.PublishVerdict.REJECT
    assert blocker in report.blockers

def test_unreviewed_identity_or_bukhori_lips_stays_draft():
    identity=g.assess_output(req(),[segment(source_identities_reviewed=False)])
    assert identity.verdict is g.PublishVerdict.NEEDS_REVIEW
    assert 'character_identity_unverified' in identity.warnings
    language=g.assess_output(req(),[segment(lips_and_language_reviewed=False)])
    assert language.verdict is g.PublishVerdict.NEEDS_REVIEW
    assert 'lip_sync_or_language_unverified' in language.warnings

def test_multiscene_gap_identity_or_duration():
    first=segment(end_ms=4000,measured_ms=4000)
    second=segment(index=1,start_ms=4500,end_ms=8000,measured_ms=3500)
    report=g.assess_output(req(),[first,second])
    assert report.verdict is g.PublishVerdict.REJECT
    assert 'scene_gap_or_overlap' in report.blockers
    joint=g.assess_output(req(),[first,segment(index=1,start_ms=4000,
        end_ms=8000,measured_ms=4000,continuity_with_previous_reviewed=False)])
    assert joint.verdict is g.PublishVerdict.NEEDS_REVIEW
    assert 'cross_scene_continuity_unverified' in joint.warnings

def test_purchases_not_allowed_before_all_gates_complete():
    missing=g.LaunchEvidence(False,False,False,False,False,False,
                             False,False,False,False)
    status=g.launch_gates(missing)
    assert status['can_sell_video_credits'] is False
    assert len(status['missing'])==10
    ready=g.LaunchEvidence(True,True,True,True,True,True,
                           True,True,True,True)
    assert g.launch_gates(ready)['can_sell_video_credits']

def test_invalid_costs_and_durations_rejected():
    with pytest.raises(g.GateRejected):
        g.assess_provider(req(max_authorized_spend_usd=D('NaN')),provider())
    with pytest.raises(g.GateRejected):
        g.assess_provider(req(seconds=True),provider())
    with pytest.raises(g.GateRejected):
        g.assess_provider(req(),provider(unit_cost_usd=D('Infinity')))
