"""One noncommercial anonymous Wan2.2 inference. Synthetic prompt, never a private image.
Submit at most once. No paid API, no token, no quota circumvention.
A receipt is PASS only after ffprobe confirms a genuinely produced video stream.
"""
from __future__ import annotations
import json,hashlib,os,shutil,subprocess,time
from pathlib import Path
PROVIDER="OpenKing/wan2-video-generation"
def evidence():
    receipt={"provider":PROVIDER,"requests_submitted":0,"private_images_uploaded":False,
             "paid_fallback":False,"gpu_generated_video_verified":False,
             "no_quota_guarantee":True,"audio_model_provided":False}
    target=Path("wan22-real-proof");target.mkdir(exist_ok=True)
    began=time.monotonic()
    try:
        from gradio_client import Client
        client=Client(PROVIDER,verbose=False)
        spec=client.view_api(return_format="dict")
        # Fail closed if contract changed, avoiding an accidental GPU request.
        ep=(spec.get("named_endpoints") or {}).get("/generate_video")
        if not ep:
            raise ValueError("Missing expected named endpoint")
        names=[p.get("parameter_name") for p in ep.get("parameters",[])]
        required=["prompt","image","width","height","num_frames","num_inference_steps","guidance_scale","seed"]
        if names!=required:raise ValueError("Changed API contract")
        prompt="Small blue paper boat glides gently forward along clear rippling water. Locked-off camera, subtle water motion, daylight, no people, no text."
        receipt["requests_submitted"]=1
        # The Gradio client handles provider queue status; never auto-retry inference.
        job=client.submit(prompt,None,512,512,25,20,4.0,42,api_name="/generate_video")
        until=time.monotonic()+430
        while not job.done() and time.monotonic()<until:time.sleep(4)
        if not job.done():
            job.cancel()
            raise TimeoutError("GPU did not complete before timeout")
        output=job.result()
        v=output[0] if isinstance(output,(list,tuple)) and output else output
        if isinstance(v,dict):v=v.get("video") or v.get("path")
        if not isinstance(v,str) or v.startswith(("http://","https://","file://")):
            raise ValueError("No valid downloaded video path returned")
        path=Path(v)
        if not path.is_file() or path.is_symlink() or not 1024<path.stat().st_size<120_000_000:
            raise ValueError("Missing media file")
        with path.open("rb") as src: header=src.read(12)
        if header[4:8]!=b"ftyp":raise ValueError("Invalid MP4 header")
        metadata=json.loads(subprocess.run(["ffprobe","-v","error","-show_entries","stream=codec_type,nb_frames",
                  "-show_entries","format=duration","-of","json",str(path)],check=True,capture_output=True,
                  text=True,timeout=20).stdout)
        videos=[s for s in metadata.get("streams",[]) if s.get("codec_type")=="video"]
        dur=float(metadata.get("format",{}).get("duration",0))
        if not videos or not 0.6<=dur<=5:raise ValueError("No valid frame sequence or duration")
        dest=target/"wan22-synthetic-ai.mp4"
        shutil.copyfile(path,dest)
        with dest.open("rb") as src:digest=hashlib.file_digest(src,"sha256").hexdigest()
        receipt.update(gpu_generated_video_verified=True,output_bytes=dest.stat().st_size,
                       video_duration_seconds=round(dur,2),sha256=digest,video_stream_verified=True,
                       provider_audio_stream=False)
    except Exception as exc:
        receipt["failure_type"]=type(exc).__name__
        receipt["provider_unverified"]=True
    finally:
        receipt["wall_seconds"]=round(time.monotonic()-began,2)
        (target/"receipt.json").write_text(json.dumps(receipt,indent=2,ensure_ascii=False))
    print(json.dumps(receipt,indent=2,ensure_ascii=False))
    if not receipt["gpu_generated_video_verified"]:raise SystemExit("No real GPU-generated video verified")
if __name__=="__main__":evidence()
