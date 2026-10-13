#!/usr/bin/env python3
"""Exactly one anonymous synthetic test on a public Wan Space. No private media.

No HF_TOKEN, retries, paid fallback, second submission, or automatic API-key use.
This is experimental: a submitted queue job does not imply rendered video.
"""
from __future__ import annotations
import hashlib
import json
import math
import shutil
import subprocess
import time
from pathlib import Path

SPACE = "zerogpu-aoti/wan2-2-fp8da-aoti-faster"
API = "/generate_video"
PARAMS = ["input_image", "prompt", "steps", "negative_prompt", "duration_seconds",
          "guidance_scale", "guidance_scale_2", "seed", "randomize_seed"]
OUT = Path("wan-fast-proof")
PROMPT = ("A yellow paper square made of origami gently folds into a paper boat "
          "and floats over a dark blue tabletop. Clear continuous physical motion, "
          "locked off camera, realistic illumination, no people, no writing.")

def media_path(output):
    """Locate a local generated video in the documented Gradio output structure."""
    if isinstance(output, dict):
        for key in ("video","path"):
            if key in output:
                found = media_path(output[key])
                if found: return found
        return None
    if isinstance(output,(tuple,list)):
        for item in output:
            found = media_path(item)
            if found:return found
        return None
    if isinstance(output,str) and not output.startswith(("http:","https:","file:")):
        try:
            path=Path(output)
            if path.suffix.lower() in (".mp4",".webm",".mov") and path.is_file() and not path.is_symlink():
                return path
        except (OSError,ValueError):
            pass
    return None

def validate_video(path:Path)->dict:
    result={"valid_video_stream":False,"motion_detected":False,"duration_seconds":None,
            "audio_track_present":False,"sha256":None}
    if path.is_symlink() or not 4096 < path.stat().st_size <= 120_000_000:
        return result
    inspect=subprocess.run(["ffprobe","-v","error","-show_entries",
        "stream=codec_type:format=duration","-of","json",str(path)],
        capture_output=True,text=True,timeout=20,check=True)
    meta=json.loads(inspect.stdout)
    seconds=float(meta.get("format",{}).get("duration",0))
    videos=[s for s in meta.get("streams",[]) if s.get("codec_type")=="video"]
    result["audio_track_present"]=any(s.get("codec_type")=="audio" for s in meta.get("streams",[]))
    if not videos or not math.isfinite(seconds) or not 0.5 <= seconds <= 15:
        return result
    result["valid_video_stream"]=True
    result["duration_seconds"]=round(seconds,3)
    frames=subprocess.run(["ffmpeg","-nostdin","-v","error","-i",str(path),"-map","0:v:0",
       "-an","-vf","fps=2,scale=48:48,format=gray","-f","rawvideo","pipe:1"],
       capture_output=True,timeout=25,check=True).stdout
    width=48*48
    if len(frames) < width*3 or len(frames)%width:
        return result
    sections=[frames[i:i+width] for i in range(0,len(frames),width)]
    deltas=[sum(abs(a-b) for a,b in zip(u,v))/width for u,v in zip(sections,sections[1:])]
    result["motion_detected"]=sum(x>=2.5 for x in deltas)>=2
    with path.open("rb") as source:
        result["sha256"]=hashlib.file_digest(source,"sha256").hexdigest()
    return result

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    receipt={"provider":SPACE,"api_name":API,"synthetic_input_only":True,"private_media_uploaded":False,
             "charged_fallback":False,"hf_auth_token_used":False,"requests_submitted":0,
             "generated_video_verified":False,"generated_audio_verified":False,
             "provider_compute_unlimited":False}
    begin=time.monotonic()
    try:
        from gradio_client import Client, handle_file
        if not Path("kolbo-synthetic-input.png").is_file():
            raise FileNotFoundError("Missing synthetic image")
        client=Client(SPACE,verbose=False)
        contract=client.view_api(return_format="dict")
        endpoint=(contract.get("named_endpoints") or {}).get(API)
        if not isinstance(endpoint,dict):
            raise ValueError("Expected endpoint unavailable")
        names=[entry.get("parameter_name") for entry in endpoint.get("parameters",[])]
        if names != PARAMS:
            raise ValueError("API contract differs: declining to submit")
        # All request fields are synthetic/public: only one job, never retried.
        receipt["requests_submitted"]=1
        job=client.submit(
            handle_file("kolbo-synthetic-input.png"),PROMPT,8,
            "distorted scene, text, watermark, static video",2.0,
            3.5,3.5,42,False,api_name=API)
        deadline=time.monotonic()+360
        while not job.done() and time.monotonic()<deadline:
            time.sleep(3)
        if not job.done():
            job.cancel()
            raise TimeoutError("Public provider job exceeded 360s")
        output=job.result()
        path=media_path(output)
        if path is None:
            raise ValueError("Provider returned no local video file")
        evidence=validate_video(path)
        receipt["video_evidence"]=evidence
        if not (evidence["valid_video_stream"] and evidence["motion_detected"]):
            raise ValueError("Missing decoded moving-video proof")
        dest=OUT/"wan-fast-synthetic-ai.mp4"
        shutil.copyfile(path,dest)
        receipt["generated_video_verified"]=True
        receipt["provider_model_inference_claimed"]=True
        receipt["generated_audio_verified"]=False
        receipt["output_bytes"]=dest.stat().st_size
    except Exception as exc:
        receipt["failure_type"]=type(exc).__name__
    finally:
        receipt["wall_seconds"]=round(time.monotonic()-begin,2)
        (OUT/"receipt.json").write_text(json.dumps(receipt,ensure_ascii=False,indent=2))
        print(json.dumps(receipt,ensure_ascii=False,indent=2))
    return 0 if receipt["generated_video_verified"] else 1

if __name__=="__main__":
    raise SystemExit(main())
