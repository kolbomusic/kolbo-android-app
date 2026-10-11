"""Fast, deterministic offline photo-motion tests; never invoke a cloud provider."""
from pathlib import Path
import wave

from PIL import Image
import pytest

from cpu_photo_studio import FreeStudioError, render

def photo(path:Path,color:tuple[int,int,int])->Path:
    Image.new("RGB",(360,480),color).save(path)
    return path

def tone_wav(path:Path,seconds:int)->Path:
    import math,struct
    with wave.open(str(path),"wb") as file:
        file.setnchannels(1)
        file.setsampwidth(2)
        file.setframerate(16000)
        payload=b"".join(struct.pack("<h",int(3000*math.sin(2*math.pi*440*i/16000)))
                         for i in range(seconds*16000))
        file.writeframes(payload)
    return path

def test_two_photo_cpu_video_really_renders_8_seconds(tmp_path):
    one=photo(tmp_path/"a.png",(180,80,40))
    two=photo(tmp_path/"b.png",(40,110,190))
    result=render(photos=[one,two],seconds=8,out=tmp_path/"cpu.mp4")
    assert result.ai_video_generated is False
    assert result.mode=="cpu_photo_motion"
    assert result.photos==2
    assert result.audio_from_user is False
    assert abs(result.actual_seconds-8)<0.15
    assert result.bytes>3000
    assert len(result.sha256)==64

def test_user_supplied_audio_is_preserved_as_a_track(tmp_path):
    image=photo(tmp_path/"a.png",(100,160,40))
    audio=tone_wav(tmp_path/"user.wav",3)
    result=render(photos=[image],seconds=3,out=tmp_path/"voiced.mp4",
                  user_wav=audio)
    assert result.audio_from_user
    assert result.ai_video_generated is False
    assert 2.85<=result.actual_seconds<=3.15

def test_refuse_fake_longer_or_shorter_duration(tmp_path):
    one=photo(tmp_path/"a.png",(0,0,0))
    for secs in [0,1,13,60]:
        with pytest.raises(FreeStudioError):
            render(photos=[one],seconds=secs,out=tmp_path/"bad.mp4")

def test_cannot_claim_user_audio_from_too_short_soundtrack(tmp_path):
    one=photo(tmp_path/"a.png",(0,0,0))
    audio=tone_wav(tmp_path/"user.wav",2)
    with pytest.raises(FreeStudioError,match="duration"):
        render(photos=[one],seconds=8,out=tmp_path/"bad.mp4",user_wav=audio)

def test_output_cannot_be_overwritten(tmp_path):
    one=photo(tmp_path/"a.png",(0,0,0))
    output=tmp_path/"already.mp4"
    output.write_bytes(b"cannot overwrite")
    with pytest.raises(FreeStudioError,match="overwrite"):
        render(photos=[one],seconds=2,out=output)
    assert output.read_bytes()==b"cannot overwrite"

def test_no_garbage_image_accepted(tmp_path):
    bad=tmp_path/"bad.png"
    bad.write_text("not an image")
    with pytest.raises(Exception):
        render(photos=[bad],seconds=2,out=tmp_path/"fail.mp4")
    assert not (tmp_path/"fail.mp4").exists()
