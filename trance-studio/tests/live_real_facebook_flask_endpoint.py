"""Real Facebook URL -> Flask /studio session -> /api/import-link -> valid MP4.

Executes actual production Flask route & actual yt-dlp (NO mocks) against a
publicly viewable National Geographic test reel. No login, no Facebook cookies,
no creating derivative media, no publication. Result bytes are temporary and
deleted immediately after ffprobe. Consent flow stays production-side.
"""
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"backend"))
from app import create_app

URL="https://www.facebook.com/reel/1016464114801712"
BASE="https://kolbo-trance-studio.onrender.com"


def real_flask_video_import():
    started=time.monotonic()
    report={"integration":"real Facebook -> authenticated Flask endpoint -> MP4",
            "mock":False,"success":False}
    with tempfile.TemporaryDirectory(prefix="kolbo-flask-e2e-") as tmp:
        app=create_app({
            "TESTING":False,
            "API_TOKEN":"ephemeral-qa-token-not-production",
            "JOB_DIR":tmp,
            "ALLOWED_ORIGINS":BASE,
        })
        client=app.test_client()
        # Real security: unauthenticated request denied.
        no_session=client.post('/api/import-link',base_url=BASE,
                               json={"url":URL})
        report["unauthenticated_denied"]=no_session.status_code==401
        assert no_session.status_code==401
        # The real /studio GET issues a SameSite=Lax HttpOnly Secure session.
        studio=client.get('/studio',base_url=BASE)
        report["studio_http_ok"]=studio.status_code==200
        assert studio.status_code==200
        assert "kolbo_studio=" in studio.headers.get("Set-Cookie","")
        result=client.post("/api/import-link",json={"url":URL},
                           base_url=BASE,headers={"Origin":BASE},buffered=True)
        report["http_code"]=result.status_code
        report["mime"]=result.mimetype
        if result.status_code!=200:
            report["failure_code"]=(result.json or {}).get("code","unknown")
        else:
            binary=result.get_data()
            report["bytes"]=len(binary)
            with tempfile.TemporaryDirectory() as probe:
                file=Path(probe)/"imported.mp4"
                file.write_bytes(binary)
                info=json.loads(subprocess.check_output(
                    ["ffprobe","-v","error","-show_entries",
                     "format=duration:stream=codec_type","-of","json",str(file)],
                    timeout=18))
                duration=float(info["format"]["duration"])
                video=any(item.get("codec_type")=="video" for item in info.get("streams",[]))
                sound=any(item.get("codec_type")=="audio" for item in info.get("streams",[]))
                report.update({"duration_sec":round(duration,2),"video_stream":video,
                               "audio_stream":sound})
                report["success"]=(report["unauthenticated_denied"]
                                   and report["studio_http_ok"]
                                   and result.mimetype=="video/mp4"
                                   and 2048<=len(binary)<=45*1024*1024
                                   and 0.15<duration<=120.5 and video and sound)
        result.close()
        report["temp_files_cleaned"]=not list(Path(tmp).glob("kolbo-social-*"))
        report["success"]=report["success"] and report["temp_files_cleaned"]
    report["elapsed_seconds"]=round(time.monotonic()-started,2)
    print("REAL_FACEBOOK_FLASK_ENDPOINT_PROOF="+json.dumps(report,ensure_ascii=False),flush=True)
    return report["success"]


if __name__=="__main__":
    raise SystemExit(0 if real_flask_video_import() else 1)
