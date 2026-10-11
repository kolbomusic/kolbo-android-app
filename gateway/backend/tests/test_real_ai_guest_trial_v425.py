"""v425: no photo slideshow disguised as AI, only actual 1-image video model.

All external inference is stubbed during pytest. Only the separate, explicit
synthetic CI proof makes one real public ZeroGPU call.
"""
import base64,hashlib,io,os,time
from pathlib import Path
from types import SimpleNamespace
from PIL import Image
from fastapi.testclient import TestClient
import pytest

import ai_trial_guards as trial
import staging_wan_api as api
import guest_sessions as guests


def photo():
    memory=io.BytesIO()
    Image.new("RGB",(96,96),(75,130,220)).save(memory,format="PNG")
    return {"mime_type":"image/png","data_base64":base64.b64encode(memory.getvalue()).decode()}


@pytest.fixture
def setup(monkeypatch,tmp_path):
    monkeypatch.setenv("KOLBO_V416_API_TOKEN","private_master_for_test_987654321_987654321")
    monkeypatch.setenv("KOLBO_GUEST_CPU_BOOTSTRAP","EXPLICITLY_ENABLED")
    monkeypatch.setenv("KOLBO_GUEST_CPU_SESSION_SECRET","some_min_48_character_test_secret_for_guest_clients_0123456789")
    monkeypatch.setenv("KOLBO_GUEST_AI_TRIAL","EXPLICITLY_ENABLED")
    monkeypatch.setenv("KOLBO_ALLOW_EXTERNAL_TEST_MEDIA","EXPLICITLY_ENABLED")
    monkeypatch.setattr(api,"ROOT",tmp_path)
    monkeypatch.setattr(api,"enabled",lambda:True)
    with api.LOCK:
        api.JOBS.clear();api.DIGESTS.clear()
    with guests.LOCK:
        guests.COUNTERS.clear()
    with trial.LOCK:
        trial.COUNTERS.clear()
    return TestClient(api.app),monkeypatch,tmp_path


def guest(client,key):
    r=client.post("/v1/guest/bootstrap",json={"install_id":key*32})
    assert r.status_code==200,r.text
    return {"Authorization":"Bearer "+r.json()["token"]}


def request(**updates):
    x={"prompt":"A cartoon robot waves both arms and walks forward",
        "seconds":3.5,"images":[photo()],
        "third_party_transfer_consent":True}
    x.update(updates)
    return x


def test_disabled_by_default_even_when_guest_bootstrap_available(setup):
    client,monkeypatch,_=setup
    monkeypatch.setenv("KOLBO_GUEST_AI_TRIAL","DISABLED")
    token=guest(client,"a")
    assert client.get("/v1/health",headers=token).json()["experimental_ai_video"]["ready"] is False
    with api.LOCK:assert not api.JOBS
    denied=client.post("/v1/ai/jobs",headers=token,json=request())
    assert denied.status_code==422


@pytest.mark.parametrize("bad,expected",[
    ({"seconds":10},"duration_unsupported"),
    ({"images":[photo(),photo()]},"single_reference_only"),
    ({"prompt":"הוא שר בבוכרית על הבמה מול עשרת אלפים איש"},"requested_audio_unavailable"),
    ({"prompt":"she speaks English to the audience"},"requested_audio_unavailable"),
    ({"prompt":"Two people dance together on stage"},"multiple_subject_identity_unavailable"),
    ({"third_party_transfer_consent":False},"external_image_transfer_consent_missing"),
    ({"commercial_use":True},"commercial_rights_not_verified"),
])
def test_unsupported_video_never_uploads_or_spends_free_gpu(setup,bad,expected):
    client,monkeypatch,root=setup
    token=guest(client,"a")
    invoked=[]
    monkeypatch.setattr(api.POOL,"submit",lambda *a,**kw:invoked.append(1))
    response=client.post("/v1/ai/jobs",json=request(**bad),headers=token)
    assert response.status_code==422,response.text
    assert expected in response.json()["detail"]["blockers"]
    assert not invoked and not list(root.iterdir())
    assert not trial.COUNTERS


def test_genuine_trial_is_owner_scoped_deduped_and_bounded(setup):
    client,monkeypatch,_=setup
    one=guest(client,"a");two=guest(client,"b")
    invoked=[]
    monkeypatch.setattr(api.POOL,"submit",lambda *a,**kw:invoked.append(1))
    sent=client.post("/v1/ai/jobs",json=request(),headers=one)
    assert sent.status_code==202,sent.text
    jobid=sent.json()["job_id"]
    assert len(invoked)==1
    again=client.post("/v1/ai/jobs",json=request(),headers=one)
    assert again.status_code==202
    assert again.json()["job_id"]==jobid and len(invoked)==1
    assert client.get("/v1/jobs/"+jobid,headers=one).status_code==200
    assert client.get("/v1/jobs/"+jobid,headers=two).status_code==404
    assert client.get("/v1/jobs/"+jobid+"/result",headers=two).status_code==404
    assert client.post("/v1/jobs",json=request(),headers=one).status_code==401
    assert client.post("/v1/ai/jobs",json=request(
        prompt="A robot bends over dramatically"),headers=one).status_code==503


def test_daily_limit_is_server_enforced_no_payment(monkeypatch):
    monkeypatch.setenv("KOLBO_GUEST_AI_TRIAL","EXPLICITLY_ENABLED")
    monkeypatch.setenv("KOLBO_ALLOW_EXTERNAL_TEST_MEDIA","EXPLICITLY_ENABLED")
    with trial.LOCK:trial.COUNTERS.clear()
    trial.reserve("a"*64,now=2000000000)
    with pytest.raises(Exception) as e:
        trial.reserve("a"*64,now=2000000000)
    assert e.value.status_code==429
    trial.reserve("b"*64,now=2000000000)
    with pytest.raises(Exception) as e:
        trial.reserve("c"*64,now=2000000000)
    assert e.value.status_code==429


def test_frozen_generated_mp4_is_rejected(setup):
    client,monkeypatch,root=setup
    token=guest(client,"a")
    class Inline:
        def submit(self,fn,*args,**kw):fn(*args,**kw)
    monkeypatch.setattr(api,"POOL",Inline())
    def fake_provider(**kwargs):
        Path(kwargs["destination"]).write_bytes(b"non-real-unit-video")
        return SimpleNamespace(bytes=19,sha256=hashlib.sha256(b"non-real-unit-video").hexdigest(),audio=False)
    monkeypatch.setattr(api.provider,"submit_one",fake_provider)
    monkeypatch.setattr(api.visual_quality,"inspect_mp4",lambda *args,**kw:
        SimpleNamespace(pixel_change_fraction=0.0,as_dict=lambda:{"pixel_change_fraction":0.0}))
    monkeypatch.setattr(api.audio_evidence,"inspect_mp4",lambda *args,**kw:
        SimpleNamespace(as_dict=lambda:{"has_audio_stream":False}))
    response=client.post("/v1/ai/jobs",json=request(),headers=token)
    assert response.status_code==202
    state=client.get("/v1/jobs/"+response.json()["job_id"],headers=token).json()
    assert state["state"]=="failed"
    assert client.get("/v1/jobs/"+response.json()["job_id"]+"/result",headers=token).status_code==409


def test_guest_preflight_uses_no_media_upload_and_reports_constraints(setup):
    client,monkeypatch,root=setup
    token=guest(client,"a")
    response=client.post("/v1/creative/plan",json={
        "prompt":"The cartoon person waves happily at the camera",
        "seconds":3.5,"image_count":1,"third_party_transfer_consent":True},headers=token)
    assert response.status_code==200
    assert response.json()["status"]=="draft_possible"
    assert list(root.iterdir())==[]
    denied=client.post("/v1/creative/plan",json={
        "prompt":"Both cartoon characters sing on stage",
        "seconds":10,"image_count":2},headers=token)
    assert denied.status_code==200
    assert "duration_unsupported" in denied.json()["blockers"]
    assert "requested_audio_unavailable" in denied.json()["blockers"]
