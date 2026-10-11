"""Free stage provider overload: detect, cool down, stop wasting photo uploads.

Simulated Gradio failures and synthetic source pictures ONLY.
Never retries public GPU jobs, defeats provider quotas or enables new services.
"""
from __future__ import annotations
from types import SimpleNamespace
from fastapi.testclient import TestClient
import pytest
import stage_provider_cooldown_v438 as cooldown
import staging_wan_api as api
import experimental_scene_builder_v433 as stage
import ai_trial_guards as trials
from test_two_person_stage_pipeline_v433 import setup,guest,body

@pytest.fixture(autouse=True)
def reset_cooldown():
    cooldown.FLUX_COOLDOWN.reset_for_tests()
    yield
    cooldown.FLUX_COOLDOWN.reset_for_tests()

def test_monotonic_observed_cooldown_is_bounded():
    current=[1000.]
    gate=cooldown.ProviderCooldown(seconds=1800,clock=lambda:current[0])
    assert gate.snapshot().blocked is False
    assert gate.record_quota_failure()==1800
    assert gate.snapshot().is_global_provider_status is False
    current[0]+=720
    assert gate.remaining()==1080
    current[0]+=1080
    assert gate.remaining()==0
    assert not gate.snapshot().blocked

def test_duo_preflight_during_observed_quota_does_not_upload_or_reserve(setup):
    client,_,root=setup
    token=guest(client)
    cooldown.FLUX_COOLDOWN.record_quota_failure()
    b={"prompt":"Two characters singing on the same stage",
       "seconds":8,"image_count":1,
       "requires_shared_stage_scene":True,
       "third_party_transfer_consent":True}
    r=client.post("/v1/native-av/plan",headers=token,json=b)
    assert r.status_code==200
    o=r.json()
    assert o["status"]=="blocked"
    assert 1<=o["retry_after_seconds"]<=1800
    assert "recent_public_quota_rejection"==o["cooldown_reason"]
    assert any("GPU" in item for item in o["blockers"])
    assert o["provider_global_availability_verified"] is False
    assert o["credits_spent"]==0
    assert not list(root.iterdir())
    assert trials.COUNTERS=={}
    health=client.get("/v1/health",headers=token).json()
    stage_caps=health["two_person_scene_builder"]
    assert not stage_caps["ready"]
    assert stage_caps["recent_quota_denial_observed"] is True
    assert stage_caps["provider_global_availability_verified"] is False

def test_duo_post_rejected_before_image_disk_and_app_trial_reservation(setup):
    client,monkeypatch,root=setup
    token=guest(client)
    cooldown.FLUX_COOLDOWN.record_quota_failure()
    response=client.post("/v1/native-av/jobs",headers=token,json=body())
    assert response.status_code==503
    assert response.headers.get("retry-after")
    assert trials.COUNTERS=={}
    assert list(root.iterdir())==[]
    assert "ממתינים" in response.json()["detail"]

def test_observed_rejection_is_only_for_two_person_stage_not_text_only(setup):
    client,_,root=setup
    token=guest(client)
    cooldown.FLUX_COOLDOWN.record_quota_failure()
    reply=client.post("/v1/native-av/plan",headers=token,
        json={"prompt":"One cartoon rabbit dances with live music",
              "seconds":3,"image_count":0,
              "requires_shared_stage_scene":False,
              "third_party_transfer_consent":True})
    assert reply.status_code==200
    assert reply.json()["status"]=="eligible_for_attempt"
    assert reply.json()["retry_after_seconds"]==0

def test_accepted_job_rejected_by_public_gpu_activates_cooldown(setup,monkeypatch):
    client,_,root=setup
    token=guest(client)
    class Inline:
        def submit(self,fn,*a,**kw):return fn(*a,**kw)
    monkeypatch.setattr(api,"POOL",Inline())
    class FaceGuard:
        def __init__(self,reference):pass
        def verify_still(self,stage):pytest.fail("FLUX must have failed before face stage QA")
        def discard(self):pass
    monkeypatch.setattr(api.identity_gate,"JobIdentityGuard",FaceGuard)
    seen=[]
    def fail_scene(*,source,prompt,destination,consent,commercial):
        seen.append("one_call")
        raise stage.SceneUnavailable("Quota message is private",
                                   reason="public_gpu_quota_or_busy")
    monkeypatch.setattr(api.stage_builder,"build",fail_scene)
    response=client.post("/v1/native-av/jobs",headers=token,json=body())
    assert response.status_code==202,response.text
    job=response.json()["job_id"]
    status=client.get("/v1/jobs/"+job,headers=token).json()
    assert status["state"]=="failed"
    assert status["error"]=="stage_public_gpu_quota_or_busy"
    assert status["phase"]=="shared_stage_generation"
    assert "Quota message is private" not in str(status)
    assert seen==["one_call"]
    assert cooldown.FLUX_COOLDOWN.snapshot().blocked
    # Previous single attempt consumed the trial counter. While the provider
    # is cooling, further requests must NOT consume additional app credits.
    before=dict(trials.COUNTERS)
    later=client.post("/v1/native-av/jobs",headers=token,json=body(
        prompt="Different reference request while provider overloaded"))
    assert later.status_code==503 and dict(trials.COUNTERS)==before
    assert seen==["one_call"]

def test_nonquota_stage_error_does_not_claim_global_unavailability(setup,monkeypatch):
    c,_,_=setup
    tok=guest(c)
    class Inline:
        def submit(self,fn,*a,**kw):fn(*a,**kw)
    monkeypatch.setattr(api,"POOL",Inline())
    class UnitFace:
        def __init__(self,source):pass
        def discard(self):pass
    monkeypatch.setattr(api.identity_gate,"JobIdentityGuard",UnitFace)
    def unavailable(**kw):
        raise stage.SceneUnavailable("Model returned bad image",
            reason="invalid_provider_image")
    monkeypatch.setattr(api.stage_builder,"build",unavailable)
    resp=c.post("/v1/native-av/jobs",headers=tok,json=body())
    assert resp.status_code==202
    assert c.get("/v1/jobs/"+resp.json()["job_id"],headers=tok).json()["error"]=="stage_returned_invalid_image"
    assert cooldown.FLUX_COOLDOWN.remaining()==0

def test_does_not_overpromise_permanent_free_compute():
    gate=cooldown.ProviderCooldown(seconds=1800)
    o=gate.snapshot()
    assert o.availability_guaranteed is False
    assert o.is_global_provider_status is False
    with pytest.raises(ValueError): cooldown.ProviderCooldown(seconds=30)
    with pytest.raises(ValueError): cooldown.ProviderCooldown(seconds=99999)
