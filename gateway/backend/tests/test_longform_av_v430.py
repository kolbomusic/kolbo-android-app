"""End-to-end assembly evidence for exactly 15s and audible 3-shot real motion.

All sources are locally generated moving FFmpeg test patterns. No proprietary,
copyrighted or personal media. These prove the media pipeline, NOT availability
of free AI GPU to supply the three moving scene segments.
"""
import hashlib
import math
from pathlib import Path
import struct
import subprocess
import wave

import pytest
import longform_av as av


def moving(out:Path,seconds:int,variant:int=0):
    # FFmpeg testsrc2 provides actual changing video pixels, never a photo pan.
    return subprocess.run(["ffmpeg","-nostdin","-v","error","-y",
       "-f","lavfi","-i",f"testsrc2=s=320x240:r=16:d={seconds}",
       "-filter_complex",f"[0:v]hue=h={variant*31}[v]",
       "-map","[v]","-pix_fmt","yuv420p","-c:v","libx264",
       "-preset","ultrafast","-crf","30",str(out)],
        check=True,capture_output=True,timeout=60)


def static(out:Path,seconds:int):
    subprocess.run(["ffmpeg","-nostdin","-v","error","-y",
        "-f","lavfi","-i",f"color=c=blue:s=320x240:r=16:d={seconds}",
        "-c:v","libx264","-preset","ultrafast",str(out)],
        check=True,capture_output=True,timeout=40)


def tone(out:Path,seconds:int):
    with wave.open(str(out),"wb") as f:
        f.setnchannels(1);f.setsampwidth(2);f.setframerate(16000)
        block=b"".join(struct.pack("<h",int(2300*math.sin(2*math.pi*440*i/16000)))
                  for i in range(seconds*16000))
        f.writeframes(block)


@pytest.mark.parametrize("seconds,expected",[
    (1,(1,)),(5,(5,)),(6,(5,1)),(10,(5,5)),
    (11,(5,5,1)),(14,(5,5,4)),(15,(5,5,5))
])
def test_shot_planner_obeys_exact_full_duration(seconds,expected):
    assert av.split_shots(seconds)==expected
    assert sum(expected)==seconds


@pytest.mark.parametrize("seconds",[0,16,30,15.5,True,None])
def test_planner_refuses_unsupported_length(seconds):
    with pytest.raises(av.LongformError):
        av.split_shots(seconds)


def test_15_seconds_plan_requires_three_actual_gpu_jobs():
    result=av.plan(seconds=15,image_count=1,
        audio_source="owned_wav",quota_remaining=2,
        licensed_provider=True,consent_to_external_transfer=True)
    assert result.status=="blocked"
    assert result.shots==(5,5,5)
    assert "insufficient_real_video_model_quota" in result.blockers
    assert result.required_external_video_submissions==3
    assert result.unlimited_free_rendering is False


def test_no_fake_singing_or_duet_or_music():
    r=av.plan(seconds=15,image_count=2,
        singing_requested=True,voice_requested=True,lipsync_requested=True,
        two_independent_people=True,audio_source="synthetic_sfx",
        quota_remaining=3,licensed_provider=True,
        consent_to_external_transfer=True)
    assert r.status=="blocked"
    assert "singing_generation_and_sync_not_available" in r.blockers
    assert "lipsync_not_available" in r.blockers
    assert "two_identity_preservation_not_available" in r.blockers
    no_audio=av.plan(seconds=5,image_count=1,audio_source="none",
        quota_remaining=3,licensed_provider=True,
        consent_to_external_transfer=True)
    assert "audible_track_required" in no_audio.blockers


def test_real_15_second_three_moving_shots_with_original_sfx(tmp_path):
    clips=[]
    for i in range(3):
        part=tmp_path/f"motion{i}.mp4"
        moving(part,5,i)
        clips.append(part)
    output=tmp_path/"15s-sound.mp4"
    receipt=av.assemble(segments=clips,seconds=15,output=output,
        synthetic_effect="applause")
    assert output.stat().st_size>20000
    assert abs(receipt["duration_seconds"]-15.0)<.085
    assert receipt["shots_seconds"]==[5,5,5]
    assert receipt["video_segments"]==3
    assert receipt["has_audio"] is True
    assert receipt["audio_source"]=="original_synthetic_sfx"
    assert receipt["audio_evidence"]["has_audio_stream"] is True
    assert receipt["audio_evidence"]["decoded_audio"] is True
    assert receipt["audio_evidence"]["non_silent_fraction"]>.03
    assert receipt["motion_evidence"]["final"]["pixel_change_fraction"]>.012
    assert receipt["singing_verified"] is False
    assert receipt["gpu_provider_licensing_verified"] is False
    assert len(receipt["sha256"])==64
    assert receipt["sha256"]==hashlib.sha256(output.read_bytes()).hexdigest()


def test_actual_user_recorded_wav_mixes_as_real_audio(tmp_path):
    part=tmp_path/"motion.mp4"
    moving(part,5)
    sound=tmp_path/"mine.wav"
    tone(sound,5)
    dest=tmp_path/"result.mp4"
    receipt=av.assemble(segments=[part],seconds=5,output=dest,
                        user_soundtrack=sound)
    assert receipt["has_audio"]
    assert receipt["audio_source"]=="user_supplied_wav"
    assert abs(receipt["duration_seconds"]-5)<.085


def test_never_silent_success_or_padding_with_missing_video(tmp_path):
    p=tmp_path/"one.mp4"
    moving(p,5)
    with pytest.raises(av.LongformError,match="segments missing"):
        av.assemble(segments=[p],seconds=15,
            output=tmp_path/"should_not_exist.mp4",
            synthetic_effect="rain")
    assert not (tmp_path/"should_not_exist.mp4").exists()


def test_reject_15_second_slideshow_source_before_any_output(tmp_path):
    clips=[tmp_path/f"{i}.mp4" for i in range(3)]
    for p in clips:
        static(p,5)
    dest=tmp_path/"bad.mp4"
    with pytest.raises(av.LongformError,match="Frozen|identical"):
        av.assemble(segments=clips,seconds=15,output=dest,
            synthetic_effect="rain")
    assert not dest.exists()


def test_reject_silent_and_short_wav(tmp_path):
    clip=tmp_path/"clip.mp4"
    moving(clip,5)
    with pytest.raises(av.LongformError,match="audible"):
        av.assemble(segments=[clip],seconds=5,output=tmp_path/"silent.mp4")
    too_short=tmp_path/"short.wav"
    tone(too_short,2)
    with pytest.raises(av.LongformError,match="span"):
        av.assemble(segments=[clip],seconds=5,output=tmp_path/"wrong.mp4",
                    user_soundtrack=too_short)


def test_can_extract_frame_for_future_provider_continuity(tmp_path):
    clip=tmp_path/"first.mp4";moving(clip,5)
    ref=av.last_frame(clip,tmp_path/"ref.png")
    assert ref.exists() and ref.stat().st_size>300
