"""Real public Facebook share/v link media acceptance, no mocks or stored media."""
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"backend"))
import link_import

SHORT_LINK="https://www.facebook.com/share/v/1NpnVb9ghX/"
EXPECTED_ID="1480256363681360"

def run():
    t=time.monotonic()
    proof={"path_type":"facebook share/v","mock":False,"success":False}
    try:
        candidates=link_import._facebook_public_candidates(SHORT_LINK,timeout=8)
        proof["recognized_correct_video"]=any(
            link_import._facebook_video_id(u)==EXPECTED_ID for u in candidates)
        proof["candidate_count"]=len(candidates)
        with tempfile.TemporaryDirectory(prefix="kolbo-share-v-") as directory:
            file,mime=link_import.fetch_public_social_media(
                SHORT_LINK,directory,timeout=70)
            p=Path(file)
            meta=json.loads(subprocess.check_output(
                ["ffprobe","-v","error","-show_entries",
                 "format=duration:stream=codec_type","-of","json",str(p)],
                timeout=12))
            duration=float(meta["format"]["duration"])
            streams={x.get("codec_type") for x in meta.get("streams",[])}
            proof.update({"mime":mime,"bytes":p.stat().st_size,
                          "duration_sec":round(duration,2),
                          "has_video":"video" in streams,
                          "has_audio":"audio" in streams})
            proof["success"]=(proof["recognized_correct_video"]
                               and mime=="video/mp4"
                               and 2048<=p.stat().st_size<=45*1024*1024
                               and 0.15<duration<=120.5
                               and "video" in streams and "audio" in streams)
    except link_import.LinkImportError as exc:
        proof.update({"error_code":exc.code,"attempts":exc.attempts})
    except (OSError,subprocess.SubprocessError,ValueError,KeyError) as exc:
        proof["error_kind"]=type(exc).__name__
    proof["elapsed_sec"]=round(time.monotonic()-t,2)
    print("REAL_SHORT_FACEBOOK_SHARE_V_PROOF="+json.dumps(proof),flush=True)
    return proof["success"]

if __name__=="__main__":
    raise SystemExit(0 if run() else 1)
