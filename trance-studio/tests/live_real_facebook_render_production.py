"""Prove deployed production Render import, without saving or publishing user media.

A public National Geographic video is used solely as a transient regression clip.
This check authenticates via the production /studio session cookie; it does not
use API keys, social cookies, CAPTCHA, or any private-media workaround.
"""
import http.cookiejar
import json
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPCookieProcessor, Request, build_opener

BASE="https://kolbo-trance-studio.onrender.com"
PUBLIC_VIDEO="https://www.facebook.com/reel/1016464114801712"


def real_production_import():
    start=time.monotonic()
    report={"test":"production Render /studio -> authenticated import -> verified MP4",
            "mock":False,"success":False}
    client=build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
    try:
        with client.open(Request(BASE+"/studio",headers={"User-Agent":"KolboQA/1.0"}),
                         timeout=75) as landing:
            report["studio_http"]=landing.status
            html=landing.read(400000)
        if report["studio_http"]!=200 or b'id="importLink"' not in html:
            raise ValueError("Production studio import UI missing")
        request=Request(
            BASE+"/api/import-link",method="POST",
            data=json.dumps({"url":PUBLIC_VIDEO}).encode("utf-8"),
            headers={"Content-Type":"application/json",
                     "Origin":BASE,"User-Agent":"KolboQA/1.0"},
        )
        try:
            with client.open(request,timeout=120) as response:
                report["http_code"]=response.status
                report["mime"]=response.headers.get_content_type()
                binary=response.read(46*1024*1024)
        except HTTPError as error:
            report["http_code"]=error.code
            try:
                body=json.loads(error.read(4096).decode("utf-8","replace"))
            except (ValueError,UnicodeError):
                body={}
            report["failure_code"]=body.get("code","unknown")
            report["failure_trace"]=body.get("trace_id","")
            raise ValueError("Production import endpoint rejected the test") from error
        if report["mime"]!="video/mp4":
            raise ValueError("Production returned non-MP4 media")
        if not 2048<=len(binary)<=45*1024*1024:
            raise ValueError("Media size exceeded agreed limit")
        with tempfile.TemporaryDirectory(prefix="kolbo-production-fb-") as tmp:
            path=Path(tmp)/"import.mp4"
            path.write_bytes(binary)
            media=json.loads(subprocess.check_output(
                ["ffprobe","-v","error","-show_entries",
                 "format=duration:stream=codec_type",
                 "-of","json",str(path)],timeout=20))
            duration=float(media["format"]["duration"])
            codecs={stream.get("codec_type") for stream in media.get("streams",[])}
            report.update({"bytes":len(binary),"duration_sec":round(duration,2),
                           "video_stream":"video" in codecs,
                           "audio_stream":"audio" in codecs})
            report["success"]=(0.15<duration<=120.5
                               and "video" in codecs and "audio" in codecs)
    except (HTTPError,URLError,OSError,ValueError,KeyError,
            subprocess.SubprocessError) as error:
        report.setdefault("failure_kind",type(error).__name__)
    report["elapsed_seconds"]=round(time.monotonic()-start,2)
    print("REAL_PRODUCTION_FACEBOOK_IMPORT_PROOF="
          +json.dumps(report,ensure_ascii=False),flush=True)
    return report["success"]


if __name__=="__main__":
    raise SystemExit(0 if real_production_import() else 1)
