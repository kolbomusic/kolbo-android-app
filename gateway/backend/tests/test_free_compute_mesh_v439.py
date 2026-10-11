"""Offline contract tests; no vendor endpoint, paid compute or user media."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from dataclasses import replace
import pytest
from free_compute_mesh_v439 import (
  GenerationRequest,VerifiedWorker,ExplicitRejection,dispatch,candidates,
  QualityEvidence,publish_gate,MAX_PROOF_AGE_SECONDS)

def req(**updates):
    return replace(GenerationRequest("a"*64,15,2,True,True,True,True,False,True),**updates)

def worker(**updates):
    return replace(VerifiedWorker("donated_gpu_1",True,True,100,True,True,1,0,15,2,True,True,True,True,True,True,False,True),**updates)

def proof(**updates):
    return replace(QualityEvidence(15,True,True,True,True,True,True,True,True),**updates)

def test_multiple_requests_no_application_daily_limit_or_fixed_cooldown():
    attempted=[]
    for i in range(1001):
        decision=dispatch(replace(req(),digest=f"{i:064x}"),[worker()],now=101,
                          submit=lambda w,r: f"job_{r.digest[-8:]}")
        assert decision.state=="worker_accepted"
        assert not decision.user_charged
        attempted.append(decision.worker_task_id)
    assert len(set(attempted))==1001

def test_absent_capacity_waits_without_claiming_generation():
    result=dispatch(req(),[],now=101,submit=lambda w,r:pytest.fail("should not submit"))
    assert result.state=="waiting_for_free_compute"
    assert result.worker_task_id is None
    assert not result.output_verified and not result.free_compute_guaranteed

def test_only_approved_authenticated_and_recent_verified_free_workers_eligible():
    assert candidates(req(),[worker()],now=101)
    changes=[{"zero_user_cost_verified":False},{"operator_approved":False},
      {"authenticated_transport":False},{"synthetic_output_verified":False},
      {"tested_at":100-MAX_PROOF_AGE_SECONDS-1},{"available_slots":0},
      {"supports_independent_two_person_identity":False},
      {"identity_qa_available":False},{"generates_real_motion":False},
      {"supports_singing":False},{"supports_lipsync":False},
      {"can_accept_private_media":False},{"max_video_seconds":14}]
    for change in changes:
        assert not candidates(req(),[worker(**change)],now=101),change

def test_no_media_sent_without_destination_consent():
    assert not candidates(req(user_consented_to_external_worker=False),[worker()],now=101)
    assert candidates(req(reference_count=0,needs_two_people=False),[worker()],now=101)

def test_commercial_use_requires_independent_rights():
    assert not candidates(req(commercial=True),[worker()],now=101)
    assert candidates(req(commercial=True),[worker(supports_commercial_use=True)],now=101)

def test_fallback_only_when_explicitly_rejected_before_task_created():
    names=[]
    def submit(w,r):
        names.append(w.name)
        if w.name=="donated_gpu_1":raise ExplicitRejection("No task created")
        return "job_1234"
    result=dispatch(req(),[worker(),worker(name="donated_gpu_2")],now=101,submit=submit)
    assert names==["donated_gpu_1","donated_gpu_2"]
    assert result.state=="worker_accepted" and result.worker_task_id=="job_1234"

def test_no_second_charge_or_submit_on_ambiguous_error():
    names=[]
    def submit(w,r):
        names.append(w.name)
        raise TimeoutError("Maybe accepted")
    result=dispatch(req(),[worker(),worker(name="donated_gpu_2")],now=101,submit=submit)
    assert result.state=="acceptance_unknown"
    assert names==["donated_gpu_1"] and result.worker_task_id is None
    assert result.credits_spent==0 and not result.output_verified

def test_identity_or_audio_or_semantic_failure_never_published_as_success():
    assert publish_gate(req(),proof())[0]
    for changes in [dict(two_identity_matches_verified=False),
                    dict(audible_audio_verified=False),
                    dict(singing_verified=False),
                    dict(lipsync_verified=False),
                    dict(story_adherence_verified=False),
                    dict(visual_motion_verified=False),
                    dict(independently_checked=False),
                    dict(duration_seconds=3)]:
        good,reasons=publish_gate(req(),proof(**changes))
        assert not good and reasons,changes

def test_invalid_contracts_rejected():
    with pytest.raises(ValueError): req(duration_seconds=16)
    with pytest.raises(ValueError): req(reference_count=3)
    with pytest.raises(ValueError): req(needs_audio=False)
    with pytest.raises(ValueError): worker(name="https://random.website")
    with pytest.raises(ValueError): candidates(req(),[worker(),worker()],now=101)
