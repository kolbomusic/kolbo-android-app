"""Experimental narration-to-generated-motion fallback using a free public LTX Space.

This sends ONLY an explicitly consented Hebrew text transcript to a community
Hugging Face Gradio Space. It never uploads voice files, login cookies or site
secrets. ZeroGPU quotas / availability are external and cannot be guaranteed.

The result is an original moving AI-generated shot, NOT licensed camera footage,
NOT a verified literal depiction of every spoken event. Output retains the
complete original music and voice and reports approximate visual coverage.
"""
from __future__ import annotations

import json
import re
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from live_video import _duration, _make_segment, _video_profile, visual_plan, UnavailableVideo

SPACE = "https://lightricks-ltx-video-distilled.hf.space"
SPACE_HOST = "lightricks-ltx-video-distilled.hf.space"
SPACE_PAGE = "https://huggingface.co/spaces/Lightricks/ltx-video-distilled"
CALL_PATH = "/gradio_api/call/text_to_video"
MAX_OUTPUT_BYTES = 18 * 1024 * 1024
MAX_WAIT_SECONDS = 210
HEBREW = re.compile(r"[א-ת]{2,}")


class AIVideoUnavailable(RuntimeError):
    """No original generative clip can be produced within the free quota."""


def cinematic_prompt(transcript, max_chars=980):
    """Describe the ACTUAL recognized words, never fabricate missing dialogue."""
    clean = re.sub(r"[\x00-\x1f\x7f]", " ", str(transcript or ""))
    clean = re.sub(r"\s+", " ", clean).strip()[:max_chars]
    if len(HEBREW.findall(clean)) < 2:
        raise AIVideoUnavailable("זיהוי הדיבור אינו מספיק ליצירת סיפור")
    known = []
    try:
        # English keywords supplement the Hebrew original, but never replace
        # unknown words with an invented action or animal.
        plan = visual_plan(clean, 6)
        known = [v["query"] for v in plan["scenes"][:4]
                 if v["basis"]=="subject_and_action"]
    except UnavailableVideo:
        pass
    ordered = "; then ".join(known)
    extra = ("Recognized visual actions, in chronological order: " + ordered +
             ". " if ordered else "")
    return (
        "Photorealistic cinematic live-action moving video. Show the actual "
        "physical events narrated below in chronological order, realistic "
        "moving subjects, natural camera motion and reactions. "
        "Do not invent different events or change the actors. "
        "No written words, captions, titles, waveforms, animation, "
        "still images or illustrations. " + extra +
        "The narration is in HEBREW. Interpret its meaning and depict it: " +
        clean
    )[:1800]


def _video_result_url(data):
    """Decode a Gradio Video FileData result without accepting arbitrary URLs."""
    if not isinstance(data, list) or not data:
        raise AIVideoUnavailable("שירות יצירת הווידאו לא החזיר קובץ")
    item = data[0]
    if isinstance(item, dict) and "video" in item:
        item = item["video"]
    if isinstance(item, dict):
        url = str(item.get("url") or "")
        if not url:
            path = str(item.get("path") or "")
            if path.startswith("/tmp/gradio/") and len(path) < 512:
                url = SPACE + "/gradio_api/file=" + urllib.parse.quote(path)
    elif isinstance(item, str):
        url = item
    else:
        url = ""
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme != "https" or parsed.hostname != SPACE_HOST or
        parsed.username or parsed.password or parsed.port not in (None,443) or
        not parsed.path.startswith("/gradio_api/file=")):
        raise AIVideoUnavailable("כתובת קובץ הווידאו אינה ממקור מאומת")
    return url


def _request_video_generation(prompt, *, opener=urllib.request.urlopen,
                              duration=5.0, max_wait=MAX_WAIT_SECONDS):
    """Call the documented public Gradio queue API with a bounded SSE wait."""
    duration = min(8.0, max(1.0, float(duration)))
    data = {
        "data": [
            prompt,
            "blurry, deformed, text, captions, watermark, anime, illustration",
            "", "", 704, 512, "text-to-video", duration,
            9, 42, True, 1.0, True,
        ]
    }
    request = urllib.request.Request(
        SPACE + CALL_PATH,
        data=json.dumps(data, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "User-Agent": "KolboTranceStudio/2.3"})
    try:
        with opener(request,timeout=25) as response:
            submission = json.loads(response.read(16000))
        event_id = str(submission.get("event_id") or "")
        if not re.fullmatch(r"[a-f0-9]{24,80}",event_id):
            raise AIVideoUnavailable("שירות הווידאו לא החזיר מספר משימה תקין")
        started=time.monotonic()
        req = urllib.request.Request(
            SPACE + CALL_PATH + "/" + event_id,
            headers={"User-Agent":"KolboTranceStudio/2.3",
                     "Accept":"text/event-stream"})
        with opener(req,timeout=min(190,int(max_wait))) as response:
            event = ""
            for raw in response:
                if time.monotonic() - started > max_wait:
                    raise AIVideoUnavailable("התור החינמי ליצירת סרטון הסתיים בזמן")
                line = raw.decode("utf-8",errors="replace").strip()
                if line.startswith("event:"):
                    event = line.split(":",1)[1].strip()
                elif line.startswith("data:"):
                    if event=="error":
                        raise AIVideoUnavailable("שירות הווידאו החינמי דחה את הבקשה")
                    if event=="complete":
                        return _video_result_url(json.loads(line.split(":",1)[1]))
        raise AIVideoUnavailable("שירות הווידאו לא סיים את יצירת הסרטון")
    except AIVideoUnavailable:
        raise
    except (TimeoutError, OSError, ValueError, urllib.error.URLError,
            json.JSONDecodeError) as exc:
        raise AIVideoUnavailable(
            "מנוע יצירת הווידאו החינמי אינו זמין כרגע או שמכסת השימוש הסתיימה"
        ) from exc


def _download_public_video(url, destination, *, opener=urllib.request.urlopen):
    # Only fetch the single trusted Gradio host. Never let the remote output
    # trigger a request to internal addresses (SSRF).
    if _video_result_url([{"video":{"url":url}}]) != url:
        raise AIVideoUnavailable("מקור הסרטון אינו מאומת")
    # Refuse redirects, which could otherwise lead to internal or unsafe URLs.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            raise AIVideoUnavailable("שירות הווידאו שינה את כתובת ההורדה")
    safe_open = urllib.request.build_opener(NoRedirect()).open
    actual_open = safe_open if opener is urllib.request.urlopen else opener
    count=0
    try:
        with actual_open(urllib.request.Request(
                url,headers={"User-Agent":"KolboTranceStudio/2.3"}),
                timeout=55) as response, open(destination,"wb") as output:
            while True:
                part=response.read(65536)
                if not part:
                    break
                count+=len(part)
                if count>MAX_OUTPUT_BYTES:
                    raise AIVideoUnavailable("קובץ הווידאו החינמי גדול מדי")
                output.write(part)
        if count < 12000:
            raise AIVideoUnavailable("הסרטון שנוצר ריק")
        codec,width,height = _video_profile(destination)
        seconds = _duration(destination)
        if not codec or not width or not height or not 0.6 <= seconds <= 12:
            raise AIVideoUnavailable("לא התקבל סרטון נע תקין")
        return seconds
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        Path(destination).unlink(missing_ok=True)
        raise AIVideoUnavailable("לא ניתן לאמת את הווידאו שנוצר") from exc


def generate_ai_story(transcript, audio_mp3, output_mp4, work_dir,
                      *, progress=None, generator=_request_video_generation,
                      download=_download_public_video):
    """Create one ORIGINAL AI shot and mux complete user soundtrack, no subtitles.

    A free shared model cannot produce 35 unique seconds on demand. We loop
    its short generated shot and explicitly report the repeated approximate
    result, instead of falsely marking every spoken scene as matched.
    """
    prompt = cinematic_prompt(transcript)
    output_mp4=Path(output_mp4)
    work=Path(work_dir);work.mkdir(parents=True,exist_ok=True)
    if progress:progress(88,"מתאר את הסיפור המקורי למנוע וידאו AI")
    url=generator(prompt)
    if progress:progress(91,"מקבל את קטע הווידאו החדש שנוצר")
    raw=work/"generated-original.mp4"
    short_seconds=download(url,raw)
    mix_seconds=_duration(audio_mp3)
    if not 1<=mix_seconds<=360:
        raise AIVideoUnavailable("משך המיקס אינו תקין")
    segment=work/"generated-loop.mp4"
    _make_segment(raw,segment,mix_seconds)
    if progress:progress(96,"משלב את הווידאו החדש עם המיקס המקורי")
    args=["ffmpeg","-nostdin","-hide_banner","-loglevel","error","-y",
          "-i",str(segment),"-i",str(audio_mp3),
          "-map","0:v:0","-map","1:a:0","-c:v","copy",
          "-c:a","aac","-b:a","160k","-shortest",
          "-movflags","+faststart",str(output_mp4)]
    try:
        subprocess.run(args,check=True,capture_output=True,timeout=65)
        codec,width,height=_video_profile(output_mp4)
        if (codec,width,height)!=("h264",360,640):
            raise AIVideoUnavailable("פורמט הסרטון אינו תואם לאנדרואיד")
        if output_mp4.stat().st_size<25000:
            raise AIVideoUnavailable("הווידאו שנוצר אינו תקין")
    except (OSError, subprocess.SubprocessError,ValueError) as exc:
        output_mp4.unlink(missing_ok=True)
        raise AIVideoUnavailable("שילוב הווידאו עם הטראנס נכשל") from exc
    return {
        "source":"generated_from_original_hebrew_transcript",
        "video_mode":"ai_generated_experimental",
        "visual_coverage":"approximate",
        "ai_clip_seconds":round(short_seconds,2),
        "audio_seconds":round(mix_seconds,2),
        "repeated_ai_shot":mix_seconds>short_seconds+0.5,
        "sources":[],
        "scenes":[{"action":"ai_generated_narrative",
                   "start":0,"end":round(mix_seconds,2),
                   "basis":"experimental_text_to_video"}],
        "provider":SPACE_PAGE,
    }
