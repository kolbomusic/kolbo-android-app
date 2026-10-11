import subprocess
from pathlib import Path
import pytest
from audio_evidence import inspect_mp4


def make_mp4(file:Path,*,silent:bool):
    audio="anullsrc=channel_layout=mono:sample_rate=16000" if silent else "sine=frequency=660:sample_rate=16000"
    subprocess.run(["ffmpeg","-nostdin","-v","error","-y",
        "-f","lavfi","-i","color=c=blue:s=160x90:r=12",
        "-f","lavfi","-i",audio,"-t","1","-c:v","libx264",
        "-preset","ultrafast","-c:a","aac",str(file)],
        capture_output=True,check=True,timeout=30)

def test_real_audible_tone_not_false_silence(tmp_path):
    video=tmp_path/"tone.mp4";make_mp4(video,silent=False)
    result=inspect_mp4(video,audio_required=True)
    assert result.has_audio_stream and result.decoded_audio
    assert result.rms_dbfs>-45
    assert result.non_silent_fraction>0.1
    assert result.verdict=="needs_review"
    assert "speech_language_and_lipsync_unverified" in result.warnings

def test_valid_aac_silence_must_fail_required_audio(tmp_path):
    video=tmp_path/"silent.mp4";make_mp4(video,silent=True)
    result=inspect_mp4(video,audio_required=True)
    assert result.has_audio_stream
    assert result.verdict=="reject"
    assert "silent_or_inaudible_audio" in result.warnings

def test_valid_aac_silence_does_not_mark_video_approved(tmp_path):
    video=tmp_path/"silent.mp4";make_mp4(video,silent=True)
    result=inspect_mp4(video,audio_required=False)
    assert result.verdict=="needs_review"

def test_unsupported_window_rejected(tmp_path):
    with pytest.raises(ValueError):
        inspect_mp4(tmp_path/"none",audio_required=True,sample_seconds=0)
