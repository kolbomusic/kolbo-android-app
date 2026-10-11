"""Proof: one synthetic reference containing TWO distinct drawn people -> LTX AI + audio.
Not identity-consistency proof; no photo from real user. Never retries public GPU.
"""
from pathlib import Path
import json,time,hashlib,subprocess,shutil
import sys
from PIL import Image,ImageDraw
from gradio_client import Client,handle_file
sys.path.insert(0,"gateway/backend")
import visual_quality,audio_evidence

folder=Path("v432-duo-synthetic-proof")
folder.mkdir(parents=True,exist_ok=True)
im=Image.new("RGB",(768,768),(25,27,41))
d=ImageDraw.Draw(im)
for x,shirt,hair,skin in [
    (198,(44,140,225),(40,22,22),(218,160,113)),
    (570,(245,119,65),(230,214,85),(168,96,58))
]:
    d.ellipse((x-69,112,x+69,250),fill=skin)
    d.pieslice((x-82,92,x+82,202),190,350,fill=hair)
    d.ellipse((x-35,179,x-22,190),fill=(45,25,25))
    d.ellipse((x+20,179,x+33,190),fill=(45,25,25))
    d.arc((x-28,191,x+28,230),0,175,fill=(95,36,36),width=4)
    d.rounded_rectangle((x-95,255,x+95,558),25,fill=shirt)
    d.line(((x-84,295),(x-140,460)),fill=skin,width=33)
    d.line(((x+84,295),(x+142,460)),fill=skin,width=33)
    d.line(((x-48,548),(x-55,730)),fill=(30,30,40),width=51)
    d.line(((x+48,548),(x+55,730)),fill=(30,30,40),width=51)
d.line(((384,20),(384,750)),fill=(120,125,135),width=2)
src=folder/"two-different-illustrated-people.jpg"
im.save(src,quality=85)
prompt=("Use the two DISTINCT illustrated people in the starting image. "
 "The LEFT figure wearing a blue jacket and the RIGHT figure wearing an "
 "orange jacket both dance with clearly moving arms and legs on ONE shared "
 "lit stage. A cheering crowd applauds loudly and rhythmically. "
 "Show BOTH unique figures in the same moving camera shot. "
 "The dance and audible cheering happen at the same time.")
client=Client("ChopperBlu/ltx-2-5-demo",verbose=False)
start=time.monotonic()
job=client.submit(prompt,handle_file(str(src)),512,512,3.0,False,42,False,
                  "conv",api_name="/generate_video")
deadline=start+480
while not job.done() and time.monotonic()<deadline:
    time.sleep(10)
if not job.done():
    job.cancel()
    raise TimeoutError("shared GPU did not return before deadline; no retry")
result=job.result()
output=result[0]
if isinstance(output,dict):
    output=output.get("path") or output.get("name")
if not isinstance(output,str) or not Path(output).is_file():
    raise RuntimeError("public model has not returned an MP4")
target=folder/"two-illustrated-characters-LTX-AI-with-audio.mp4"
shutil.copyfile(output,target)
probe=json.loads(subprocess.run(["ffprobe","-v","error",
    "-show_entries","format=duration:stream=codec_type",
    "-of","json",str(target)],check=True,capture_output=True,text=True).stdout)
duration=float(probe["format"]["duration"])
motion=visual_quality.inspect_mp4(target,audio_required=True)
sound=audio_evidence.inspect_mp4(target,audio_required=True)
receipt={
 "two_separate_reference_images":True,
 "one_merged_start_reference":True,
 "model":"public LTX-2.5 native AV",
 "generated_ai":True,"source_real_photos":False,
 "requested_seconds":3,"output_seconds":duration,
 "pixel_change_fraction":motion.pixel_change_fraction,
 "rms_dbfs":sound.rms_dbfs,
 "audible":sound.verdict!="reject",
 "two_actor_identity_preservation_verified":False,
 "prompt_semantics_verified":False,
 "singing_lyrics_verified":False,
 "external_free_quota_guaranteed":False,
 "sha256":hashlib.sha256(target.read_bytes()).hexdigest()
}
(folder/"receipt.json").write_text(json.dumps(receipt,indent=2))
print("DUO_PROOF",json.dumps(receipt),flush=True)
assert abs(duration-3)<.35
assert motion.pixel_change_fraction>=.012
assert sound.decoded_audio and sound.verdict!="reject"
print("PASS real synthesized LTX AI motion+audio from ONE combined two-person reference")
