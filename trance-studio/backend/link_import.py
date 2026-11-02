"""Bounded public social-video import for explicit user initiated link sharing.

Never fetch arbitrary URLs from the server. This importer intentionally only
accepts a short list of public social/video domains with supported extractors.
Private/login/DRM pages fail closed. No browser cookies or account tokens.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

MAX_VIDEO=45*1024*1024
MAX_AUDIO=15*1024*1024
MAX_SECONDS=120.5
ALLOWED_HOSTS=(
    "facebook.com","fb.watch","instagram.com","tiktok.com","tiktokv.com",
    "vimeo.com",
    "twitter.com","x.com","reddit.com","redd.it","dailymotion.com",
    "dai.ly","soundcloud.com","twitch.tv","clips.twitch.tv",
    "pinterest.com","pin.it",
)
MEDIA_EXT={".mp4":"video/mp4",".webm":"video/webm",".mov":"video/quicktime",
           ".m4a":"audio/mp4",".mp3":"audio/mpeg",".ogg":"audio/ogg",
           ".opus":"audio/ogg",".wav":"audio/wav",".flac":"audio/flac",
           ".aac":"audio/aac",".3gp":"video/3gpp",".3gpp":"video/3gpp"}


class LinkImportError(ValueError):
    pass


def validate_public_link(raw):
    value=str(raw or "").strip()
    if not value or len(value)>2048 or any(c.isspace() for c in value):
        raise LinkImportError("יש לשתף קישור HTTPS קצר לתוכן ציבורי יחיד.")
    try:
        url=urlsplit(value)
        host=(url.hostname or "").lower().rstrip(".")
        port=url.port
    except ValueError as exc:
        raise LinkImportError("כתובת הקישור אינה תקינה.") from exc
    if (url.scheme!="https" or not host or url.username or url.password or
            port not in (None,443) or "\\" in value or
            host.startswith("xn--") or
            not any(host==root or host.endswith("."+root)
                    for root in ALLOWED_HOSTS)):
        raise LinkImportError(
            "הקישור אינו מאתר וידאו נתמך לייבוא. ניתן לשתף את קובץ המדיה עצמו.")
    if url.path.startswith("//"):
        raise LinkImportError("כתובת הקישור אינה תקינה.")
    return value


def _media_probe(path):
    try:
        output=subprocess.check_output(
            ["ffprobe","-v","error","-show_entries","format=duration",
             "-of","default=noprint_wrappers=1:nokey=1",str(path)],
            timeout=10,stderr=subprocess.DEVNULL)
        duration=float(output.decode().strip())
        if not 0.15<duration<=MAX_SECONDS:
            raise LinkImportError("משך הסרטון גדול משתי דקות או שאינו תקין.")
    except (ValueError,subprocess.CalledProcessError,subprocess.TimeoutExpired) as exc:
        if isinstance(exc,LinkImportError):raise
        raise LinkImportError("לא התקבל קובץ שמע או וידאו תקין.") from exc
    return duration


def fetch_public_social_media(url, directory, *,timeout=70):
    """Return (path, mime), only for a public single clip within upload limits.

    yt-dlp is run without cookies, playlists, login or arbitrary user flags.
    The importer monitors temporary directory bytes while subprocess runs,
    terminating downloads exceeding the allowed upload budget.
    """
    url=validate_public_link(url)
    folder=Path(directory)
    folder.mkdir(parents=True,exist_ok=True)
    command=[
        sys.executable,"-m","yt_dlp","--ignore-config",
        "--no-playlist","--no-progress","--no-warnings",
        "--no-cache-dir","--no-write-thumbnail","--no-write-subs",
        "--no-write-auto-subs","--restrict-filenames",
        "--max-filesize","45M","--match-filter","duration <= 120",
        "--format","bv*[height<=720][ext=mp4]+ba[ext=m4a]/b[ext=mp4]/"
                   "b[height<=720]/ba[ext=m4a]/bestaudio",
        "--merge-output-format","mp4",
        "--output",str(folder/"shared.%(ext)s"),
        url
    ]
    try:
        proc=subprocess.Popen(command,stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL)
    except (OSError,ValueError) as exc:
        raise LinkImportError("מנוע ייבוא הקישורים אינו זמין כרגע.") from exc
    start=time.monotonic()
    try:
        while proc.poll() is None:
            if time.monotonic()-start>timeout:
                raise LinkImportError("ייבוא הקישור התארך מדי. ניתן להעלות קובץ ישירות.")
            size=sum(p.stat().st_size for p in folder.iterdir() if p.is_file())
            if size>MAX_VIDEO+3*1024*1024:
                raise LinkImportError("הסרטון גדול מהמגבלה של 45MB.")
            time.sleep(.3)
        if proc.returncode!=0:
            raise LinkImportError(
                "לא ניתן לייבא את הקישור. ייתכן שהפוסט פרטי, דורש התחברות, "
                "מוגן או שהרשת אינה מאפשרת הורדה ציבורית.")
        candidates=[p for p in folder.iterdir() if p.is_file()
                    and p.suffix.lower() in MEDIA_EXT and
                    p.name.startswith("shared.")]
        if len(candidates)!=1:
            raise LinkImportError("לא התקבל קובץ מדיה יחיד בפורמט נתמך.")
        result=candidates[0]
        mime=MEDIA_EXT[result.suffix.lower()]
        cap=MAX_VIDEO if mime.startswith("video/") else MAX_AUDIO
        if not 2048<=result.stat().st_size<=cap:
            raise LinkImportError("קובץ המדיה חורג מהמגבלה או שאינו תקין.")
        _media_probe(result)
        return result,mime
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=2)
