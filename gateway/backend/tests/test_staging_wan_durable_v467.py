"""Integration of the free-GPU journal with the existing experimental FastAPI.
No real provider requests, private photos, or paid endpoints.
"""
import base64
import hashlib
import io
from pathlib import Path
from types import SimpleNamespace
import pytest
from PIL import Image
from fastapi.testclient import TestClient

import free_gpu_journal as journal_module
import staging_wan_api as api
import ai_trial_guards as trials
import guest_sessions as guests

def sample_image():
    mem=io.BytesIO()
    Image.new("RGB",(96,96),(80,120,215)).save(mem,format="PNG")
    return {"mime_type":"image/png","data_base64":base64.b64encode(mem.getvalue()).decode()}

def request():
    return {"prompt":"A yellow paper boat moves slowly across the water",
            "seconds":2.0, "images":[sample_image()],
            "third_party_transfer_consent":True}

@pytest.fixture
def env(monkeypatch,tmp_path):
    private=tmp_path/"permanent"
    private.mkdir(mode=0o700)
    monkeypatch.setenv("KOLBO_FREE_GPU_JOURNAL_PATH",str(private/"jobs.sqlite3"))
    monkeypatch.setenv("KOLBO_FREE_GPU_PERSISTENT_VOLUME_VERIFIED","EXPLICITLY_ENABLED")
    monkeypatch.setenv("KOLBO_GUEST_CPU_BOOTSTRAP","EXPLICITLY_ENABLED")
    monkeypatch.setenv("KOLBO_GUEST_CPU_SESSION_SECRET",
                      "test_only_very_long_shared_secret_01234567890123456789")
    monkeypatch.setenv("KOLBO_GUEST_AI_TRIAL","EXPLICITLY_ENABLED")
    monkeypatch.setenv("KOLBO_ALLOW_EXTERNAL_TEST_MEDIA","EXPLICITLY_ENABLED")
    monkeypatch.setenv("KOLBO_V416_API_TOKEN","test_only_master_token_longer_than_32chars")
    monkeypatch.setattr(api,"ROOT",private)
    monkeypatch.setattr(api,"enabled",lambda:True)
    with api.LOCK:api.JOBS.clear();api.DIGESTS.clear()
    with trials.LOCK:trials.COUNTERS.clear()
    with guests.LOCK:guests.COUNTERS.clear()
    client=TestClient(api.app)
    bootstrap=client.post("/v1/guest/bootstrap",json={"install_id":"a"*32})
    assert bootstrap.status_code==200
    token={"Authorization":"Bearer "+bootstrap.json()["token"]}
    return client,token,private,monkeypatch

def test_duplicate_after_restart_never_dispatches_again(env):
    client,token,private,monkeypatch=env
    submitted=[]
    monkeypatch.setattr(api.POOL,"submit",lambda *args,**kw:submitted.append(1))
    first=client.post("/v1/ai/jobs",headers=token,json=request())
    assert first.status_code==202,first.text
    data=first.json()
    assert data["journal_enabled"] is True
    assert len(submitted)==1
    with api.LOCK:api.JOBS.clear();api.DIGESTS.clear()
    duplicate=client.post("/v1/ai/jobs",headers=token,json=request())
    assert duplicate.status_code==202,duplicate.text
    assert duplicate.json()["deduplicated"] is True
    assert duplicate.json()["job_id"]==data["job_id"]
    assert len(submitted)==1
    assert client.get("/v1/jobs/"+data["job_id"],headers=token).status_code==200
    assert client.get("/v1/jobs/"+data["job_id"]+"/result",headers=token).status_code==409

def test_after_remote_submit_crash_reports_unknown_and_does_not_retry(env):
    client,token,private,monkeypatch=env
    submitted=[]
    monkeypatch.setattr(api.POOL,"submit",lambda *args,**kw:submitted.append(1))
    first=client.post("/v1/ai/jobs",headers=token,json=request())
    job_id=first.json()["job_id"]
    owner=guests.verify(token["Authorization"]).owner
    journal=journal_module.FreeGpuJournal(private/"jobs.sqlite3")
    journal.change(job_id,owner,"submitting",provider="wan_fast")
    with api.LOCK:api.JOBS.clear();api.DIGESTS.clear()
    state=client.get("/v1/jobs/"+job_id,headers=token)
    assert state.status_code==200 and state.json()["state"]=="acceptance_unknown"
    again=client.post("/v1/ai/jobs",headers=token,json=request())
    assert again.json()["deduplicated"]
    assert again.json()["needs_operator_reconciliation"]
    assert len(submitted)==1

def test_no_persistence_operator_confirmation_means_no_upload(env):
    client,token,private,monkeypatch=env
    monkeypatch.delenv("KOLBO_FREE_GPU_PERSISTENT_VOLUME_VERIFIED")
    submitted=[]
    monkeypatch.setattr(api.POOL,"submit",lambda *args,**kw:submitted.append(1))
    result=client.post("/v1/ai/jobs",headers=token,json=request())
    assert result.status_code==503
    assert submitted==[]

def test_provider_output_digest_persisted_then_recovered(env):
    client,token,private,monkeypatch=env
    class Inline:
        def submit(self,fn,*args,**kwargs):
            fn(*args,**kwargs)
    monkeypatch.setattr(api,"POOL",Inline())
    data=b"fixture_mp4_nongenerative_video_bytes"
    checksum=hashlib.sha256(data).hexdigest()
    def provider(**kwargs):
        Path(kwargs["destination"]).write_bytes(data)
        return SimpleNamespace(bytes=len(data),sha256=checksum,audio=False)
    monkeypatch.setattr(api.provider,"submit_one",provider)
    monkeypatch.setattr(api.visual_quality,"inspect_mp4",lambda *a,**k:
        SimpleNamespace(pixel_change_fraction=.2,as_dict=lambda:{"pixel_change_fraction":.2}))
    monkeypatch.setattr(api.audio_evidence,"inspect_mp4",lambda *a,**k:
        SimpleNamespace(as_dict=lambda:{"has_audio_stream":False}))
    result=client.post("/v1/ai/jobs",headers=token,json=request())
    assert result.status_code==202,result.text
    jid=result.json()["job_id"]
    with api.LOCK:api.JOBS.clear();api.DIGESTS.clear()
    status=client.get("/v1/jobs/"+jid,headers=token)
    assert status.status_code==200,status.text
    assert status.json()["state"]=="completed"
    media=client.get("/v1/jobs/"+jid+"/result",headers=token)
    assert media.status_code==200 and media.content==data
    # Test is only about storage/transport, NOT actual generated media.
