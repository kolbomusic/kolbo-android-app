"""Reliable video fallback when the USER supplied an actual moving video.

No generative model, third-party footage, cartoon, waveform or invented scene.
Only a real moving video track from the original WhatsApp upload can be used.
The existing trance mix replaces the source soundtrack. A voice-only OPUS,
WAV or static picture cannot qualify; do not claim it is a newly filmed event.
"""
from pathlib import Path
import subprocess
from live_video import _make_segment, _duration, _video_profile, UnavailableVideo
from motion_quality import require_visible_motion, NoVisibleMotion

VIDEO_TYPES={".mp4",".webm",".3gp",".3gpp",".mov"}

def compose_original_video_with_mix(original_paths, music_mp3, output_mp4, work_dir,
                                    bpm=145, transcript_hint="",
                                    fx_timeline=None,humor="auto",
                                    fx_intensity=2,progress=None):
    work=Path(work_dir)
    work.mkdir(parents=True,exist_ok=True)
    audio_duration=_duration(music_mp3)
    if not .5<=audio_duration<=360.:
        raise UnavailableVideo("משך המיקס אינו מתאים לסרטון")
    original=None
    original_index=0
    for index,input_path in enumerate(original_paths):
        source=Path(input_path)
        if source.suffix.lower() not in VIDEO_TYPES or not source.is_file():
            continue
        try:
            _video_profile(source)
            require_visible_motion(source,threshold=.30)
            if _duration(source)<.8:
                continue
            original=source
            original_index=index
            break
        except (OSError,ValueError,subprocess.SubprocessError,NoVisibleMotion):
            continue
    if original is None:
        raise UnavailableVideo("קובץ המקור אינו כולל צילום וידאו נע")
    # An original WhatsApp video now receives an actual edited video
    # treatment. Do NOT just paste the MP3 over untouched frames.
    from beat_video_editor import compose_edited_original_video
    return compose_edited_original_video(
        original,music_mp3,output_mp4,work/"beat-edit",
        bpm=bpm,transcript_hint=transcript_hint,
        fx_timeline=fx_timeline,humor=humor,fx_intensity=fx_intensity,
        source_file_index=original_index,progress=progress)
