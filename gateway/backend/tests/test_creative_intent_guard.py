"""Creative requirements: no fake audio, shortened results or merged identities."""
import base64
from io import BytesIO

from fastapi.testclient import TestClient
from PIL import Image
import pytest
import creative_intent_guard as guard
import staging_wan_api as api


@pytest.mark.parametrize("prompt,expected",[
    ("הדמות תשיר בבוכרית כשהיא רוקדת", "requested_audio_unavailable"),
    ("הדמות תדבר בעברית מול המצלמה", "requested_audio_unavailable"),
    ("האיש יושב בשירותים ומפליץ בקול", "requested_audio_unavailable"),
    ("She sings in Bukharian", "requested_audio_unavailable"),
    ("The character says something funny", "requested_audio_unavailable"),
    ("The man makes realistic fart sounds", "requested_audio_unavailable"),
    ("שתי הדמויות ירקדו יחד באותה סצנה", "multiple_subject_identity_unavailable"),
    ("both characters dance in the same room", "multiple_subject_identity_unavailable"),
    ("הדמות מבצעת סנכרון שפתיים לשיר", "lip_sync_unavailable"),
])
def test_unavailable_semantics_blocked_before_submission(prompt,expected):
    plan=guard.plan(prompt=prompt, seconds=3.5,image_count=1,
                    consent=True,compute_available=True)
    assert plan.status=="blocked"
    assert expected in plan.blockers
    assert not plan.automatic_success_claim


def test_without_background_music_does_not_hide_singing():
    p=guard.plan(prompt="היא שרה בבוכרית ללא מוזיקה", seconds=3.5,
                 image_count=1,consent=True,compute_available=True)
    assert p.needs_audio and "requested_audio_unavailable" in p.blockers


@pytest.mark.parametrize("length",[0.5,8,12,60])
def test_no_silent_shortened_fallback(length):
    p=guard.plan(prompt="A golden rocket moves in the sky", seconds=length,
                 image_count=1,consent=True,compute_available=True)
    assert p.status=="blocked" and "duration_unsupported" in p.blockers


def test_single_image_silent_trial_is_only_draft():
    p=guard.plan(prompt="An origami rocket moves upward",
         seconds=3.5,image_count=1,consent=True,compute_available=True)
    assert p.status=="draft_possible"
    assert p.cost_verified_free is False
    assert p.automatic_success_claim is False
    assert "human_semantic_review_required" in p.limits


def test_explicit_flags_override_missing_words():
    p=guard.plan(prompt="A person turns around",seconds=3.5,image_count=1,
           requires_audio=True,requires_lipsync=True,
           requires_two_independent_people=True,commercial_use=True,
           consent=True,compute_available=True)
    assert set(("requested_audio_unavailable","lip_sync_unavailable",
                "multiple_subject_identity_unavailable",
                "commercial_rights_not_verified")) <= set(p.blockers)


def test_audio_absence_not_guessed_as_video_quality():
    p=guard.plan(prompt="A dancer dances without music",
           seconds=3.5,image_count=1,consent=True,compute_available=True)
    assert p.status=="draft_possible"


def test_unconfigured_compute_rejected():
    p=guard.plan(prompt="A dancer moves in a room",seconds=3.5,image_count=1,
           consent=True,compute_available=False)
    assert "no_enabled_verified_free_gpu_route" in p.blockers


def test_api_preflight_readonly_does_not_upload(monkeypatch,tmp_path):
    monkeypatch.setenv("KOLBO_V416_API_TOKEN","a_secret_token_at_least_32_characters")
    monkeypatch.setattr(api,"ROOT",tmp_path)
    monkeypatch.setattr(api,"enabled",lambda: True)
    client=TestClient(api.app)
    headers={"Authorization":"Bearer a_secret_token_at_least_32_characters"}
    response=client.post("/v1/creative/plan",headers=headers,json={
        "prompt":"הדמויות שרות ורוקדות בבוכרית",
        "seconds":8,"image_count":2,"third_party_transfer_consent":True})
    assert response.status_code==200
    p=response.json()
    assert p["status"]=="blocked"
    assert set(("duration_unsupported","requested_audio_unavailable",
                "multiple_subject_identity_unavailable")) <= set(p["blockers"])
    assert list(tmp_path.iterdir())==[]
    assert client.post("/v1/creative/plan",json={"prompt":"some video",
        "seconds":8,"image_count":2}).status_code==401


def test_job_fails_before_decoding_media_or_submitting(monkeypatch,tmp_path):
    monkeypatch.setenv("KOLBO_V416_API_TOKEN","a_secret_token_at_least_32_characters")
    monkeypatch.setattr(api,"ROOT",tmp_path)
    monkeypatch.setattr(api,"enabled",lambda: True)
    invoked=[]
    monkeypatch.setattr(api.POOL,"submit",lambda *args,**kwargs:invoked.append(1))
    with api.LOCK:
        api.JOBS.clear();api.DIGESTS.clear()
    img=BytesIO()
    Image.new("RGB",(80,80)).save(img,format="PNG")
    body={"prompt":"the dancer sings in Bukharian","seconds":3.5,
          "images":[{"mime_type":"image/png",
           "data_base64":base64.b64encode(img.getvalue()).decode()}],
          "third_party_transfer_consent":True}
    client=TestClient(api.app)
    res=client.post("/v1/jobs",json=body,headers={
        "Authorization":"Bearer a_secret_token_at_least_32_characters"})
    assert res.status_code==422
    assert "requested_audio_unavailable" in res.json()["detail"]["blockers"]
    assert not invoked
    assert list(tmp_path.iterdir())==[]
