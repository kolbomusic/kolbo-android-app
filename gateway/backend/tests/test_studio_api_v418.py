"""Authenticated CPU studio API tests: real FFmpeg export, zero provider calls."""
import base64, hashlib, io, time
from pathlib import Path
from PIL import Image
from fastapi.testclient import TestClient
import pytest
import staging_wan_api as api


def image(color):
    output=io.BytesIO()
    Image.new("RGB",(150,220),color).save(output,format="PNG")
    return {"mime_type":"image/png",
            "data_base64":base64.b64encode(output.getvalue()).decode()}

@pytest.fixture
def client(monkeypatch,tmp_path):
    monkeypatch.setenv("KOLBO_V416_API_TOKEN","safe_local_test_only_1234567890_123456789")
    monkeypatch.setenv("KOLBO_ALLOW_EXTERNAL_TEST_MEDIA","DISABLED")
    monkeypatch.setattr(api,"ROOT",tmp_path)
    with api.LOCK:
        api.JOBS.clear();api.DIGESTS.clear()
    return TestClient(api.app),tmp_path,monkeypatch

def headers():
    return {"Authorization":"Bearer safe_local_test_only_1234567890_123456789"}

def request(**overrides):
    args={"mode":"cpu_photo_motion","seconds":3,"images":[image((180,70,40))],
          "media_rights_attested":True}
    args.update(overrides)
    return args

def test_studio_can_render_without_gpu_provider(client):
    c,root,monkeypatch=client
    monkeypatch.setattr(api.provider,"submit_one",
        lambda **kw: (_ for _ in ()).throw(AssertionError("External provider called")))
    # Run task inline to deterministically test API + FFmpeg together.
    class InlinePool:
        def submit(self,fn,*a,**kw):fn(*a,**kw)
    monkeypatch.setattr(api,"POOL",InlinePool())
    response=c.post("/v1/studio/jobs",json=request(seconds=4,images=[
       image((180,70,40)),image((20,70,180))]),headers=headers())
    assert response.status_code==202,response.text
    ident=response.json()["job_id"]
    status=c.get(f"/v1/jobs/{ident}",headers=headers())
    assert status.status_code==200
    assert status.json()["state"]=="completed"
    assert status.json()["quality"]["mode"]=="cpu_photo_motion"
    assert status.json()["quality"]["ai_video_generated"] is False
    assert status.json()["quality"]["photos"]==2
    assert status.json()["has_audio"] is False
    output=c.get(f"/v1/jobs/{ident}/result",headers=headers())
    assert output.status_code==200
    assert output.content[4:8]==b"ftyp"
    assert len(output.content)>3000
    assert hashlib.sha256(output.content).hexdigest()==status.json()["quality"]["sha256"]
    dedup=c.post("/v1/studio/jobs",json=request(seconds=4,images=[
       image((180,70,40)),image((20,70,180))]),headers=headers())
    assert dedup.json()["deduplicated"] is True
    assert dedup.json()["job_id"]==ident

def test_studio_requires_auth_and_rights(client):
    c,root,monkeypatch=client
    assert c.post("/v1/studio/jobs",json=request()).status_code==401
    fail=c.post("/v1/studio/jobs",
         json=request(media_rights_attested=False),headers=headers())
    assert fail.status_code==422
    assert list(root.iterdir())==[]

def test_no_implicit_ai_fallback_for_singing_requests(client):
    c,root,monkeypatch=client
    # AI endpoint must reject requested singing. The CPU editor is
    # an explicitly different action, never selected automatically.
    result=c.post("/v1/jobs",json={
       "prompt":"The character sings in Bukharian",
       "seconds":4,"images":[image((80,70,40))],
       "third_party_transfer_consent":True},headers=headers())
    assert result.status_code in (422,503)
    assert list(root.iterdir())==[]
