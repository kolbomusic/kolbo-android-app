"""Safely mux small ORIGINAL AI-motion clips produced by the user's browser.

The external model receives only consented transcript/prompt, never voice.
The browser fetches generated MP4s from public Gradio Spaces and uploads the
small resulting media bytes to this same-origin authenticated API. This works
even when cloud-server IPs are denied free public GPU access.

We intentionally do not use arbitrary submitted URLs, create images, subtitles,
waveform visualizations or make factual claims that generated fiction is real.
"""
from __future__ import annotations
import json
import subprocess
from pathlib import Path
import math

from live_video import _duration, _video_profile, _make_segment, UnavailableVideo

MAX_CLIP_BYTES=10*1024*1024
MAX_CLIPS=3


class MobileClipError(ValueError):
    """Uploaded generated video was not safe/usable for a full audio remix."""


def validate_mp4_clip(path):
    """Reject playlists, remote media pointers, still files and oversized inputs."""
    path=Path(path)
    if not path.is_file() or not 12000<=path.stat().st_size<=MAX_CLIP_BYTES:
        raise MobileClipError("קובץ הווידאו שנוצר חסר או גדול מדי")
    with path.open("rb") as f:
        head=f.read(16)
    if len(head)<12 or head[4:8]!=b"ftyp":
        raise MobileClipError("מנוע הווידאו לא החזיר קובץ MP4 אמיתי")
    try:
        codec,w,h=_video_profile(path)
        length=_duration(path)
    except (OSError,subprocess.SubprocessError,ValueError,UnavailableVideo):
        raise MobileClipError("לא ניתן לבדוק את הסרטון שנוצר") from None
    if codec not in ("h264","hevc","vp9","av1","mpeg4") or not (100<=w<=4096 and 100<=h<=4096):
        raise MobileClipError("הווידאו אינו בפורמט נתמך")
    if not .67<=length<=12.5:
        raise MobileClipError("קטע הווידאו חייב להיות בין שנייה ל־12 שניות")
    return length


def combine_mobile_ai_clips(paths,audio_mp3,output_mp4,work_dir,*,weights=None):
    """Mux at most three genuine moving AI clips + the ENTIRE existing MP3.

    Inputs are server-written MP4 files uploaded as bytes, NOT external URLs.
    The output is Android-compatible H264 360x640 + AAC 160k with a single
    bounded encoding pass per small source excerpt.
    """
    if not 1<=len(paths)<=MAX_CLIPS:
        raise MobileClipError("יש לבחור בין קטע וידאו אחד לשלושה")
    work=Path(work_dir)
    work.mkdir(parents=True,exist_ok=True,mode=0o700)
    output=Path(output_mp4)
    seconds=[validate_mp4_clip(p) for p in paths]
    try:
        duration=_duration(audio_mp3)
    except (OSError,ValueError,subprocess.SubprocessError):
        raise MobileClipError("קובץ המיקס המקורי אינו זמין") from None
    if not 1<=duration<=360:
        raise MobileClipError("משך המיקס המקורי אינו תקין")
    # Preserve spoken order and use original narration word counts for
    # relative screen time, not an arbitrary 50/50 cut. We cannot infer exact
    # vocal positions inside the remixed audio; still label as approximate.
    if weights is None:
        weights=[1.0]*len(paths)
    if (len(weights)!=len(paths) or any(
            isinstance(w,bool) or not isinstance(w,(float,int)) or
            not math.isfinite(float(w)) or not 0.1<=float(w)<=400
            for w in weights)):
        raise MobileClipError("משקל התזמון של סצנות הווידאו אינו תקין")
    total=float(sum(weights))
    allocations=[duration*float(w)/total for w in weights]
    if min(allocations)<.7:
        raise MobileClipError("אורך אחת מסצנות הווידאו קצר מדי")
    parts=[]
    try:
        for i,path in enumerate(paths):
            length=allocations[i] if i<len(paths)-1 else duration-sum(allocations[:-1])
            segment=work/f"mobile-scene-{i}.mp4"
            _make_segment(path,segment,length)
            parts.append(segment)
        if len(parts)>1:
            manifest=work/"mobile-concat.txt"
            manifest.write_text("".join("file '"+p.name+"'\n" for p in parts),encoding="utf-8")
            silent=work/"mobile-silent.mp4"
            subprocess.run(["ffmpeg","-nostdin","-hide_banner","-loglevel","error","-y",
                            "-f","concat","-safe","0","-i",str(manifest),
                            "-c","copy",str(silent)],
                           cwd=work,check=True,capture_output=True,timeout=50)
        else:
            silent=parts[0]
        subprocess.run(["ffmpeg","-nostdin","-hide_banner","-loglevel","error","-y",
                        "-i",str(silent),"-i",str(audio_mp3),
                        "-map","0:v:0","-map","1:a:0","-c:v","copy",
                        "-c:a","aac","-b:a","160k","-shortest",
                        "-movflags","+faststart",str(output)],
                       capture_output=True,check=True,timeout=75)
        codec,w,h=_video_profile(output)
        final_length=_duration(output)
        if (codec,w,h)!=("h264",360,640) or final_length<duration-.8 or final_length>duration+1.5:
            raise MobileClipError("הסרטון המוכן אינו תואם לאנדרואיד או למשך המיקס")
        if output.stat().st_size<25000:
            raise MobileClipError("קובץ ה־MP4 שנוצר קטן מדי")
    except MobileClipError:
        output.unlink(missing_ok=True)
        raise
    except (OSError,subprocess.SubprocessError,ValueError,UnavailableVideo) as exc:
        output.unlink(missing_ok=True)
        raise MobileClipError("לא ניתן לשלב את קטעי הווידאו עם המיקס") from exc
    return {
        "source":"mobile_direct_public_ai",
        "video_mode":"ai_generated_client_fallback",
        "visual_coverage":"approximate",
        "ai_clips_generated":len(paths),
        "audio_seconds":round(duration,2),
        "ai_clip_seconds":round(sum(seconds),2),
        "repeated_ai_shot":any(allocations[i]>n+.5 for i,n in enumerate(seconds)),
        "sources":[],
        "pacing_basis":"original_transcript_spoken_word_counts",
        "scenes":[
            {"action":"original_ai_generated_motion",
             "start":round(sum(allocations[:i]),2),
             "end":round(sum(allocations[:i+1]),2),
             "basis":"consented_browser_text_to_video",
             "original_motion_seconds":round(seconds[i],2)}
            for i in range(len(paths))
        ],
    }
