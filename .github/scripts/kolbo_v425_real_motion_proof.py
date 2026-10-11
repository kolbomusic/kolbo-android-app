"""One legitimate free public ZeroGPU Wan GPU job with synthetic scene, no user files.

Claim threshold: must contain motion not just stable two-panel photo collage.
No auto retry, no paid credits, no login token. Video marked EXPERIMENTAL.
"""
import hashlib,json,shutil,subprocess,time
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
from gradio_client import Client,handle_file

OUT=Path("v425-real-proof")
SPACE="zerogpu-aoti/wan2-2-fp8da-aoti-faster"
PROMPT=("One happy cartoon dancer stands center stage. In the video the dancer "
        "energetically WAVES THE RIGHT ARM UP AND DOWN three times and visibly "
        "turns their head. The person's limbs and body visibly MOVE relative "
        "to a completely STATIC blue stage background. Fixed camera, "
        "no zoom, no static image, no split-screen or captions.")

def run(*args,**kw):
    return subprocess.run(args,check=True,capture_output=True,text=True,timeout=45,**kw).stdout
def frame(video:Path,t:float,out:Path):
    subprocess.run(["ffmpeg","-nostdin","-v","error","-y","-ss",str(t),
        "-i",str(video),"-frames:v","1",str(out)],check=True,timeout=30)
    return np.array(Image.open(out).convert("RGB"))
def main():
    OUT.mkdir(exist_ok=True)
    canvas=Image.new("RGB",(640,640),(60,132,205))
    d=ImageDraw.Draw(canvas)
    # Entirely synthetic illustrated person (no real personal photos).
    d.rectangle((0,530,639,639),fill=(44,101,166))
    d.ellipse((247,115,392,258),fill=(239,190,125))
    d.ellipse((277,169,295,184),fill=(32,32,45))
    d.ellipse((347,169,365,184),fill=(32,32,45))
    d.arc((292,193,349,226),5,174,fill=(85,35,35),width=4)
    d.rounded_rectangle((261,250,387,452),20,fill=(205,60,80))
    d.line([(261,278),(190,370),(165,430)],fill=(239,190,125),width=34)
    d.line([(388,275),(475,365),(497,294)],fill=(239,190,125),width=34)
    d.line([(298,450),(280,570)],fill=(44,43,60),width=39)
    d.line([(356,450),(382,570)],fill=(44,43,60),width=39)
    ref=OUT/"synthetic-dancer.png"
    canvas.save(ref)
    start=time.monotonic()
    client=Client(SPACE,verbose=False)
    # 8 steps generally slightly better than previously tested 6-step output.
    job=client.submit(handle_file(str(ref)),PROMPT,8,"",3.5,1.0,1.0,42,
                      False,api_name="/generate_video")
    deadline=start+420
    while not job.done() and time.monotonic()<deadline:
        time.sleep(5)
    if not job.done():
        job.cancel()
        raise TimeoutError("Shared free GPU timed out; no second attempt")
    value=job.result()
    obj=value[0]
    if isinstance(obj,dict):
        obj=obj.get("path") or obj.get("name")
    if not isinstance(obj,str) or not Path(obj).is_file():
        raise ValueError("Provider produced no download")
    dest=OUT/"real-3.5s-wan-ai.mp4"
    shutil.copyfile(obj,dest)
    meta=json.loads(run(["ffprobe","-v","error","-show_entries",
        "format=duration:stream=codec_type","-of","json",str(dest)]))
    dur=float(meta["format"]["duration"])
    assert abs(dur-3.5)<0.5 and any(x["codec_type"]=="video" for x in meta["streams"])
    f1=frame(dest,min(.25,dur*.1),OUT/"f1.png")
    f2=frame(dest,dur*.5,OUT/"f2.png")
    f3=frame(dest,dur*.85,OUT/"f3.png")
    diffs=[float(np.abs(a.astype(np.int16)-b.astype(np.int16)).mean())
          for a,b in [(f1,f2),(f2,f3)]]
    frozen=(max(diffs)<2.0)
    note={"generated_by_real_wan_ai":True,"source":"synthetic-only",
          "audio":False,"duration":dur,"frame_rgb_difference_mean":diffs,
          "frozen_motion_evidence":frozen,
          "human_scene_semantics_verified":False,
          "commercial_rights_verified":False,
          "release_ready":False,"generation_time_s":round(time.monotonic()-start,2),
          "sha256":hashlib.sha256(dest.read_bytes()).hexdigest()}
    (OUT/"receipt.json").write_text(json.dumps(note,indent=2),encoding="utf8")
    print("REAL VIDEO PROOF",json.dumps(note,ensure_ascii=False),flush=True)
    if frozen: raise AssertionError("Provider video lacks measurable motion")
if __name__=="__main__":main()
