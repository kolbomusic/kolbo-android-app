"""Single anonymous official Gradio SDK attempt, synthetic LTX video+audio.
Never use paid APIs or submit a second GPU job after an uncertain response.
"""
import hashlib,json,os,time,subprocess
from pathlib import Path

SPACE="ChopperBlu/ltx-2-5-demo"
API="/generate_video"
PROMPT="Small blue paper boat moves from left to right on rippling shallow water, single fixed shot, natural outdoor bird calls and gentle splashes, no people, no text or logos."
def main():
 from gradio_client import Client
 outcome={"provider":SPACE,"attempted_submission":False,"submitted_once":False,
    "verified_ai_mp4":False,"video_track":False,"audio_track":False,
    "paid_fallback":False,"images_sent":0,"commercial_use":False}
 root=Path("gpu-sdk-result");root.mkdir(exist_ok=True)
 job=None
 started=time.monotonic()
 try:
  client=Client(SPACE,verbose=False)
  # One and only one public ZeroGPU request. Gradio SDK manages queue/session.
  outcome["attempted_submission"]=True
  job=client.submit(PROMPT,None,512,512,1.0,False,42,False,"conv",api_name=API)
  outcome["submitted_once"]=True
  deadline=time.monotonic()+330
  while not job.done() and time.monotonic()<deadline:time.sleep(2)
  if not job.done():
   try:job.cancel()
   except Exception:pass
   raise RuntimeError("Unresolved job, no retry")
  result=job.result()
  item=result[0] if isinstance(result,(list,tuple)) and result else result
  file=item.get("path") if isinstance(item,dict) else item
  if not isinstance(file,str) or file.startswith(("http:","https:","file:")):
   raise RuntimeError("Remote or invalid result not accepted")
  path=Path(file)
  if not path.is_file() or path.is_symlink() or path.suffix.lower()!=".mp4" or not 2048<=path.stat().st_size<=120_000_000:
   raise RuntimeError("No safe local MP4")
  with path.open("rb") as source:head=source.read(12)
  if head[4:8]!=b"ftyp":raise RuntimeError("Invalid MP4 magic")
  metadata=json.loads(subprocess.run(["ffprobe","-v","error","-show_entries","stream=codec_type:format=duration",
      "-of","json",str(path)],check=True,capture_output=True,text=True,timeout=25).stdout)
  types={s.get("codec_type") for s in metadata.get("streams",[])}
  dur=float(metadata.get("format",{}).get("duration",0))
  if not 0.5<=dur<=3 or "video" not in types or "audio" not in types:
   raise RuntimeError("No valid moving-image+audio container")
  from shutil import copyfile
  target=root/"synthetic-ltx-ai.mp4"
  if target.exists():raise RuntimeError("Refusing to overwrite output")
  copyfile(path,target)
  with target.open("rb") as stream:digest=hashlib.file_digest(stream,"sha256").hexdigest()
  outcome.update(verified_ai_mp4=True,video_track=True,audio_track=True,
      duration_seconds=dur,bytes=target.stat().st_size,sha256=digest)
 except Exception as exc:
  # Do not log signed URLs, personal tokens, or upstream exception text.
  outcome["error_type"]=type(exc).__name__
  outcome["failure_class"]="provider_or_unauthenticated_quota_or_api"
 finally:
  outcome["elapsed_seconds"]=round(time.monotonic()-started,1)
  (root/"receipt.json").write_text(json.dumps(outcome,indent=2),encoding="utf-8")
 print(json.dumps(outcome,indent=2))
 if not outcome["verified_ai_mp4"]:raise SystemExit("AI video not verified; no retry")
if __name__=="__main__":main()
