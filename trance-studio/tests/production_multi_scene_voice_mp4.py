"""MULTI-SCENE production e2e: Hebrew OPUS speech -> TWO true moving scenes.

No transcript is supplied. A generated TTS voice is used solely as a public
test stimulus; no private user's WhatsApp audio is sent or stored in GitHub.
"""
from __future__ import annotations
import hashlib
import io
import json
import os
import pathlib
import subprocess
import time
import urllib.error
import urllib.request
from http.cookiejar import CookieJar
from urllib.request import HTTPCookieProcessor, Request, build_opener

BASE=os.environ.get("KOLBO_TRANCE_URL","https://kolbo-trance-studio.onrender.com")
OPUS=pathlib.Path("/tmp/kolbo-multi-story-hebrew.opus")
assert OPUS.is_file() and OPUS.stat().st_size>1000
source=OPUS.read_bytes()
jar=CookieJar()
client=build_opener(HTTPCookieProcessor(jar))
def request(path, data=None, headers=None, timeout=30):
    try:
        with client.open(Request(BASE+path,data=data,headers=headers or {}),timeout=timeout) as r:
            return r.read(),r.status
    except urllib.error.HTTPError as e:
        details=e.read(400).decode("utf-8","replace")
        raise AssertionError(f"HTTP {e.code} {path}: {details}") from e

health=json.loads(request("/health",timeout=60)[0])
assert health.get("ok") and health.get("asr_preloaded"),health
request("/studio",timeout=60)
assert any(c.name=="kolbo_studio" for c in jar)
boundary="----KolboMultiSceneProductionZ8631"
parts=[]
def part(name,value,filename=None,mime=None):
    h=f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"'
    if filename:h+=f'; filename="{filename}"'
    h+='\r\n'
    if mime:h+=f'Content-Type: {mime}\r\n'
    parts.append(h.encode()+b'\r\n'+value+b'\r\n')
part("audio",source,"voice.opus","audio/ogg")
for k,v in {
    "make_video":"on","video_requested":"on",
    "transcript":"","transcript_origin":"auto",
    "source_hashes":hashlib.sha256(source).hexdigest(),
    "style":"mixed","seconds":"30","bpm":"145",
    "humor":"auto","fx_intensity":"2"
}.items():part(k,str(v).encode())
parts.append(f"--{boundary}--\r\n".encode())
data,status=request("/api/jobs",b"".join(parts),
    {"Content-Type":f"multipart/form-data; boundary={boundary}"},timeout=60)
assert status==202
job=json.loads(data)
print("PRODUCTION_JOB_ACCEPTED",job["id"],flush=True)
deadline=time.monotonic()+390
state=None
while time.monotonic()<deadline:
    time.sleep(3)
    state=json.loads(request(job["status_url"],timeout=60)[0])
    print("PRODUCTION_STAGE",state.get("state"),state.get("percent"),
          str(state.get("label",""))[:80],flush=True)
    if state.get("state") in ("done","error"):
        break
assert state and state.get("state")=="done",state
assert state.get("video_status")=="done",state
assert state.get("transcript_origin")=="server_original_asr",state
assert state.get("video_url"),state
movie_bytes,code=request(state["video_url"],timeout=120)
assert code==200 and len(movie_bytes)>20000
story_bytes,_=request(state["storyboard_url"],timeout=60)
story=json.loads(story_bytes)
sources=story.get("sources") or []
assert len(sources)>=2,("NOT_ENOUGH_MATCHED_VIDEO_SCENES",sources,story)
assert all(s.get("page","").startswith("https://commons.wikimedia.org/wiki/")
           for s in sources),story
actions=[s["action"] for s in sources]
assert len(set(actions))>=2,("REPEATED_SINGLE_ACTION_INSTEAD_OF_STORY",actions)
print("MULTI_SCENE_ACTIONS",actions,flush=True)
out=pathlib.Path("/tmp/kolbo-multi-scene-verified.mp4")
out.write_bytes(movie_bytes)
info=json.loads(subprocess.check_output([
    "ffprobe","-v","error","-show_format","-show_streams","-of","json",str(out)]))
tracks={s["codec_type"] for s in info["streams"]}
assert tracks=={"video","audio"},tracks
video=next(s for s in info["streams"] if s["codec_type"]=="video")
assert video["codec_name"]=="h264",(video["codec_name"],video)
assert (video["width"],video["height"])==(360,640),video
duration=float(info["format"]["duration"])
assert 29<duration<32,duration
subprocess.run(["ffmpeg","-v","error","-ss","23","-i",str(out),
    "-frames:v","1","-f","null","-"],check=True,timeout=30)
# Confirm actual changes across decoded image frames, not simply a video stream
# that repeats an unmoving still image for the entire soundtrack.
raw_frames=subprocess.check_output([
    "ffmpeg","-nostdin","-v","error","-i",str(out),
    "-vf","fps=1,scale=64:64,format=gray","-an","-f","rawvideo","-"],
    timeout=45)
frame_size=64*64
frames=[raw_frames[i:i+frame_size] for i in range(
    0,len(raw_frames)-frame_size+1,frame_size)]
assert len(frames)>=8,("VIDEO_FRAMES_TOO_FEW",len(frames))
motion=[sum(abs(a-b) for a,b in zip(frames[i],frames[i+1]))/frame_size
        for i in range(len(frames)-1)]
assert max(motion)>2.0,("VIDEO_HAS_NO_ACTUAL_VISIBLE_MOTION",max(motion))
# Require full-height live-action portrait coverage, not the previous
# letterboxed 16:9 footage inside a tall, mostly-black mobile screen.
first=frames[0]
top=sum(first[:64*8])/(64*8)
bottom=sum(first[-64*8:])/(64*8)
assert top>18 and bottom>18,(
    "VIDEO_HAS_LARGE_BLACK_LETTERBOX_BARS",round(top,1),round(bottom,1))
print("NO_BLACK_BARS_PASS",{"top_luma":round(top,1),
                            "bottom_luma":round(bottom,1)},flush=True)
print("MULTI_SCENE_DECODED_MOTION_PASS",
      {"max_average_pixel_delta":round(max(motion),2),
       "decoded_frames":len(frames)},flush=True)
print("REAL_PRODUCTION_MULTI_SCENE_MP4_PASS",json.dumps({
    "mp4_bytes":len(movie_bytes),"duration":duration,
    "video_codec":video["codec_name"],"dimensions":[video["width"],video["height"]],
    "scene_sources":[s["page"] for s in sources],
    "coverage":state.get("visual_coverage"),
    "transcript_origin":state.get("transcript_origin"),
    "video_status":state.get("video_status")},ensure_ascii=False),flush=True)
