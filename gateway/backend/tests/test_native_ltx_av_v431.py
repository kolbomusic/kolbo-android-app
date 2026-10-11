"""v431 strict public LTX native audio+video route: mocked model but real MP4 QA.

The ONE live trial is kept in a separate optional workflow. Regression CI never
uploads photos or consumes the community's anonymous GPU credits.
"""
import base64
import hashlib
import io
from pathlib import Path
import subprocess
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from PIL import Image

import experimental_ltx25_native_av as adapter
import staging_wan_api as api
import guest_sessions as guests
import ai_trial_guards as trials

@pytest.fixture
def state(monkeypatch,tmp_path):
    monkeypatch.setenv("KOLBO_V416_API_TOKEN","unit_only_master_token_0123456789_1234567890")
    monkeypatch.setenv("KOLBO_GUEST_CPU_BOOTSTRAP","EXPLICITLY_ENABLED")
    monkeypatch.setenv("KOLBO_GUEST_CPU_SESSION_SECRET",
        "unit_only_guest_secret_0123456789_unit_only_0123456789abcde")
    monkeypatch.setenv("KOLBO_GUEST_AI_TRIAL","EXPLICITLY_ENABLED")
    monkeypatch.setenv("KOLBO_ALLOW_EXTERNAL_TEST_MEDIA","EXPLICITLY_ENABLED")
    monkeypatch.setenv("KOLBO_NATIVE_LTX25_TRIAL","EXPLICITLY_ENABLED")
    monkeypatch.setattr(api,"ROOT",tmp_path)
    monkeypatch.setattr(api,"enabled",lambda:True)
    with api.LOCK:
        api.JOBS.clear(); api.DIGESTS.clear()
    with guests.LOCK:guests.COUNTERS.clear()
    with trials.LOCK:trials.COUNTERS.clear()
    return TestClient(api.app),monkeypatch,tmp_path

def user(client,char):
    r=client.post("/v1/guest/bootstrap",json={"install_id":char*32})
    assert r.status_code==200,r.text
    return {"Authorization":"Bearer "+r.json()["token"]}

def picture():
    o=io.BytesIO()
    Image.new("RGB",(96,96),(40,75,180)).save(o,"PNG")
    return {"mime_type":"image/png",
            "data_base64":base64.b64encode(o.getvalue()).decode()}

def request(**changes):
    x={"prompt":"One cartoon character waves on stage and laughs clearly.",
       "seconds":3,"images":[],"third_party_transfer_consent":True}
    x.update(changes)
    return x

def test_feature_off_by_default_requires_env(state):
    c,m,_=state
    m.setenv("KOLBO_NATIVE_LTX25_TRIAL","DISABLED")
    a=user(c,"a")
    assert c.get("/v1/health",headers=a).json()["native_audio_video_trial"]["ready"] is False
    assert c.post("/v1/native-av/jobs",headers=a,json=request()).status_code==503

def test_guest_preflight_spends_no_gpu_or_uploads(state):
    c,_,root=state
    a=user(c,"a")
    health=c.get("/v1/health",headers=a).json()
    assert health["native_audio_video_trial"]["ready"]
    assert health["native_audio_video_trial"]["max_seconds"]==15
    assert health["native_audio_video_trial"]["native_audio"]
    assert health["native_audio_video_trial"]["singing_lipsync_verified"] is False
    preview=c.post("/v1/native-av/plan",headers=a,json=request(seconds=15))
    assert preview.status_code==200 and preview.json()["credits_spent"]==0
    assert preview.json()["status"]=="eligible_for_attempt"
    denied=c.post("/v1/native-av/plan",headers=a,json=request(
        third_party_transfer_consent=False))
    assert denied.json()["status"]=="blocked"
    assert c.post("/v1/native-av/plan",json=request()).status_code==401
    assert list(root.iterdir())==[]

@pytest.mark.parametrize("bad,expected",[
    ({"third_party_transfer_consent":False},422),
    ({"commercial_use":True},422),
    ({"seconds":17},422),
    ({"images":[picture(),picture()]},422),
])
def test_fail_closed_before_inference_or_source_disk(state,bad,expected):
    c,m,root=state
    a=user(c,"a")
    calls=[]
    m.setattr(api.POOL,"submit",lambda *x,**kw:calls.append(1))
    result=c.post("/v1/native-av/jobs",headers=a,json=request(**bad))
    assert result.status_code==expected,result.text
    assert calls==[] and list(root.iterdir())==[]
    assert trials.COUNTERS=={}

def test_single_owned_native_av_job_and_no_quota_bypass(state):
    c,m,root=state
    a=user(c,"a");b=user(c,"b")
    calls=[]
    m.setattr(api.POOL,"submit",lambda *args,**kw:calls.append(1))
    result=c.post("/v1/native-av/jobs",headers=a,
             json=request(images=[picture()],seconds=15))
    assert result.status_code==202,result.text
    job=result.json()["job_id"]
    assert len(calls)==1
    retry=c.post("/v1/native-av/jobs",headers=a,
             json=request(images=[picture()],seconds=15))
    assert retry.status_code==202 and retry.json()["job_id"]==job
    assert len(calls)==1
    assert c.get("/v1/jobs/"+job,headers=b).status_code==404
    assert c.get("/v1/jobs/"+job,headers=a).status_code==200
    assert c.get("/v1/jobs/"+job+"/result",headers=b).status_code==404
    assert c.post("/v1/native-av/jobs",headers=a,json=request(
        prompt="An entirely different human figure dances")).status_code==503
    assert c.post("/v1/jobs",headers=a,json=request()).status_code==401

def test_actual_output_contains_motion_audible_track(state):
    c,m,root=state
    a=user(c,"a")
    class Immediate:
        def submit(self,fn,*args,**kw):
            fn(*args,**kw)
    m.setattr(api,"POOL",Immediate())
    def fake_generate(*,prompt,seconds,reference,destination,consent,commercial):
        assert consent and not commercial and int(seconds)==2
        subprocess.run(["ffmpeg","-nostdin","-v","error","-y",
            "-f","lavfi","-i","testsrc2=size=320x240:rate=16:duration=2",
            "-f","lavfi","-i","sine=frequency=440:sample_rate=16000:duration=2",
            "-map","0:v","-map","1:a","-c:v","libx264","-preset","ultrafast",
            "-c:a","aac","-shortest",str(destination)],
            check=True,timeout=70)
        import visual_quality,audio_evidence
        visual=visual_quality.inspect_mp4(destination,audio_required=True)
        aud=audio_evidence.inspect_mp4(destination,audio_required=True)
        with Path(destination).open("rb") as src:
            sha=hashlib.file_digest(src,"sha256").hexdigest()
        return adapter.NativeReceipt(sha,2,Path(destination).stat().st_size,
            "test-local-moving-video",aud.as_dict(),visual.as_dict())
    m.setattr(api.ltx,"generate",fake_generate)
    resp=c.post("/v1/native-av/jobs",headers=a,json=request(seconds=2))
    assert resp.status_code==202,resp.text
    jobid=resp.json()["job_id"]
    state=c.get("/v1/jobs/"+jobid,headers=a).json()
    assert state["state"]=="completed",state
    assert state["has_audio"] is True
    assert state["quality"]["audio_evidence"]["non_silent_fraction"]>.03
    r=c.get("/v1/jobs/"+jobid+"/result",headers=a)
    assert r.status_code==200 and r.content[4:8]==b"ftyp"


def test_public_provider_client_signature_without_real_network(state,tmp_path):
    m=state[1]
    m.setenv("KOLBO_NATIVE_LTX25_TRIAL","EXPLICITLY_ENABLED")
    movie=tmp_path/"source.mp4"
    subprocess.run(["ffmpeg","-nostdin","-v","error","-y",
        "-f","lavfi","-i","testsrc2=size=320x240:rate=16:duration=2",
        "-f","lavfi","-i","sine=frequency=600:sample_rate=16000:duration=2",
        "-c:v","libx264","-preset","ultrafast","-c:a","aac",str(movie)],
        check=True,timeout=70)
    captured=[]
    class Job:
        def done(self):return True
        def result(self):return (str(movie),42,"2s")
    class Client:
        def __init__(self,*a,**kw):captured.append(("init",a,kw))
        def submit(self,*args,**kw):
            captured.append(("generate",args,kw))
            return Job()
    output=tmp_path/"out.mp4"
    receipt=adapter.generate(prompt="One moving illustrated singer laughs.",
        seconds=2,destination=output,reference=None,consent=True,
        client_factory=Client,handle_file_fn=lambda x:x)
    assert receipt.size_bytes>2500 and receipt.audio_evidence["has_audio_stream"]
    calls=[c for c in captured if c[0]=="generate"]
    assert len(calls)==1
    assert calls[0][1][1] is None
    assert calls[0][1][2:5]==(512,512,2.0)
    assert calls[0][2]["api_name"]=="/generate_video"
