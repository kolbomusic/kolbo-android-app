"""Real CPU MP4 with synthesized audible effect and no external inference."""
import hashlib
from pathlib import Path
import pytest
from PIL import Image
from fastapi.testclient import TestClient
import audio_evidence
import procedural_sfx
import staging_wan_api as api
from test_studio_api_v418 import image,request,headers


@pytest.mark.parametrize("description,expected",[
    ("האיש מפליץ ונקרע מצחוק","fart"),
    ("הוא מפליצים בקולי קולות","fart"),
    ("man farts loudly","fart"),
    ("ממש יורד גשם עכשיו","rain"),
    ("מחיאות כפיים אחרי ההופעה","applause"),
    ("ציפורים מצייצות בבוקר","bird"),
    ("הדמות אומרת משהו בעברית","none"),
    ("Sing in Bukharian","none"),
    ("בלי גשם נעים יותר","none"),
])
def test_only_explicit_sfx_intents(description,expected):
    assert procedural_sfx.recognize(description)==expected


def test_procedural_sfx_encoded_in_real_video_and_audible(tmp_path):
    src=tmp_path/"photo.png"
    Image.new("RGB",(240,360),(38,86,120)).save(src)
    for effect in ("fart","rain","applause","bird"):
        result_file=tmp_path/(effect+".mp4")
        from cpu_photo_studio import render
        receipt=render(photos=[src],seconds=3,out=result_file,generated_sfx=effect)
        assert receipt.ai_video_generated is False
        assert receipt.generated_sfx==effect
        assert receipt.audio_from_user is False
        assert receipt.has_audio_track is True
        assert abs(receipt.actual_seconds-3)<0.15
        check=audio_evidence.inspect_mp4(result_file,audio_required=True)
        assert check.has_audio_stream and check.decoded_audio
        assert check.non_silent_fraction>0.03
        assert check.verdict!="reject", (effect,check)



def test_generated_sfx_sent_only_for_opted_in_cpu_mode(monkeypatch,tmp_path):
    import base64
    monkeypatch.setenv("KOLBO_V416_API_TOKEN","safe_local_test_only_1234567890_123456789")
    monkeypatch.setenv("KOLBO_ALLOW_EXTERNAL_TEST_MEDIA","DISABLED")
    monkeypatch.setattr(api,"ROOT",tmp_path)
    with api.LOCK:
        api.JOBS.clear(); api.DIGESTS.clear()
    class Inline:
        def submit(self,fn,*args,**kwargs):fn(*args,**kwargs)
    monkeypatch.setattr(api,"POOL",Inline())
    monkeypatch.setattr(api.provider,"submit_one",lambda **kw: (_ for _ in ()).throw(AssertionError("vendor called")))
    pic=image((160,160,210))
    payload={"seconds":3,"images":[pic],"mode":"cpu_photo_motion",
             "media_rights_attested":True,
             "sound_effect_description":"האיש מפליץ",
             "include_procedural_effect":True}
    c=TestClient(api.app)
    x=c.post("/v1/studio/jobs",json=payload,headers=headers())
    assert x.status_code==202,x.text
    status=c.get("/v1/jobs/"+x.json()["job_id"],headers=headers())
    assert status.status_code==200
    assert status.json()["state"]=="completed",status.json()
    assert status.json()["has_audio"] is True
    assert status.json()["quality"]["generated_sfx"]=="fart"
    assert status.json()["quality"]["measured_audio"]["verdict"]!="reject"
    r=c.get("/v1/jobs/"+x.json()["job_id"]+"/result",headers=headers())
    assert r.status_code==200 and r.content[4:8]==b"ftyp"
    # Explicit opt-out cannot silently reuse an audible result.
    payload["include_procedural_effect"]=False
    other=c.post("/v1/studio/jobs",json=payload,headers=headers())
    assert other.status_code==202
    assert other.json()["job_id"]!=x.json()["job_id"]
    other_state=c.get("/v1/jobs/"+other.json()["job_id"],headers=headers()).json()
    assert other_state["has_audio"] is False
