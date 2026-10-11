"""One-stage provider error taxonomy regression. Synthetic inputs only."""
from pathlib import Path
from PIL import Image
import pytest
import experimental_scene_builder_v433 as stage
import native_av_failure_codes_v436 as failures

@pytest.mark.parametrize("error,expected",[
    ("ZeroGPU quota exceeded (60s requested vs 0s left)","public_gpu_quota_or_busy"),
    ("HTTP 429 Too many requests","public_gpu_quota_or_busy"),
    ("GPU queue over capacity","public_gpu_quota_or_busy"),
    ("Remote AppError: runtime exception","public_model_runtime_error"),
    ("Unknown failure contains private-photo-name.png","public_model_runtime_error")
])
def test_provider_classifies_only_safe_error_types(error,expected):
    assert stage._public_result_kind(RuntimeError(error))==expected

@pytest.mark.parametrize("reason,code",[
    ("public_gpu_quota_or_busy","stage_public_gpu_quota_or_busy"),
    ("public_model_runtime_error","stage_model_execution_failed"),
    ("unchanged_scene","stage_was_not_reconstructed"),
    ("invalid_provider_image","stage_returned_invalid_image"),
    ("stage_not_available","stage_provider_unavailable")
])
def test_stage_code_preserves_privacy_and_is_human_readable(reason,code):
    e=stage.SceneUnavailable("Bearer SECRET_PERSON_A.png",reason=reason)
    safe=failures.classify(e,"shared_stage_generation")
    assert safe.error==code and safe.phase=="shared_stage_generation"
    assert not safe.retry_automatically
    assert "SECRET_PERSON_A" not in safe.detail
    assert "Bearer" not in safe.detail

def test_model_result_direct_dict_path_is_supported(tmp_path,monkeypatch):
    monkeypatch.setenv("KOLBO_SCENE_BUILDER_V433","EXPLICITLY_ENABLED")
    monkeypatch.setenv("KOLBO_ALLOW_EXTERNAL_TEST_MEDIA","EXPLICITLY_ENABLED")
    src=tmp_path/"two_illustrations.jpg"
    Image.new("RGB",(512,512),(10,30,55)).save(src)
    generated=tmp_path/"model_generated.png"
    Image.new("RGB",(512,512),(235,150,65)).save(generated)
    class Response:
        def done(self):return True
        def result(self):return {"path":str(generated)}
    class Client:
        def __init__(self,*a,**kw):pass
        def submit(self,*a,**kw):
            assert kw["api_name"]=="/infer"
            return Response()
    result=stage.build(source=src,prompt="Transform into a lively stage",
       destination=tmp_path/"stage.png",consent=True,
       client_factory=Client,handle_file_fn=lambda p:p)
    assert result.generated_new_scene
    assert (tmp_path/"stage.png").is_file()

def test_provider_quota_exception_never_leaks_raw_prompt_or_service_text(tmp_path,monkeypatch):
    monkeypatch.setenv("KOLBO_SCENE_BUILDER_V433","EXPLICITLY_ENABLED")
    monkeypatch.setenv("KOLBO_ALLOW_EXTERNAL_TEST_MEDIA","EXPLICITLY_ENABLED")
    src=tmp_path/"two.png"
    Image.new("RGB",(512,512),"blue").save(src)
    class Job:
        def done(self):return True
        def result(self):
            raise RuntimeError("ZeroGPU quota exceeded TOKEN=topsecret.png")
    class Client:
        def __init__(self,*a,**kw):pass
        def submit(self,*a,**kw):return Job()
    with pytest.raises(stage.SceneUnavailable) as err:
        stage.build(source=src,prompt="Create concert stage",
            destination=tmp_path/"result.png",consent=True,
            client_factory=Client,handle_file_fn=lambda p:p)
    assert err.value.reason=="public_gpu_quota_or_busy"
    assert "topsecret" not in str(err.value)
    assert not (tmp_path/"result.png").exists()

def test_provider_timeout_ambiguous_never_auto_resubmits(tmp_path,monkeypatch):
    monkeypatch.setenv("KOLBO_SCENE_BUILDER_V433","EXPLICITLY_ENABLED")
    monkeypatch.setenv("KOLBO_ALLOW_EXTERNAL_TEST_MEDIA","EXPLICITLY_ENABLED")
    src=tmp_path/"two.png"
    Image.new("RGB",(512,512),"blue").save(src)
    calls=[]
    class Job:
        def done(self):return False
        def cancel(self):calls.append("cancel")
    class Client:
        def __init__(self,*a,**kw):pass
        def submit(self,*a,**kw):calls.append("submit");return Job()
    with pytest.raises(stage.SceneUncertain):
        stage.build(source=src,prompt="Create concert stage",
            destination=tmp_path/"result.png",consent=True,
            wait_seconds=0,
            client_factory=Client,handle_file_fn=lambda p:p)
    assert calls==["submit","cancel"]
