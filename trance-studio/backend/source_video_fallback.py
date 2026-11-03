"""Reliable video fallback when the USER supplied an actual moving video.

No generative model, third-party footage, cartoon, waveform or invented scene.
Only a real moving video track from the original WhatsApp upload can be used.
The existing trance mix replaces the source soundtrack. A voice-only OPUS,
WAV or static picture cannot qualify; do not claim it is a newly filmed event.
"""
from pathlib import Path
import subprocess
from live_video import _make_segment, _duration, _video_profile, UnavailableVideo
from motion_quality import require_visible_motion_somewhere, NoVisibleMotion

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
    rejections=set()
    seen_video=False
    for index,input_path in enumerate(original_paths):
        source=Path(input_path)
        if source.suffix.lower() not in VIDEO_TYPES or not source.is_file():
            continue
        seen_video=True
        try:
            _video_profile(source)
            source_duration=_duration(source)
            if source_duration<.8:
                rejections.add("too_short")
                continue
            # Talking-face footage can move subtly over a nearly static
            # background. .15 rejects a true frozen video but is less
            # aggressive than the .30 threshold for generated AI clips.
            require_visible_motion_somewhere(
                source,duration=source_duration,threshold=.15)
            original=source
            original_index=index
            break
        except NoVisibleMotion:
            rejections.add("not_moving")
        except UnavailableVideo:
            rejections.add("no_video_track")
        except (OSError,ValueError,subprocess.SubprocessError):
            rejections.add("unsupported_codec")
    if original is None:
        if not seen_video:
            raise UnavailableVideo("ההקלטה מכילה שמע בלבד, ללא ערוץ וידאו מקורי")
        if "not_moving" in rejections:
            raise UnavailableVideo("בקובץ המקורי לא זוהתה תנועת תמונה מספקת")
        if "no_video_track" in rejections:
            raise UnavailableVideo("קובץ המקור אינו מכיל ערוץ תמונה שניתן לפענוח")
        if "too_short" in rejections:
            raise UnavailableVideo("סרטון המקור קצר מדי לעריכה")
        raise UnavailableVideo("לא ניתן לפענח את ערוץ התמונה בסרטון המקור")
    # Prefer accurate sample-timed edits of the ORIGINAL moving video.
    # If the expensive multi-pass editor fails after a valid video was
    # verified, rescue the real footage via a bounded single FFmpeg pass
    # rather than silently returning audio only. Never imply this fallback
    # is per-phoneme AI motion synchronization.
    from beat_video_editor import (compose_edited_original_video,
                                    compose_simple_original_video_fallback)
    try:
        return compose_edited_original_video(
            original,music_mp3,output_mp4,work/"beat-edit",
            bpm=bpm,transcript_hint=transcript_hint,
            fx_timeline=fx_timeline,humor=humor,fx_intensity=fx_intensity,
            source_file_index=original_index,progress=progress)
    except (UnavailableVideo,NoVisibleMotion,OSError,ValueError,
            subprocess.SubprocessError) as first_error:
        Path(output_mp4).unlink(missing_ok=True)
        if progress:
            progress(90,"עריכת הווידאו המתקדמת לא הצליחה; מנסה עיבוד גיבוי של צילום המקור")
        try:
            return compose_simple_original_video_fallback(
                original,music_mp3,output_mp4,work/"simple-rescue",bpm=bpm)
        except (UnavailableVideo,NoVisibleMotion,OSError,ValueError,
                subprocess.SubprocessError) as rescue_error:
            # Do not log/return absolute file paths or internal FFmpeg stderr.
            raise UnavailableVideo(
                "מקור הווידאו זוהה, אך העריכה המתקדמת ועריכת הגיבוי נכשלו. "
                "נסה קובץ MP4 מקורי אחר או סרטון AI ניסיוני מהדיבור."
            ) from rescue_error
