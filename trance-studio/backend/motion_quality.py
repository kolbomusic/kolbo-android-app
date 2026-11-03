"""Reject static "videos" and ensure visible frame-to-frame motion.

A valid MP4 is not necessarily a moving scene: a repeated still image can
pass ffprobe. Sample a handful of tiny greyscale frames using CPU-bound
FFmpeg (48x48, 5 fps) and check that visual content changes. This is motion
validation, NOT proof that an AI shot semantically matches the original voice.
"""
from __future__ import annotations
import subprocess


class NoVisibleMotion(ValueError):
    pass


def motion_score(video_path, *, timeout=18, start_seconds=0):
    """Return maximum adjacent-frame mean pixel change (0 = static).

    Only 3 seconds starting at a selected valid source offset are decoded at 48x48/5fps and memory stays below
    100KB. The output is bounded and intentionally silent.
    """
    command=[
        "ffmpeg","-nostdin","-hide_banner","-loglevel","error",
        "-ss",str(max(0.0,float(start_seconds))),"-i",str(video_path),
        "-t","3",
        "-map","0:v:0","-vf","fps=5,scale=48:48,format=gray",
        "-frames:v","15","-f","rawvideo","pipe:1"
    ]
    try:
        result=subprocess.run(command,check=True,capture_output=True,
                              timeout=timeout)
    except (OSError, subprocess.SubprocessError) as exc:
        raise NoVisibleMotion("לא ניתן לבדוק תנועה בווידאו שנוצר") from exc
    step=48*48
    raw=result.stdout
    if len(raw)<step*2 or len(raw)%step:
        raise NoVisibleMotion("הקטע קצר מדי או אינו כולל פריימים תקינים")
    frames=[raw[i:i+step] for i in range(0,len(raw),step)]
    return max(
        sum(abs(a-b) for a,b in zip(left,right))/step
        for left,right in zip(frames,frames[1:])
    )


def require_visible_motion(video_path, *, threshold=0.30, start_seconds=0):
    """Do not present a stationary slide as a genuine moving AI scene."""
    score=motion_score(video_path,start_seconds=start_seconds)
    if score<threshold:
        raise NoVisibleMotion("נוצר סרטון סטטי ללא תנועה חזותית מספקת")
    return score


def require_visible_motion_somewhere(video_path, *, duration, threshold=0.30):
    """Validate real motion after a possible title-card intro.

    All real-source video code paths must share the same checks. Returning
    from only the first-three-second validation rejects real videos that
    start with a stationary card. Never accept a completely frozen image,
    and cap CPU work to four short original-video samples.
    """
    duration=float(duration)
    if not .8<=duration<=600:
        raise NoVisibleMotion("משך סרטון המקור אינו תקין")
    for offset in (0,3,8,15):
        if duration<offset+1:
            continue
        try:
            return require_visible_motion(video_path,threshold=threshold,
                                          start_seconds=offset)
        except NoVisibleMotion:
            continue
    raise NoVisibleMotion("קובץ המקור לא מכיל תנועה חזותית מספקת")
