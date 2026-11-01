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

def compose_original_video_with_mix(original_paths, music_mp3, output_mp4, work_dir):
    work=Path(work_dir)
    work.mkdir(parents=True,exist_ok=True)
    audio_duration=_duration(music_mp3)
    if not .5<=audio_duration<=360.:
        raise UnavailableVideo("משך המיקס אינו מתאים לסרטון")
    original=None
    for input_path in original_paths:
        source=Path(input_path)
        if source.suffix.lower() not in VIDEO_TYPES or not source.is_file():
            continue
        try:
            _video_profile(source)
            require_visible_motion(source,threshold=.30)
            if _duration(source)<.8:
                continue
            original=source
            break
        except (OSError,ValueError,subprocess.SubprocessError,NoVisibleMotion):
            continue
    if original is None:
        raise UnavailableVideo("קובץ המקור אינו כולל צילום וידאו נע")
    segment=work/"original-verified-motion.mp4"
    _make_segment(original,segment,audio_duration)
    subprocess.run([
        "ffmpeg","-nostdin","-v","error","-y",
        "-i",str(segment),"-i",str(music_mp3),
        "-map","0:v:0","-map","1:a:0","-c:v","copy",
        "-c:a","aac","-b:a","160k","-shortest",
        "-movflags","+faststart",str(output_mp4)
    ],capture_output=True,check=True,timeout=70)
    result=Path(output_mp4)
    if not result.is_file() or result.stat().st_size<12000:
        raise UnavailableVideo("לא ניתן למזג את צילום המקור עם המיקס")
    return {"source":"original_shared_moving_video",
            "video_mode":"original_input_video",
            "visual_coverage":"original_video_not_scene_generated",
            "video_note":"הסרטון מציג את הווידאו המקורי ששיתפת עם המיקס החדש. "
                         "הוא אינו יצירת AI הממחישה את המילים.",
            "video_status":"done"}
