"""Staging FastAPI contract tests. No network, no GPU, no real user media."""
import base64, hashlib, io, time, uuid
from pathlib import Path
from PIL import Image
from fastapi.testclient import TestClient
import pytest
import staging_wan_api as api


def photo():
    memory=io.BytesIO()
    Image.new("RGB",(80,80),(90,120,180)).save(memory,format="PNG")
    return {"mime_type":"image/png",
            "data_base64":base64.b64encode(memory.getvalue()).decode()}


def body(**updates):
    d={"prompt":"An origami rocket moves upward",
       "seconds":3.5,"fps":24,"images":[photo()],
       "third_party_transfer_consent":True}
    d.update(updates)
    return d

@pytest.fixture
def config(monkeypatch,tmp_path):
    monkeypatch.setenv("KOLBO_V416_API_TOKEN","test_secret_that_is_longer_than_32_chars")
    monkeypatch.setenv("KOLBO_ALLOW_EXTERNAL_TEST_MEDIA","EXPLICITLY_ENABLED")
    monkeypatch.setattr(api,"ROOT",tmp_path)
    monkeypatch.setattr(api,"enabled",lambda: True)
    with api.LOCK:
        api.JOBS.clear();api.DIGESTS.clear()
    return TestClient(api.app)

def auth():
    return {"Authorization":"Bearer test_secret_that_is_longer_than_32_chars"}

def test_health_never_claims_durability_or_audio(config):
    response=config.get("/v1/health",headers=auth())
    assert response.status_code==200
    health=response.json()
    assert health["supported_image_counts"]==[1]
    assert health["max_seconds"]==5
    assert health["supports_audio"] is False
    assert health["storage_durable"] is False
    assert health["commercial_rights_verified"] is False

def test_anonymous_and_invalid_token_rejected(config):
    assert config.get("/v1/health").status_code==401
    assert config.get("/v1/health",headers={"Authorization":"Bearer wrong"}).status_code==401
    assert config.post("/v1/jobs",json=body()).status_code==401

@pytest.mark.parametrize("payload",[
    {"images":[photo(),photo()]}, {"seconds":8},
    {"third_party_transfer_consent":False}, {"images":[]},
])
def test_unsupported_jobs_do_not_enter_queue(config,monkeypatch,payload):
    calls=[]
    monkeypatch.setattr(api.POOL,"submit",lambda *a,**kw:calls.append(1))
    r=config.post("/v1/jobs",json=body(**payload),headers=auth())
    assert r.status_code==422
    assert calls==[]

def test_identical_submission_is_idempotent_and_queue_is_limited(config,monkeypatch):
    scheduled=[]
    monkeypatch.setattr(api.POOL,"submit",lambda *args,**kw:scheduled.append(1))
    first=config.post("/v1/jobs",json=body(),headers=auth())
    assert first.status_code==202
    job_id=first.json()["job_id"]
    assert len(scheduled)==1
    again=config.post("/v1/jobs",json=body(),headers=auth())
    assert again.status_code==202
    assert again.json()["job_id"]==job_id
    assert len(scheduled)==1
    another=config.post("/v1/jobs",json=body(prompt="Different rocket animation"),
                        headers=auth())
    assert another.status_code==503
    state=config.get("/v1/jobs/"+job_id,headers=auth())
    assert state.status_code==200 and state.json()["state"]=="queued"

def test_download_requires_completion_and_integrity(config,monkeypatch,tmp_path):
    uid=str(uuid.uuid4());target=tmp_path/uid;target.mkdir()
    video=target/"draft.mp4";video.write_bytes(b"example-media-bytes"*250)
    with api.LOCK:
        api.JOBS[uid]={"state":"completed","created_at":time.time(),
                       "digest":"x","detail":"review",
                       "size":video.stat().st_size,
                       "sha256":hashlib.sha256(video.read_bytes()).hexdigest()}
    r=config.get("/v1/jobs/"+uid+"/result",headers=auth())
    assert r.status_code==200 and len(r.content)==video.stat().st_size
    video.write_bytes(b"tampered-media-bytes")
    assert config.get("/v1/jobs/"+uid+"/result",headers=auth()).status_code==409

def test_disabled_without_operator_optin(monkeypatch):
    monkeypatch.setenv("KOLBO_V416_API_TOKEN","test_secret_that_is_longer_than_32_chars")
    monkeypatch.delenv("KOLBO_ALLOW_EXTERNAL_TEST_MEDIA",raising=False)
    assert api.enabled() is False
