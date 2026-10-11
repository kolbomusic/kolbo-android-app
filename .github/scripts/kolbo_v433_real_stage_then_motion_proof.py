"""One real two-provider chain: verified AI stage image -> native LTX video+sound.

Reuse previously generated SYNTHETIC stage from FLUX CI artifact to avoid
repeating GPU work. No user photos, no service token, no retries.
"""
from pathlib import Path
from gradio_client import Client,handle_file
import hashlib,json,shutil,subprocess,sys,time
sys.path.insert(0,"gateway/backend")
import audio_evidence,visual_quality,scene_integrity_v433

start_image=Path("prebuilt-stage/generated-shared-stage-preview.png")
if not start_image.is_file():
    raise RuntimeError("Missing genuine FLUX-created shared stage image")
prompt=("TWO different performers stand together on ONE outdoor theater stage "
        "with a crowded audience. Both performers visibly move their hands and "
        "upper bodies, raising microphones, smiling and singing joyfully; "
        "audible live stage music, cheering and applause accompany the action. "
        "Keep a SINGLE shared cinematic frame, NEVER side-by-side portrait "
        "panels, static photo collage, split-screen or framed pictures.")
folder=Path("v433-two-step-proof")
folder.mkdir(exist_ok=True)
started=time.monotonic()
client=Client("ChopperBlu/ltx-2-5-demo",verbose=False)
job=client.submit(prompt,handle_file(str(start_image)),512,512,3.0,
                  False,42,False,"conv",api_name="/generate_video")
deadline=time.monotonic()+490
while not job.done() and time.monotonic()<deadline:
    time.sleep(10)
if not job.done():
    job.cancel()
    raise TimeoutError("Public GPU took too long; do not resubmit")
result=job.result()
source=result[0] if isinstance(result,(tuple,list)) else None
if isinstance(source,dict):source=source.get("path") or source.get("name")
if not isinstance(source,str) or not Path(source).is_file():
    raise RuntimeError("Native video/audio model returned no MP4")
output=folder/"FLUX-stage-then-LTX-motion-audio.mp4"
shutil.copyfile(source,output)
probe=json.loads(subprocess.run(["ffprobe","-v","error","-show_entries",
    "format=duration:stream=codec_type","-of","json",str(output)],
    check=True,capture_output=True,text=True).stdout)
duration=float(probe["format"]["duration"])
sound=audio_evidence.inspect_mp4(output,audio_required=True)
motion=visual_quality.inspect_mp4(output,audio_required=True)
scene=scene_integrity_v433.inspect_video(output)
receipt={
    "video_by_model":"ChopperBlu/ltx-2-5-demo",
    "stage_by_model":"black-forest-labs/FLUX.1-Kontext-dev",
    "original_input":"SYNTHETIC ONLY",
    "two_provider_stage_to_video_pipeline":True,
    "duration_seconds":duration,
    "audio_evidence":sound.as_dict(),
    "motion_evidence":motion.as_dict(),
    "scene_layout_evidence":scene.as_dict(),
    "faces_verified":False,
    "crowd_size_verified":False,
    "singing_language_verified":False,
    "lip_sync_verified":False,
    "commercial_rights_verified":False,
    "unlimited_free_gpu":False,
    "sha256":hashlib.sha256(output.read_bytes()).hexdigest(),
    "total_seconds_second_step":round(time.monotonic()-started,2),
}
(folder/"receipt.json").write_text(json.dumps(receipt,ensure_ascii=False,indent=2))
print("TWO_STAGE_PROOF",json.dumps(receipt,ensure_ascii=False),flush=True)
assert abs(duration-3)<.35
assert sound.decoded_audio and sound.verdict!="reject"
assert motion.pixel_change_fraction>.012
assert not scene.output_is_split_layout,"Retained split portraits; cannot claim successful two-person scene"
assert not scene.near_static_frames,"Frozen camera image was returned"
print("PASS TWO SEQUENTIAL MODELS: NEW SHARED STAGE + MOVING AUDIO-VIDEO",flush=True)
