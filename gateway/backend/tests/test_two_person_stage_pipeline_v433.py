"""Two-stage stage-builder then native video/audio pipeline; no private users in tests."""
from pathlib import Path
from types import SimpleNamespace
import base64,hashlib,io,subprocess
from fastapi.testclient import TestClient
import pytest
from PIL import Image
import staging_wan_api as api
import guest_sessions as guests
import ai_trial_guards as trials
import experimental_scene_builder_v433 as stage
import experimental_ltx25_native_av as ltx
import audio_evidence,visual_quality

@pytest.fixture
def setup(monkeypatch,tmp_path):
    for key,val in {
        "KOLBO_V416_API_TOKEN":"only_unit_master_secret_with_length_1234567890",
        "KOLBO_GUEST_CPU_BOOTSTRAP":"EXPLICITLY_ENABLED",
        "KOLBO_GUEST_CPU_SESSION_SECRET":"only_unit_guest_secret_more_than_48_characters_0123456789",
        "KOLBO_ALLOW_EXTERNAL_TEST_MEDIA":"EXPLICITLY_ENABLED",
        "KOLBO_GUEST_AI_TRIAL":"EXPLICITLY_ENABLED",
        "KOLBO_NATIVE_LTX25_TRIAL":"EXPLICITLY_ENABLED",
        "KOLBO_SCENE_BUILDER_V433":"EXPLICITLY_ENABLED"
    }.items():monkeypatch.setenv(key,val)
    monkeypatch.setattr(api,"ROOT",tmp_path)
    monkeypatch.setattr(api,"enabled",lambda:True)
    with api.LOCK:
        api.JOBS.clear();api.DIGESTS.clear()
    with guests.LOCK:guests.COUNTERS.clear()
    with trials.LOCK:trials.COUNTERS.clear()
    return TestClient(api.app),monkeypatch,tmp_path

def guest(client):
    r=client.post("/v1/guest/bootstrap",json={"install_id":"a"*32})
    assert r.status_code==200,r.text
    return {"Authorization":"Bearer "+r.json()["token"]}

def photo():
    buf=io.BytesIO()
    Image.new("RGB",(128,128),(70,110,170)).save(buf,"PNG")
    return {"mime_type":"image/png","data_base64":base64.b64encode(buf.getvalue()).decode()}

def body(**override):
    item={"prompt":"Two people singing together on a real open-air stage at Caesarea",
          "seconds":3.0,"images":[photo()],
          "third_party_transfer_consent":True,
          "requires_shared_stage_scene":True}
    item.update(override)
    return item

def make_video(path:Path,duration:int=3,split=False):
    # This unit clip is moving in both halves and contains actual audible AAC.
    # It is NOT intended to represent real generated human acting.
    subprocess.run(["ffmpeg","-nostdin","-v","error","-y",
        "-f","lavfi","-i",f"testsrc2=s=320x320:r=16:d={duration}",
        "-f","lavfi","-i",f"sine=f=400:sample_rate=16000:duration={duration}",
        "-map","0:v","-map","1:a","-c:v","libx264","-preset","ultrafast",
        "-c:a","aac","-shortest",str(path)],check=True,timeout=60)

def test_stage_disabled_does_not_spend_quota_or_upload(setup):
    client,monkeypatch,root=setup
    monkeypatch.setenv("KOLBO_SCENE_BUILDER_V433","DISABLED")
    token=guest(client)
    preview=client.post("/v1/native-av/plan",json=body(),headers=token)
    assert preview.status_code==200
    assert "two_person_scene_builder_unavailable" in preview.json()["blockers"]
    result=client.post("/v1/native-av/jobs",json=body(),headers=token)
    assert result.status_code==503
    assert trials.COUNTERS=={}
    assert not list(root.iterdir())

def test_non_duo_single_model_remains_supported(setup):
    c,_,_=setup
    token=guest(c)
    resp=c.post("/v1/native-av/plan",headers=token,json=body(
        requires_shared_stage_scene=False))
    assert resp.status_code==200 and resp.json()["status"]=="eligible_for_attempt"

def test_duo_needs_one_combined_source_reference(setup):
    c,_,root=setup
    token=guest(c)
    resp=c.post("/v1/native-av/jobs",headers=token,json=body(images=[]))
    assert resp.status_code==422
    assert trials.COUNTERS=={} and not list(root.iterdir())

def test_scene_builder_receipt_has_no_unverified_identity_claim(setup,tmp_path):
    _,_,root=setup
    incoming=root/"in.png";Image.new("RGB",(512,512),"blue").save(incoming)
    class FakeClient:
        def __init__(self,*a,**k):pass
        def submit(self,*args,**kwargs):
            assert args[0]==str(incoming)
            assert kwargs["api_name"]=="/infer"
            class Job:
                def done(self):return True
                def result(self):return (str(scene_file),42,None)
            return Job()
    scene_file=root/"demo-scene.png"
    Image.new("RGB",(640,640),"orange").save(scene_file)
    result=stage.build(source=incoming,prompt="Two singers on a crowded amphitheater",
                       destination=root/"rendered.png",consent=True,
                       client_factory=FakeClient,handle_file_fn=lambda x:x)
    assert result.generated_new_scene and result.pixel_difference_mean>18
    assert result.faces_preserved_verified is False
    assert result.crowd_count_verified is False

def test_one_scene_generation_before_video_and_sound(setup):
    client,monkeypatch,root=setup
    token=guest(client)
    class Inline:
        def submit(self,fn,*args,**kwargs):return fn(*args,**kwargs)
    monkeypatch.setattr(api,"POOL",Inline())
    calls=[]
    def fake_stage(*,source,prompt,destination,consent,commercial):
        calls.append("scene")
        assert source.is_file() and consent and not commercial
        Image.new("RGB",(512,512),"purple").save(destination)
        return stage.SceneReceipt(True,"synthetic_unit_scene_provider",47.0)
    def fake_video(*,prompt,seconds,reference,destination,consent,commercial):
        calls.append("video")
        assert reference is not None and reference.name=="generated-shared-stage.png"
        assert reference.exists()
        make_video(destination)
        with destination.open("rb") as inp:
            digest=hashlib.file_digest(inp,"sha256").hexdigest()
        return ltx.NativeReceipt(digest,float(seconds),destination.stat().st_size,
            "synthetic_unit_ai",audio_evidence.inspect_mp4(
                destination,audio_required=True).as_dict(),
            visual_quality.inspect_mp4(destination,audio_required=True).as_dict())
    monkeypatch.setattr(api.stage_builder,"build",fake_stage)
    monkeypatch.setattr(api.ltx,"generate",fake_video)
    result=client.post("/v1/native-av/jobs",json=body(),headers=token)
    assert result.status_code==202,result.text
    jobid=result.json()["job_id"]
    status=client.get("/v1/jobs/"+jobid,headers=token)
    assert status.status_code==200,status.text
    data=status.json()
    assert data["state"]=="completed",data
    assert calls==["scene","video"]
    assert data["quality"]["shared_scene_generated_by_image_model"] is True
    assert data["quality"]["stage_builder_quality"]["faces_preserved_verified"] is False
    assert data["quality"]["duet_singing_verified"] is False
    assert data["has_audio"]
    assert data["quality"]["scene_audit"]["output_is_split_layout"] is False
    assert not (root/jobid/"generated-shared-stage.png").exists()
    movie=client.get("/v1/jobs/"+jobid+"/result",headers=token)
    assert movie.status_code==200 and movie.content[4:8]==b"ftyp"

def test_scene_failure_does_not_retry_video(setup):
    client,monkeypatch,root=setup
    token=guest(client)
    class Inline:
        def submit(self,fn,*args,**kwargs):fn(*args,**kwargs)
    monkeypatch.setattr(api,"POOL",Inline())
    calls=[]
    def crash(**kwargs):
        calls.append("scene")
        raise stage.SceneUncertain("Ambiguous acceptance")
    monkeypatch.setattr(api.stage_builder,"build",crash)
    monkeypatch.setattr(api.ltx,"generate",lambda **kw:calls.append("video"))
    r=client.post("/v1/native-av/jobs",json=body(),headers=token)
    assert r.status_code==202
    state=client.get("/v1/jobs/"+r.json()["job_id"],headers=token).json()
    assert state["state"]=="failed" and calls==["scene"]


def test_android_433_metadata_only_duo_preflight_accepts_selected_two_photos(setup):
    """Exact Android request that failed in screenshot: image_count=1, no bytes."""
    client,monkeypatch,root=setup
    token=guest(client)
    request={"prompt":"Two actors singing on stage at Caesarea before 10000 people",
        "seconds":8,"image_count":1,"requires_shared_stage_scene":True,
        "third_party_transfer_consent":True}
    assert "images" not in request
    result=client.post("/v1/native-av/plan",headers=token,json=request)
    assert result.status_code==200,result.text
    assert result.json()["status"]=="eligible_for_attempt",result.text
    assert "combined_two_person_reference_required" not in result.json()["blockers"]
    assert result.json()["credits_spent"]==0
    assert not list(root.iterdir()) and trials.COUNTERS=={}
    # Preflight should not bypass ACTUAL job's required image contents.
    incomplete=client.post("/v1/native-av/jobs",headers=token,
        json={k:v for k,v in request.items() if k!="image_count"})
    assert incomplete.status_code==422
    assert trials.COUNTERS=={}

def test_android_one_image_and_text_only_metadata_preflight(setup):
    client,_,root=setup
    token=guest(client)
    for image_count in (0,1):
        request={"prompt":"Animated cartoon singer waving arms with live music",
            "seconds":15,"image_count":image_count,
            "third_party_transfer_consent":True,
            "requires_shared_stage_scene":False}
        response=client.post("/v1/native-av/plan",headers=token,json=request)
        assert response.status_code==200
        assert response.json()["status"]=="eligible_for_attempt"
    assert trials.COUNTERS=={} and not list(root.iterdir())

def test_two_people_preflight_with_no_selected_source_remains_blocked(setup):
    client,_,root=setup
    token=guest(client)
    result=client.post("/v1/native-av/plan",headers=token,
        json={"prompt":"Two people sing together on one stage",
              "seconds":8,"image_count":0,
              "requires_shared_stage_scene":True,
              "third_party_transfer_consent":True})
    assert result.status_code==200
    assert result.json()["status"]=="blocked"
    assert "combined_two_person_reference_required" in result.json()["blockers"]
    assert not list(root.iterdir())

def test_preflight_rejects_inconsistent_actual_photo_and_count(setup):
    client,_,root=setup
    token=guest(client)
    result=client.post("/v1/native-av/plan",headers=token,
        json={"prompt":"Two people perform together on stage",
              "seconds":8,"image_count":0,"images":[photo()],
              "requires_shared_stage_scene":True,
              "third_party_transfer_consent":True})
    assert result.status_code==200
    assert "image_count_and_supplied_images_disagree" in result.json()["blockers"]
    assert trials.COUNTERS=={} and not list(root.iterdir())
