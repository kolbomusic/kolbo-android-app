"""Live public Facebook import acceptance, not mocked. Retains NO media.

The video URL is a public National Geographic Facebook Reel whose landing page
can be opened without signing in. Use a single bounded import attempt.
Never archives or republishes the source video; checks codec and media bytes,
then deletes the temporary file.
"""
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"backend"))
from link_import import fetch_public_social_media, LinkImportError

PUBLIC_VIDEO="https://www.facebook.com/reel/1016464114801712"

def proof():
    start=time.monotonic()
    result={"public_test":"National Geographic public reel 1016464114801712",
            "mock":False,"success":False,"test":"actual Facebook source -> MP4"}
    with tempfile.TemporaryDirectory(prefix="kolbo-real-public-fb-") as tmp:
        try:
            path,mime=fetch_public_social_media(PUBLIC_VIDEO,tmp,timeout=75)
            data=Path(path)
            size=data.stat().st_size
            probe=subprocess.check_output(
                ["ffprobe","-v","error","-show_entries",
                 "format=duration:stream=codec_type,codec_name",
                 "-of","json",str(data)],timeout=18)
            info=json.loads(probe)
            duration=float(info["format"]["duration"])
            streams=info.get("streams",[])
            valid=(mime=="video/mp4" and 2048<=size<=45*1024*1024
                   and 0.15<duration<=120.5
                   and any(s.get("codec_type")=="video" for s in streams))
            result.update({"success":bool(valid),"mime":mime,"bytes":size,
                           "duration_sec":round(duration,2),
                           "video_stream":any(s.get("codec_type")=="video" for s in streams),
                           "audio_stream":any(s.get("codec_type")=="audio" for s in streams),
                           "file_validated":bool(valid)})
        except LinkImportError as exc:
            result.update({"failure_code":exc.code,
                           "attempts":exc.attempts,
                           "failure_category":"upstream_or_extraction"})
        except (OSError,subprocess.SubprocessError,ValueError,KeyError) as exc:
            result.update({"failure_code":type(exc).__name__,
                           "failure_category":"media_probe"})
    result["elapsed_seconds"]=round(time.monotonic()-start,2)
    print("REAL_PUBLIC_FACEBOOK_IMPORT_PROOF="+json.dumps(result,ensure_ascii=False),flush=True)
    return result["success"]

if __name__=="__main__":
    raise SystemExit(0 if proof() else 1)
