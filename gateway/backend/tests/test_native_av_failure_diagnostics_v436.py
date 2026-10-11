"""Regressions for REAL USER failure: accepted two-source job then generic error.

The Android receives only safe stage-specific error info, never prompt, image
contents, tokens or third-party exception strings; no automatic retries.
"""
from pathlib import Path
from types import SimpleNamespace
import logging
from fastapi.testclient import TestClient
import pytest
import native_av_failure_codes_v436 as failures
import experimental_ltx25_native_av as ltx
import experimental_scene_builder_v433 as stage
import identity_guard_v435 as face
import staging_wan_api as api
from test_two_person_stage_pipeline_v433 import setup,guest,body

@pytest.mark.parametrize("failure,phase,expected",[
    (stage.SceneUnavailable("TOKEN=secret foo"),"shared_stage_generation","stage_provider_unavailable"),
    (stage.SceneUncertain("bad authorization personal photo"),"shared_stage_generation","stage_provider_submission_uncertain"),
    (face.IdentityMismatch("face embeddings are 123..."),"source_face_check","source_faces_not_detected"),
    (face.IdentityMismatch("someone swapped"),"shared_stage_face_check","generated_stage_faces_changed"),
    (face.IdentityMismatch("person replaced"),"video_face_check","video_faces_changed"),
    (ltx.Unavailable("model space failed"),"native_video_audio_generation","video_provider_unavailable"),
    (ltx.UnknownAcceptance("timeout remote request"),"native_video_audio_generation","video_provider_submission_uncertain"),
    (ValueError("Frozen output"),"video_media_quality_check","video_quality_rejected"),
    (RuntimeError("raw path /app/work/people.jpg"),"native_video_audio_generation","internal_processing_error")
])
def test_failures_classified_without_external_exception_text(failure,phase,expected):
    report=failures.classify(failure,phase)
    assert report.error==expected and report.phase==phase
    assert report.retry_automatically is False
    assert "secret" not in report.detail
    assert "embeddings" not in report.detail
    assert "/app/" not in report.detail
    assert "personal photo" not in report.detail

def test_pipelines_return_actionable_stage_and_log_only_safe_codes(
        setup,monkeypatch,caplog):
    client,_,root=setup
    token=guest(client)
    class Inline:
        def submit(self,fn,*a,**kw):return fn(*a,**kw)
    monkeypatch.setattr(api,"POOL",Inline())
    phases=[]
    class OriginalFaceGuard:
        def __init__(self,ref):phases.append("source")
        def verify_still(self,stage):phases.append("stage check")
        def discard(self):phases.append("destroy")
    monkeypatch.setattr(api.identity_gate,"JobIdentityGuard",OriginalFaceGuard)
    def provider_fails(*,source,prompt,destination,consent,commercial):
        phases.append("external stage")
        raise stage.SceneUnavailable("private_user_photo.png Bearer secret1234")
    monkeypatch.setattr(api.stage_builder,"build",provider_fails)
    with caplog.at_level(logging.WARNING,logger="kolbo.native_av"):
        response=client.post("/v1/native-av/jobs",headers=token,json=body())
    assert response.status_code==202,response.text
    job=response.json()["job_id"]
    report=client.get("/v1/jobs/"+job,headers=token).json()
    assert report["state"]=="failed"
    assert report["error"]=="stage_provider_unavailable"
    assert report["phase"]=="shared_stage_generation"
    assert report["diagnostic_id"]==job[:8]
    assert "בניית הבמה" in report["detail"]
    assert phases==["source","external stage","destroy"]
    assert not (root/job/"draft.mp4").exists()
    assert client.get("/v1/jobs/"+job+"/result",headers=token).status_code==409
    assert len(caplog.records)==1
    assert "phase=shared_stage_generation" in caplog.text
    assert "code=stage_provider_unavailable" in caplog.text
    assert "private_user_photo" not in caplog.text
    assert "secret1234" not in caplog.text
    assert "Bearer" not in caplog.text

def test_previous_identity_failure_still_presents_correct_stage(setup,monkeypatch):
    client,_,_=setup
    token=guest(client)
    class Inline:
        def submit(self,fn,*a,**kw):return fn(*a,**kw)
    monkeypatch.setattr(api,"POOL",Inline())
    class BrokenOriginal:
        def __init__(self,ref):
            raise face.IdentityMismatch("raw user full name")
    monkeypatch.setattr(api.identity_gate,"JobIdentityGuard",BrokenOriginal)
    resp=client.post("/v1/native-av/jobs",headers=token,json=body())
    job=resp.json()["job_id"]
    report=client.get("/v1/jobs/"+job,headers=token).json()
    assert report["state"]=="failed"
    assert report["phase"]=="source_face_check"
    assert report["error"]=="source_faces_not_detected"
    assert "raw user" not in str(report)

def test_no_leak_when_video_provider_fails_after_stage_pass(setup,monkeypatch):
    client,_,root=setup
    token=guest(client)
    class Inline:
        def submit(self,fn,*a,**kw):return fn(*a,**kw)
    monkeypatch.setattr(api,"POOL",Inline())
    class Original:
        def __init__(self,ref):pass
        def verify_still(self,stage):
            return SimpleNamespace(as_dict=lambda:{"left_similarity":.88,"right_similarity":.89})
        def discard(self):pass
    monkeypatch.setattr(api.identity_gate,"JobIdentityGuard",Original)
    def scene_ok(*,source,prompt,destination,consent,commercial):
        from PIL import Image
        Image.new("RGB",(512,512),"orange").save(destination)
        return SimpleNamespace(as_dict=lambda:{"generated_new_scene":True})
    monkeypatch.setattr(api.stage_builder,"build",scene_ok)
    monkeypatch.setattr(api.ltx,"generate",lambda **kw:
        (_ for _ in ()).throw(ltx.Unavailable("user-personal-picture.png")))
    r=client.post("/v1/native-av/jobs",headers=token,json=body())
    assert r.status_code==202
    job=r.json()["job_id"]
    status=client.get("/v1/jobs/"+job,headers=token).json()
    assert status["state"]=="failed"
    assert status["phase"]=="native_video_audio_generation"
    assert status["error"]=="video_provider_unavailable"
    assert "user-personal-picture" not in str(status)
    assert not (root/job/"generated-shared-stage.png").exists()
    assert client.get("/v1/jobs/"+job+"/result",headers=token).status_code==409
