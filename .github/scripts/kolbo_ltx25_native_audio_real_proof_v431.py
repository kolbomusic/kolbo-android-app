"""One actual public LTX-2.5 ZeroGPU T2V+audio attempt, synthetic only.

Never uploads user photos, uses paid APIs, or retries an uncertain job.
Require BOTH moving frames and decoded audible audio before success.
"""
import json,hashlib,shutil,subprocess,time,os
from pathlib import Path
from gradio_client import Client
from PIL import Image
import sys
sys.path.insert(0,"gateway/backend")
import audio_evidence,visual_quality

TARGET=Path("v431-native-av-proof")
TARGET.mkdir(exist_ok=True)
PROMPT=("A cute stylized 3D cartoon rabbit wearing a blue hat dances and "
        "waves both arms on a stage, knees and arms visibly move. "
        "The rabbit laughs and the audience applauds loudly in rhythm. "
        "Camera fixed on stage. Sound of cheerful clapping synchronized with motion.")
space="ChopperBlu/ltx-2-5-demo"
start=time.monotonic()
client=Client(space,verbose=False)
job=client.submit(PROMPT,None,512,512,2.0,False,42,False,"conv",api_name="/generate_video")
deadline=time.monotonic()+480
while not job.done() and time.monotonic()<deadline:
    print("WAITING queued seconds",int(time.monotonic()-start),flush=True)
    time.sleep(15)
if not job.done():
    job.cancel()
    raise TimeoutError("One ZeroGPU submission timed out, no blind retry")
result=job.result()
print("MODEL-RETURN",str(result)[:1800])
value=result[0]
if isinstance(value,dict):
    value=value.get("path") or value.get("name")
if not isinstance(value,str) or not Path(value).is_file():
    raise RuntimeError("Model returned no accessible MP4")
out=TARGET/"native-ai-video-plus-audio-2s.mp4"
shutil.copyfile(value,out)
meta=json.loads(subprocess.run(["ffprobe","-v","error",
    "-show_entries","format=duration:stream=codec_type,width,height",
    "-of","json",str(out)],check=True,capture_output=True,timeout=30).stdout)
duration=float(meta["format"]["duration"])
tracks=[x.get("codec_type") for x in meta.get("streams",[])]
assert "video" in tracks
visual=visual_quality.inspect_mp4(out,audio_required=True)
audio=audio_evidence.inspect_mp4(out,audio_required=True)
report={"model":"LTX-2.5 Distilled public Gradio ZeroGPU trial",
    "origin":space,"duration_seconds":duration,
    "video":True,"has_audio_track":"audio" in tracks,
    "audio_audibility":audio.as_dict(),"frame_motion":visual.as_dict(),
    "has_user_media":False,"prompt_semantics_verified":False,
    "speech_language_verified":False,
    "identity_consistency_verified":False,
    "commercial_rights_verified":False,
    "available_free_unlimited":False,
    "sha256":hashlib.sha256(out.read_bytes()).hexdigest(),
    "elapsed_seconds":time.monotonic()-start}
(TARGET/"receipt.json").write_text(json.dumps(report,indent=2))
print("NATIVE-LTX-PROOF",json.dumps(report),flush=True)
assert abs(duration-2)<.30,("Duration mismatch",duration)
assert audio.has_audio_stream and audio.decoded_audio and audio.verdict!="reject","Native model output has no audible audio"
assert visual.pixel_change_fraction>=0.012,"AI frames are nearly static"
print("PASS REAL LTX AI VIDEO WITH AUDIBLE AUDIO",flush=True)
