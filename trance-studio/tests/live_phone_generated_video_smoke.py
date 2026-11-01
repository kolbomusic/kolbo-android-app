"""Real Render smoke for phone-completed motion MP4 with original Hebrew OPUS.

Only fictional synthetic speech and a generated moving test pattern are sent;
this test proves the upload/mux endpoint, not photorealistic AI scene quality.
"""
from __future__ import annotations
import hashlib,io,json,os,pathlib,subprocess,time,urllib.error,urllib.request
from http.cookiejar import CookieJar
from urllib.request import HTTPCookieProcessor,Request,build_opener

BASE=os.environ.get("KOLBO_TRANCE_URL","https://kolbo-trance-studio.onrender.com")
SPEECH=pathlib.Path("/tmp/kolbo-phone-fallback-sample.opus")
CLIP=pathlib.Path("/tmp/kolbo-phone-fallback-motion.mp4")
assert SPEECH.is_file() and CLIP.is_file()
jar=CookieJar()
client=build_opener(HTTPCookieProcessor(jar))

def call(path,body=None,headers=None,timeout=90):
    with client.open(Request(BASE+path,data=body,headers=headers or {}),timeout=timeout) as response:
        return response.read(),response.status

# Wait for the new frontend before starting a long-lived Render Free job.
for i in range(90):
    try:
        page,_=call("/studio",timeout=24)
        if b"completeAIVideoOnPhone" in page:
            break
    except (OSError,urllib.error.URLError):
        pass
    time.sleep(5)
else:
    raise RuntimeError("phone quota fallback not deployed")

time.sleep(12)
boundary="----KolboPhoneVideoSmoke20261101"
parts=[]
def part(name,data,filename=None,mime=None):
    h=f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"'
    if filename:h+=f'; filename="{filename}"'
    h+='\r\n'
    if mime:h+=f'Content-Type: {mime}\r\n'
    parts.append(h.encode()+b'\r\n'+data+b'\r\n')

content=SPEECH.read_bytes()
part("audio",content,"speech.opus","audio/ogg")
for key,value in {
    "make_video":"on","video_requested":"on","ai_video_consent":"on",
    "transcript":"","transcript_origin":"auto",
    "source_hashes":hashlib.sha256(content).hexdigest(),
    "bpm":"145","style":"mixed","humor":"auto","seconds":"30"
}.items():part(key,str(value).encode())
parts.append(f"--{boundary}--\r\n".encode())
data,status=call("/api/jobs",b"".join(parts),
    {"Content-Type":f"multipart/form-data; boundary={boundary}"})
assert status==202
job=json.loads(data)
print("PHONE_FALLBACK_JOB_ACCEPTED",job["id"],flush=True)
deadline=time.monotonic()+430
state={}
while time.monotonic()<deadline:
    time.sleep(4)
    data,_=call(job["status_url"],timeout=60)
    state=json.loads(data)
    print("PHONE_FALLBACK_STAGE",state.get("state"),state.get("percent"),
          str(state.get("label",""))[:70],flush=True)
    if state.get("state") in ("error","done"):break
assert state.get("state")=="done",state
if state.get("video_status")!="done":
    assert state.get("client_ai_fallback") is True,state
    assert "glass" not in state  # no invented transcript correction
    assert "client_ai_prompt" in state and len(state["client_ai_prompt"])>50,state
    clip=CLIP.read_bytes()
    boundary="----KolboPhoneVideoUpload20261101"
    payload=(f'--{boundary}\r\nContent-Disposition: form-data; '
        'name="video"; filename="generated.mp4"\r\n'
        'Content-Type: video/mp4\r\n\r\n').encode()+clip+f'\r\n--{boundary}--\r\n'.encode()
    response,code=call("/api/jobs/"+job["id"]+"/generated-video",
        payload,{"Content-Type":f"multipart/form-data; boundary={boundary}"},
        timeout=125)
    assert code==200,response[:400]
    movie_result=json.loads(response)
    print("PHONE_FALLBACK_UPLOAD_DONE",movie_result["video_status"],flush=True)
    assert movie_result["video_mode"]=="ai_generated_on_device",movie_result
    state=json.loads(call(job["status_url"])[0])
assert state.get("video_status")=="done",state
mp4,code=call(state["video_url"],timeout=90)
assert code==200 and len(mp4)>30000
out=pathlib.Path("/tmp/kolbo-phone-fallback-output.mp4")
out.write_bytes(mp4)
probe=json.loads(subprocess.check_output([
    "ffprobe","-v","error","-show_streams","-show_format","-of","json",str(out)]))
video=next(s for s in probe["streams"] if s["codec_type"]=="video")
assert (video["codec_name"],video["width"],video["height"])==("h264",360,640),video
assert {s["codec_type"] for s in probe["streams"]}=={"audio","video"},probe
duration=float(probe["format"]["duration"])
assert 29<duration<32,duration
subprocess.run(["ffmpeg","-v","error","-ss","24","-i",str(out),
                "-frames:v","1","-f","null","-"],check=True,timeout=25)
print("REAL_RENDER_PHONE_QUOTA_FALLBACK_MP4_PASS",{
    "mp4_bytes":len(mp4),"duration":duration,
    "origin":state.get("transcript_origin"),
    "mode":state.get("video_mode"),
    "coverage":state.get("visual_coverage")},flush=True)
