"""v419 zero-input connection proof: guest does not inherit private AI rights."""
from __future__ import annotations
import base64
import hashlib
import io
import threading
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient
from PIL import Image
import pytest
import guest_sessions as guest
import staging_wan_api as api


def picture(rgb=(45,70,90)):
    out=io.BytesIO()
    Image.new("RGB",(120,100),rgb).save(out,format="PNG")
    return {"mime_type":"image/png","data_base64":base64.b64encode(out.getvalue()).decode()}


@pytest.fixture
def state(monkeypatch,tmp_path):
    monkeypatch.setenv("KOLBO_V416_API_TOKEN","master_secret_test_only_exceeding_32_chars")
    monkeypatch.setenv("KOLBO_GUEST_CPU_BOOTSTRAP","EXPLICITLY_ENABLED")
    monkeypatch.setenv("KOLBO_GUEST_CPU_SESSION_SECRET","only_test_secret_never_deploy_1234567890_1234567890123456")
    monkeypatch.setenv("KOLBO_ALLOW_EXTERNAL_TEST_MEDIA","DISABLED")
    monkeypatch.setattr(api,"ROOT",tmp_path)
    with guest.LOCK:
        guest.COUNTERS.clear()
    with api.LOCK:
        api.JOBS.clear()
        api.DIGESTS.clear()
    return TestClient(api.app),monkeypatch,tmp_path


def enroll(client,install="a"*32):
    result=client.post("/v1/guest/bootstrap",json={"install_id":install})
    assert result.status_code==200,result.text
    assert result.json()["ai_generation"] is False
    return "Bearer "+result.json()["token"]


def req(rgb=(45,70,90),seconds=2):
    return {"mode":"cpu_photo_motion","seconds":seconds,"images":[picture(rgb)],
            "media_rights_attested":True}


def test_anonymous_bootstrap_disabled_by_default(state):
    c,m,_=state
    m.setenv("KOLBO_GUEST_CPU_BOOTSTRAP","DISABLED")
    assert c.post("/v1/guest/bootstrap",json={"install_id":"a"*32}).status_code==503


def test_bootstrap_secret_required(state):
    c,m,_=state
    m.setenv("KOLBO_GUEST_CPU_SESSION_SECRET","short")
    assert c.post("/v1/guest/bootstrap",json={"install_id":"a"*32}).status_code==503


def test_guest_scoped_cpu_only_and_job_data_isolated(state):
    c,m,root=state
    one=enroll(c,"a"*32)
    two=enroll(c,"b"*32)
    assert c.get("/v1/health",headers={"Authorization":one}).status_code==200
    assert c.get("/v1/health",headers={"Authorization":one}).json()["status"]=="not_ready"
    assert c.get("/v1/health",headers={"Authorization":one}).json()["cpu_photo_studio"]["ai_video"] is False
    plan=c.post("/v1/creative/plan",json={"prompt":"singing and dancing","seconds":3,
                    "image_count":1},headers={"Authorization":one})
    assert plan.status_code==200
    assert "requested_audio_unavailable" in plan.json()["blockers"]
    assert plan.json()["status"]=="blocked"
    assert c.post("/v1/jobs",json={"prompt":"A bird flies over trees","seconds":3,
                    "images":[picture()],"third_party_transfer_consent":True},
                    headers={"Authorization":one}).status_code==401
    class InlinePool:
        def submit(self,fn,*args,**kw):fn(*args,**kw)
    m.setattr(api,"POOL",InlinePool())
    job=c.post("/v1/studio/jobs",json=req(),headers={"Authorization":one})
    assert job.status_code==202,job.text
    identifier=job.json()["job_id"]
    assert c.get("/v1/jobs/"+identifier,headers={"Authorization":one}).status_code==200
    assert c.get("/v1/jobs/"+identifier,headers={"Authorization":two}).status_code==404
    assert c.get("/v1/jobs/"+identifier+"/result",headers={"Authorization":two}).status_code==404
    result=c.get("/v1/jobs/"+identifier+"/result",headers={"Authorization":one})
    assert result.status_code==200
    assert result.content[4:8]==b"ftyp"
    # User two submitting exactly same photo must never return user one's ID.
    j2=c.post("/v1/studio/jobs",json=req(),headers={"Authorization":two})
    assert j2.status_code==202
    assert j2.json()["job_id"]!=identifier


def test_tampered_session_rejected(state):
    c,_,_=state
    good=enroll(c)
    altered=good[:-4]+"xxxx"
    assert c.get("/v1/health",headers={"Authorization":altered}).status_code==401


def test_guest_hours_expiration_and_daily_caps(state):
    c,_,_=state
    one=enroll(c)
    for n in range(4):
        assert c.post("/v1/guest/bootstrap",json={"install_id":"a"*32}).status_code==200
    assert c.post("/v1/guest/bootstrap",json={"install_id":"a"*32}).status_code==429
    token=one[len("Bearer "):]
    with pytest.raises(Exception):
        guest.verify(one,now=10**11)
    owner=guest.verify(one).owner
    guest.reserve_seconds(owner,12)
    guest.reserve_seconds(owner,12)
    with pytest.raises(Exception):
        guest.reserve_seconds(owner,2)


def test_bootstrap_never_contains_master_credential(state):
    c,_,_=state
    token=enroll(c)
    assert "master_secret_test_only_exceeding_32_chars" not in token
    assert "KOLBO_V416_API_TOKEN" not in token
