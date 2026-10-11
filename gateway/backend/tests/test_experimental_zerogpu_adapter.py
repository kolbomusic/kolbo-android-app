"""No network, no GPU, no third-party image transfer in these tests."""
import hashlib
from pathlib import Path
import pytest
import experimental_zerogpu_adapter as worker

class Task:
    def __init__(self, result):self._value=result;self.cancelled=False
    def done(self):return True
    def result(self):return self._value
    def cancel(self):self.cancelled=True

class Client:
    def __init__(self, result):self.result=result;self.called=[]
    def submit(self,*args,**kwargs):
        self.called.append((args,kwargs))
        return Task(self.result)


def test_default_disabled_even_with_consent(monkeypatch):
    monkeypatch.delenv("KOLBO_ALLOW_EXTERNAL_TEST_MEDIA",raising=False)
    with pytest.raises(worker.ProviderUnavailable,match="disabled"):
        worker.validate(references=1,seconds=3.5,wants_audio=False,
                        wants_lipsync=False,commercial=False,consent=True)

@pytest.mark.parametrize("config",[
    {"references":2}, {"references":0}, {"seconds":8},
    {"seconds":0}, {"wants_audio":True},
    {"wants_lipsync":True}, {"commercial":True}, {"consent":False},
])
def test_unsupported_request_rejected_before_external_upload(monkeypatch,config):
    monkeypatch.setenv("KOLBO_ALLOW_EXTERNAL_TEST_MEDIA","EXPLICITLY_ENABLED")
    options={"references":1,"seconds":3.5,"wants_audio":False,
             "wants_lipsync":False,"commercial":False,"consent":True}
    options.update(config)
    with pytest.raises(worker.UnsupportedRequest):
        worker.validate(**options)


def test_once_only_provider_result_creates_unpublished_mp4(monkeypatch,tmp_path):
    monkeypatch.setenv("KOLBO_ALLOW_EXTERNAL_TEST_MEDIA","EXPLICITLY_ENABLED")
    reference=tmp_path/"reference.png";reference.write_bytes(b"\x89PNG\r\n\x1a\n"+b"a"*300)
    returned=tmp_path/"supplier.mp4";returned.write_bytes(b"\0"*4000)
    c=Client([str(returned),42])
    monkeypatch.setattr(worker,"probe",lambda f:(3.5,True,False))
    out=tmp_path/"out.mp4"
    receipt=worker.submit_one(reference=reference,prompt="rocket moving upward",
         seconds=3.5,destination=out,consent=True,client_factory=lambda *args,**kw:c,
         handle_file_fn=lambda p:p)
    assert out.is_file() and out.stat().st_size==4000
    assert receipt.status=="requires_manual_semantic_review"
    assert receipt.public_record()["commercial_rights_verified"] is False
    assert c.called[0][1]["api_name"]=="/generate_video"
    assert c.called[0][0][4]==3.5
    with pytest.raises(worker.UnsupportedRequest,match="replace"):
        worker.submit_one(reference=reference,prompt="rocket moving upward",
         seconds=3.5,destination=out,consent=True,client_factory=lambda *args,**kw:c,
         handle_file_fn=lambda p:p)


def test_invalid_duration_does_not_publish_anything(monkeypatch,tmp_path):
    monkeypatch.setenv("KOLBO_ALLOW_EXTERNAL_TEST_MEDIA","EXPLICITLY_ENABLED")
    inp=tmp_path/"ref.png";inp.write_bytes(b"img")
    returned=tmp_path/"video.mp4";returned.write_bytes(b"\0"*5000)
    monkeypatch.setattr(worker,"probe",lambda p:(1.0,True,False))
    output=tmp_path/"out.mp4"
    with pytest.raises(worker.ProviderUnavailable,match="duration"):
        worker.submit_one(reference=inp,prompt="rocket moving upward",
            seconds=3.5,destination=output,consent=True,
            client_factory=lambda *args,**kw:Client([str(returned)]),
            handle_file_fn=lambda p:p)
    assert not output.exists()


def test_acceptance_uncertainty_never_retry(monkeypatch,tmp_path):
    monkeypatch.setenv("KOLBO_ALLOW_EXTERNAL_TEST_MEDIA","EXPLICITLY_ENABLED")
    inp=tmp_path/"ref.png";inp.write_bytes(b"img")
    called=[]
    class Broken:
        def submit(self,*args,**kwargs):
            called.append(1);raise TimeoutError("unknown")
    with pytest.raises(worker.UnknownAcceptance):
        worker.submit_one(reference=inp,prompt="rocket moving upward",
            seconds=3.5,destination=tmp_path/"out.mp4",consent=True,
            client_factory=lambda *args,**kw:Broken(),handle_file_fn=lambda p:p)
    assert len(called)==1
