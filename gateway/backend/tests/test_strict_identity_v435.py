"""Strict local, ephemeral face resemblance acceptance unit and API tests.

Artificial numeric vectors only. No actual or identifying personal data in CI.
A separate model smoke verifies OpenCV model SHA and C++ inference loads.
"""
import pytest
from pathlib import Path
from types import SimpleNamespace
import identity_guard_v435 as guard
import staging_wan_api as api
from test_two_person_stage_pipeline_v433 import setup,guest,body,make_video

# Stub numeric SFace feature: each float uniquely identifies a synthetic actor.
class StubFaceEngine:
    def __init__(self,samples):
        self.samples=samples
    def embeddings(self,photo):
        return self.samples[Path(photo).name]
    def cosine(self,a,b):
        return 1.0-abs(float(a)-float(b))

def source():
    return [(0.25,0.),(0.75,1.)]
def intact():
    return [(0.25,.04),(.75,.97)]

def test_actor_one_and_two_remain_in_slots_with_high_separation():
    engine=StubFaceEngine({})
    score=guard.compare_slots(source(),intact(),engine)
    assert score.left_similarity==pytest.approx(.96)
    assert score.right_similarity==pytest.approx(.97)
    assert score.minimum_wrong_pair_margin>.8
    assert not score.same_real_people_guaranteed

@pytest.mark.parametrize("fake,reason",[
    ([(.25,1.),(.75,0.)],"swapped"),
    ([(.25,.9),(.75,.9)],"mismatch"),
    ([(.25,.02)],"two visible"),
    ([(.25,.03),(.27,.99)],"overlap"),
])
def test_reject_identity_swapped_merged_or_missing(fake,reason):
    with pytest.raises(guard.IdentityMismatch):
        guard.compare_slots(source(),fake,StubFaceEngine({}))

def test_reject_source_when_cannot_separate_two_individuals():
    e=StubFaceEngine({})
    with pytest.raises(guard.IdentityMismatch):
        guard.compare_slots([(.25,.08),(.8,.09)],intact(),e)

def test_face_guard_fails_closed_when_models_missing(tmp_path,monkeypatch):
    monkeypatch.setenv("KOLBO_STRICT_FACE_GUARD","EXPLICITLY_ENABLED")
    monkeypatch.setenv("KOLBO_LOCAL_FACE_MODELS_DIR",str(tmp_path))
    assert not guard.configured()
    with pytest.raises(guard.IdentityUnavailable):
        guard.JobIdentityGuard(tmp_path/"fake.png")
    # Face data is neither uploaded nor retained in persistent models.
    assert list(tmp_path.iterdir())==[]

def test_different_files_with_wrong_hash_must_not_activate_model(tmp_path,monkeypatch):
    monkeypatch.setenv("KOLBO_STRICT_FACE_GUARD","EXPLICITLY_ENABLED")
    monkeypatch.setenv("KOLBO_LOCAL_FACE_MODELS_DIR",str(tmp_path))
    for filename in (guard.DETECTOR_NAME,guard.MATCHER_NAME):
        (tmp_path/filename).write_bytes(b"x"*40000)
    assert not guard.configured()
    assert not guard.models_present()

def test_actual_duo_submission_refused_without_available_local_gate(setup,monkeypatch):
    client,_,root=setup
    token=guest(client)
    monkeypatch.setattr(api.identity_gate,"configured",lambda:False)
    plan=client.post("/v1/native-av/plan",headers=token,json={
        "prompt":"Two actors on stage with accurate original faces","seconds":8,
        "image_count":1,"requires_shared_stage_scene":True,
        "third_party_transfer_consent":True})
    assert plan.status_code==200
    assert plan.json()["status"]=="blocked"
    assert "local_face_similarity_guard_unavailable" in plan.json()["blockers"]
    result=client.post("/v1/native-av/jobs",headers=token,json=body())
    assert result.status_code==503
    assert api.ai_trials.COUNTERS=={}
    assert list(root.iterdir())==[]

def test_changed_faces_in_new_stage_abort_before_video_model(setup,monkeypatch):
    client,_,root=setup
    token=guest(client)
    class Inline:
        def submit(self,fn,*args,**kwargs):fn(*args,**kwargs)
    monkeypatch.setattr(api,"POOL",Inline())
    calls=[]
    class RejectStage:
        def __init__(self,photo):calls.append("extract_source")
        def verify_still(self,image):
            calls.append("compare_stage")
            raise guard.IdentityMismatch("Faces changed on new stage")
        def verify_video(self,video):
            calls.append("video_verification")
        def discard(self):calls.append("discard")
    monkeypatch.setattr(api.identity_gate,"JobIdentityGuard",RejectStage)
    def stage_edit(*,source,prompt,destination,consent,commercial):
        from PIL import Image
        calls.append("create_stage")
        Image.new("RGB",(512,512),"orange").save(destination)
        return SimpleNamespace(as_dict=lambda:{"faces_preserved_verified":False})
    monkeypatch.setattr(api.stage_builder,"build",stage_edit)
    monkeypatch.setattr(api.ltx,"generate",lambda **kw:calls.append("EXPENSIVE_VIDEO"))
    response=client.post("/v1/native-av/jobs",headers=token,json=body())
    assert response.status_code==202
    job=response.json()["job_id"]
    status=client.get("/v1/jobs/"+job,headers=token).json()
    assert status["state"]=="failed"
    assert status["error"]=="generated_stage_faces_changed"
    assert calls==["extract_source","create_stage","compare_stage","discard"]
    assert not (root/job/"draft.mp4").exists()
    assert client.get("/v1/jobs/"+job+"/result",headers=token).status_code==409

def test_identity_drift_in_video_rejects_download_and_deletes_failed_mp4(
        setup,monkeypatch):
    client,_,root=setup
    token=guest(client)
    class Inline:
        def submit(self,fn,*args,**kwargs):fn(*args,**kwargs)
    monkeypatch.setattr(api,"POOL",Inline())
    class StagePassVideoFail:
        def __init__(self,photo):pass
        def verify_still(self,path):
            return SimpleNamespace(as_dict=lambda:{"left_similarity":.81,"right_similarity":.76})
        def verify_video(self,path):
            raise guard.IdentityMismatch("Left person replaced in middle frame")
        def discard(self):pass
    monkeypatch.setattr(api.identity_gate,"JobIdentityGuard",StagePassVideoFail)
    def fake_stage(*,source,prompt,destination,consent,commercial):
        from PIL import Image
        Image.new("RGB",(512,512),"purple").save(destination)
        return SimpleNamespace(as_dict=lambda:{"generated_new_scene":True})
    monkeypatch.setattr(api.stage_builder,"build",fake_stage)
    def generate(*,prompt,seconds,reference,destination,consent,commercial):
        make_video(destination)
        return SimpleNamespace(as_dict=lambda:{"native_video":True},
            size_bytes=destination.stat().st_size,
            sha256="0"*64)
    monkeypatch.setattr(api.ltx,"generate",generate)
    response=client.post("/v1/native-av/jobs",headers=token,json=body())
    assert response.status_code==202
    job=response.json()["job_id"]
    state=client.get("/v1/jobs/"+job,headers=token).json()
    assert state["state"]=="failed"
    assert state["error"]=="video_faces_changed"
    assert not (root/job/"draft.mp4").exists()
    assert client.get("/v1/jobs/"+job+"/result",headers=token).status_code==409



def test_local_face_restore_is_optional_and_disabled_by_default(monkeypatch):
    import local_face_repair_v435 as repair
    monkeypatch.delenv("KOLBO_LOCAL_FACE_REPAIR",raising=False)
    assert repair.enabled() is False

def test_original_pixels_can_be_restored_without_a_second_external_gpu_job(
        setup,monkeypatch):
    from PIL import Image
    import local_face_repair_v435 as repair
    import experimental_scene_builder_v433 as builder
    client,_,root=setup
    token=guest(client)
    monkeypatch.setenv("KOLBO_LOCAL_FACE_REPAIR","EXPLICITLY_ENABLED")
    class Inline:
        def submit(self,fn,*args,**kwargs):fn(*args,**kwargs)
    monkeypatch.setattr(api,"POOL",Inline())
    calls=[]
    class ModelIdentity:
        def __init__(self,source):calls.append("source")
        def verify_still(self,image):
            if "restored" not in str(image):
                calls.append("original_stage_rejected")
                raise guard.IdentityMismatch("FLUX changed the faces")
            calls.append("locally_repaired_stage_passed")
            return SimpleNamespace(as_dict=lambda:{"left_similarity":.78,
                              "right_similarity":.82})
        def verify_video(self,video):
            calls.append("video_face_check")
            return [SimpleNamespace(as_dict=lambda:{"left_similarity":.74,
                     "right_similarity":.75}) for _ in range(3)]
        def discard(self):calls.append("discard")
    monkeypatch.setattr(api.identity_gate,"JobIdentityGuard",ModelIdentity)
    def new_stage(*,source,prompt,destination,consent,commercial):
        calls.append("external_scene_GPU")
        Image.new("RGB",(512,512),"purple").save(destination)
        return builder.SceneReceipt(True,"fake",35.0)
    def restore(source,stage,destination):
        calls.append("local_CPU_face_restore")
        Image.new("RGB",(512,512),"yellow").save(destination)
        return destination
    def generate(*,prompt,seconds,reference,destination,consent,commercial):
        assert "restored" in reference.name
        calls.append("external_video_GPU")
        make_video(destination)
        return SimpleNamespace(as_dict=lambda:{"video":True},
                sha256="0"*64,size_bytes=destination.stat().st_size)
    monkeypatch.setattr(api.stage_builder,"build",new_stage)
    monkeypatch.setattr(api.face_repair,"reconstruct",restore)
    monkeypatch.setattr(api.ltx,"generate",generate)
    response=client.post("/v1/native-av/jobs",headers=token,json=body())
    assert response.status_code==202
    job=response.json()["job_id"]
    state=client.get("/v1/jobs/"+job,headers=token).json()
    assert state["state"]=="completed",state
    assert state["quality"]["face_similarity_check_passed"] is True
    assert state["quality"]["face_stage_scores"]["left_similarity"]==.78
    assert len(state["quality"]["face_video_scores"])==3
    assert calls==["source","external_scene_GPU","original_stage_rejected",
        "local_CPU_face_restore","locally_repaired_stage_passed",
        "external_video_GPU","video_face_check","discard"]
    assert not (root/job/"local-face-restored-stage.png").exists()
