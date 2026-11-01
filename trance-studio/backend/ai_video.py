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
SECONDARY_SPACE = "https://lightricks-ltx-2-5.hf.space"
SECONDARY_HOST = "lightricks-ltx-2-5.hf.space"
SECONDARY_PAGE = "https://huggingface.co/spaces/Lightricks/LTX-2.5"
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


def _video_result_url(data, *, expected_host=SPACE_HOST):
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
                url = "https://" + expected_host + "/gradio_api/file=" + urllib.parse.quote(path)
    elif isinstance(item, str):
        url = item
    else:
        url = ""
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme != "https" or parsed.hostname != expected_host or
        parsed.username or parsed.password or parsed.port not in (None,443) or
        not parsed.path.startswith("/gradio_api/file=")):
        raise AIVideoUnavailable("כתובת קובץ הווידאו אינה ממקור מאומת")
    return url


def _request_video_generation(prompt, *, opener=urllib.request.urlopen,
                              duration=2.0, max_wait=MAX_WAIT_SECONDS):
    """Call the documented public Gradio queue API with a bounded SSE wait."""
    duration = min(3.0, max(1.0, float(duration)))
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


def _request_ltx25_generation(prompt, *, opener=urllib.request.urlopen,
                              duration=2.0, max_wait=MAX_WAIT_SECONDS):
    """Second *verified* public ZeroGPU video generation engine.

    LTX 2.5 accepts a named JSON object, NOT the older positional Gradio
    data array used by the distilled space. Both public endpoints were
    independently checked with a real generated 1s video in GitHub Actions.
    """
    payload={
        "prompt":str(prompt)[:1800],
        "image_path":None,
        "height":512,
        "width":768,
        "duration_s":min(3.0,max(1.0,float(duration))),
        "seed":42,
        "decoder":"conv",
        "auto_len":False,
        "randomize_seed":False,
        "do_enhance":False,
    }
    req=urllib.request.Request(
        SECONDARY_SPACE+"/gradio_api/call/v2/run",
        data=json.dumps(payload,ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type":"application/json",
                 "User-Agent":"KolboTranceStudio/2.4"})
    try:
        with opener(req,timeout=25) as response:
            event=json.loads(response.read(16000))
        event_id=str(event.get("event_id") or "")
        if not re.fullmatch(r"[a-f0-9]{24,80}",event_id):
            raise AIVideoUnavailable("מנוע הווידאו השני לא החזיר משימה תקינה")
        request=urllib.request.Request(
            SECONDARY_SPACE+"/gradio_api/call/run/"+event_id,
            headers={"Accept":"text/event-stream",
                     "User-Agent":"KolboTranceStudio/2.4"})
        began=time.monotonic()
        with opener(request,timeout=min(190,int(max_wait))) as response:
            event_type=""
            for raw in response:
                if time.monotonic()-began>max_wait:
                    raise AIVideoUnavailable("הבקשה למנוע הווידאו השני נמשכה זמן רב מדי")
                line=raw.decode("utf-8",errors="replace").strip()
                if line.startswith("event:"):
                    event_type=line.split(":",1)[1].strip()
                elif line.startswith("data:"):
                    if event_type=="error":
                        raise AIVideoUnavailable("גם מנוע הווידאו השני אינו זמין כעת")
                    if event_type=="complete":
                        return _video_result_url(
                            json.loads(line.split(":",1)[1]),
                            expected_host=SECONDARY_HOST)
        raise AIVideoUnavailable("מנוע הווידאו השני לא השלים את הסרטון")
    except AIVideoUnavailable:
        raise
    except (TimeoutError,OSError,ValueError,urllib.error.URLError,
            json.JSONDecodeError) as exc:
        raise AIVideoUnavailable("מנוע הווידאו השני אינו זמין או מוגבל כעת") from exc


def _download_public_video(url, destination, *, opener=urllib.request.urlopen):
    # Only fetch the single trusted Gradio host. Never let the remote output
    # trigger a request to internal addresses (SSRF).
    parsed=urllib.parse.urlsplit(url)
    if parsed.hostname not in (SPACE_HOST,SECONDARY_HOST):
        raise AIVideoUnavailable("מקור הסרטון אינו מאומת")
    if _video_result_url([{"video":{"url":url}}],expected_host=parsed.hostname) != url:
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


def _narrative_shots(transcript):
    """Keep the spoken sequence and split at most two coherent visual moments.

    Two real AI-generated shots are more useful than looping one unrelated
    second repeatedly. A ZeroGPU free visitor cannot request unlimited shots.
    """
    text=re.sub(r"\s+"," ",str(transcript or "")).strip()
    clauses=[v.strip(" .,!;:") for v in re.split(
        r"(?<=[.!?;,])\s+|\b(?:ואז|לאחר מכן|ואחר כך|אחר כך|פתאום)\b",text)
        if len(HEBREW.findall(v))>=2]
    if len(clauses)<2 and len(text.split())>=16:
        words=text.split()
        half=max(2,len(words)//2)
        clauses=[" ".join(words[:half])," ".join(words[half:])]
    if not clauses:
        clauses=[text]
    if len(clauses)<=2:
        return clauses
    cut=max(1,len(clauses)//2)
    return [" ".join(clauses[:cut])," ".join(clauses[cut:])]


def generate_ai_story(transcript, audio_mp3, output_mp4, work_dir,
                      *, progress=None, generator=_request_video_generation,
                      download=_download_public_video):
    """Produce up to two original moving shots in spoken order with entire audio.

    Original narration is sent as text ONLY after the app opt-in. Two shots
    are attempted within the public ZeroGPU quota; if the second fails, use
    the first and clearly report an incomplete visual recreation.
    """
    shots = _narrative_shots(transcript)
    output_mp4=Path(output_mp4)
    work=Path(work_dir);work.mkdir(parents=True,exist_ok=True)
    audio_length=_duration(audio_mp3)
    if not 1<=audio_length<=360:
        raise AIVideoUnavailable("משך המיקס אינו תקין")
    prepared=[]
    failure=None
    for index, words in enumerate(shots):
        if progress:
            progress(88+index*3,"מייצר סצנת AI חדשה " + str(index+1) +
                     " מתוך " + str(len(shots)))
        try:
            prompt=cinematic_prompt(words)
            try:
                url=generator(prompt)
            except AIVideoUnavailable:
                if generator is not _request_video_generation:
                    raise
                # Two verified free video Spaces, then a shorter original
                # request. No credit card, paid API key or private audio.
                try:
                    url=_request_ltx25_generation(prompt,duration=2.0)
                except AIVideoUnavailable:
                    try:
                        # LTX 2.5 was independently verified producing a
                        # real 25-frame original motion clip at exactly 1s.
                        url=_request_ltx25_generation(prompt,duration=1.0)
                    except AIVideoUnavailable:
                        url=generator(prompt,duration=1.0)
            raw=work/f"generated-original-{index}.mp4"
            seconds=download(url,raw)
            prepared.append((words,raw,seconds))
        except AIVideoUnavailable as exc:
            failure=exc
            # Subsequent requests to the same exhausted quota will not help.
            break
    if not prepared:
        raise failure or AIVideoUnavailable("שירות יצירת הווידאו החינמי אינו זמין")
    duration_seconds=sum(max(1,len(HEBREW.findall(clip[0])))
                         for clip in prepared)
    encoded=[]
    sources=[]
    for index,(words,raw,source_seconds) in enumerate(prepared):
        spoken_weight=max(1,len(HEBREW.findall(words)))
        allocated=audio_length*spoken_weight/duration_seconds
        segment=work/f"generated-segment-{index}.mp4"
        _make_segment(raw,segment,allocated)
        encoded.append(segment)
        sources.append({
            "action":"ai_generated_narrative",
            "start":round(audio_length*sum(
                max(1,len(HEBREW.findall(x[0]))) for x in prepared[:index]) /
                duration_seconds,2),
            "end":round(audio_length*sum(
                max(1,len(HEBREW.findall(x[0]))) for x in prepared[:index+1]) /
                duration_seconds,2),
            "basis":"experimental_text_to_video",
            "original_motion_seconds":round(source_seconds,2)
        })
    if progress:
        progress(95,"מחבר את סצנות ה־AI ומוסיף את כל המיקס המקורי")
    if len(encoded)>1:
        manifest=work/"generated-manifest.txt"
        manifest.write_text("".join(
            "file '"+segment.name+"'\n" for segment in encoded),
            encoding="utf-8")
        silent=work/"generated-silent.mp4"
        try:
            subprocess.run([
                "ffmpeg","-nostdin","-hide_banner","-loglevel","error","-y",
                "-f","concat","-safe","0","-i",str(manifest),
                "-c","copy",str(silent)],cwd=work,capture_output=True,
                check=True,timeout=50)
        except (OSError,subprocess.SubprocessError) as exc:
            raise AIVideoUnavailable("לא ניתן לחבר את סצנות הווידאו שנוצרו") from exc
    else:
        silent=encoded[0]
    args=["ffmpeg","-nostdin","-hide_banner","-loglevel","error","-y",
          "-i",str(silent),"-i",str(audio_mp3),
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
        duration=_duration(output_mp4)
        if duration<max(0.7,audio_length-0.5):
            raise AIVideoUnavailable("משך הווידאו קצר מדי ביחס למיקס")
    except (OSError, subprocess.SubprocessError,ValueError) as exc:
        output_mp4.unlink(missing_ok=True)
        raise AIVideoUnavailable("שילוב הווידאו עם הטראנס נכשל") from exc
    return {
        "source":"generated_from_original_hebrew_transcript",
        "video_mode":"ai_generated_experimental",
        "visual_coverage":"approximate",
        "ai_clip_seconds":round(sum(item[2] for item in prepared),2),
        "ai_clips_generated":len(prepared),
        "ai_clips_requested":len(shots),
        "audio_seconds":round(audio_length,2),
        "repeated_ai_shot":any(
            sources[i]["end"]-sources[i]["start"]>shot[2]+.5
            for i,shot in enumerate(prepared)),
        "sources":[],
        "scenes":sources,
        "provider":SPACE_PAGE+" | "+SECONDARY_PAGE,
    }
