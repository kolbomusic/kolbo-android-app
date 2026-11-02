"""Real, non-mocked public Facebook /share/v/ video regression, no saved media."""
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"backend"))
import link_import

# Both are publicly documented short-share/video ID pairs. One failure does
# not imply the entire importer is unavailable; record individual outcomes.
PUBLIC_TESTS=(
    ("https://www.facebook.com/share/v/1NpnVb9ghX/","1480256363681360"),
    ("https://www.facebook.com/share/v/1AQTkKfH1u/","1972277293595444"),
)


def attempt(link,expected):
    t=time.monotonic()
    proof={"kind":"public Facebook share/v", "expected_id":expected,
           "mock":False,"success":False}
    try:
        candidates=link_import._facebook_public_candidates(link,timeout=9)
        proof["recognized_correct_video"]=any(
            link_import._facebook_video_id(u)==expected for u in candidates)
        proof["candidate_count"]=len(candidates)
        with tempfile.TemporaryDirectory(prefix="kolbo-share-v-") as directory:
            file,mime=link_import.fetch_public_social_media(
                link,directory,timeout=72)
            p=Path(file)
            meta=json.loads(subprocess.check_output(
                ["ffprobe","-v","error","-show_entries",
                 "format=duration:stream=codec_type","-of","json",str(p)],
                timeout=12))
            duration=float(meta["format"]["duration"])
            streams={x.get("codec_type") for x in meta.get("streams",[])}
            proof.update({"mime":mime,"bytes":p.stat().st_size,
                          "duration_sec":round(duration,2),
                          "video_stream":"video" in streams,
                          "audio_stream":"audio" in streams})
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
    print("REAL_FACEBOOK_SHORT_SHARE_VIDEO_PROOF="+json.dumps(proof),
          flush=True)
    return proof["success"]


def main():
    proofs=[]
    for link,expected in PUBLIC_TESTS:
        ok=attempt(link,expected)
        proofs.append(ok)
        if ok:break
    print("REAL_SHORT_SHARE_ANY_MP4_PASSED="+str(any(proofs)),flush=True)
    return any(proofs)


if __name__=="__main__":
    raise SystemExit(0 if main() else 1)
