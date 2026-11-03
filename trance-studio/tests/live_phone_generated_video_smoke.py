"""Real Render smoke for phone-completed motion MP4 with original Hebrew OPUS.

Only fictional synthetic speech and a generated moving test pattern are sent;
this test proves the upload/mux endpoint, not photorealistic AI scene quality.
"""
from __future__ import annotations
import hashlib,io,json,os,pathlib,re,subprocess,time,urllib.error,urllib.request
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

# A push triggers this production acceptance BEFORE manual Render deployment.
# Merely seeing the old /studio HTML is not proof the new worker is live:
# sending a job during worker replacement loses its in-memory job ID (404).
# Extract the version from THIS checked-out backend instead of hard-coding it.
backend=(pathlib.Path(__file__).resolve().parents[1]/
         "backend"/"app.py").read_text(encoding="utf-8")
version_match=re.search(
    r"service='kolbo-trance-studio',version='([0-9]+\.[0-9]+\.[0-9]+)'",
    backend)
if not version_match:
    raise RuntimeError("Cannot identify checked-out Kolbo backend version")
expected_version=version_match.group(1)
for i in range(90):
    try:
        raw,_=call("/health",timeout=24)
        health=json.loads(raw)
        if health.get("ok") and health.get("version")==expected_version:
            page,_=call("/studio",timeout=24)
            if b"completeAIVideoOnPhone" in page:
                print("PHONE_SMOKE_TARGET_BACKEND_READY",expected_version,flush=True)
                break
    except (OSError,urllib.error.URLError,ValueError):
        pass
    time.sleep(5)
else:
    raise RuntimeError("Target backend version not deployed: "+expected_version)

# Allow the previous Render worker to drain before creating an in-memory job.
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

    # This legacy one-shot endpoint cannot legitimately fill a 30-second
    # soundtrack from a TWO-SECOND clip. HTTP 422 is an intentional
    # anti-loop safety check; it is NOT a failing renderer.
    clip=CLIP.read_bytes()
    boundary="----KolboPhoneVideoUpload20261103"
    one_shot=(f'--{boundary}\r\nContent-Disposition: form-data; '
        'name="video"; filename="short-scene.mp4"\r\n'
        'Content-Type: video/mp4\r\n\r\n').encode()+clip+f'\r\n--{boundary}--\r\n'.encode()
    try:
        call("/api/jobs/"+job["id"]+"/generated-video",
            one_shot,{"Content-Type":f"multipart/form-data; boundary={boundary}"},
            timeout=125)
    except urllib.error.HTTPError as exc:
        assert exc.code==422,("Expected anti-loop rejection",exc.code)
        error=json.loads(exc.read()).get("error","")
        assert "קליפ AI יחיד קצר" in error,error
        print("REAL_RENDER_PHONE_SHORT_CLIP_SAFELY_REJECTED",flush=True)
    else:
        raise AssertionError("A two-second AI clip MUST NOT become a 30-second repeated MP4")

    # Validate the CURRENT phone-to-server route with ordered, actually
    # distinct moving scenes covering the entire recorded mix. Each visual
    # clip below is purely synthetic; no private WhatsApp data or external
    # GPU quota is used by this mux integration test.
    count=int(state.get("client_ai_scene_count",0))
    weights=state.get("client_ai_scene_weights") or []
    assert 1<=count<=24 and len(weights)==count,(count,len(weights))
    soundtrack=float(state.get("audio_seconds",0))
    assert 10<=soundtrack<=360,soundtrack
    total=float(sum(weights))
    durations=[soundtrack*float(weight)/total for weight in weights]
    assert min(durations)>=.7,durations
    assert max(durations)<=11.8,("No 12-second free-clip allocation can cover scene",max(durations))
    colors=["red","lime","blue","yellow","cyan","magenta","orange",
            "white","purple","green","pink","aqua","brown","gold",
            "silver","teal","navy","violet","coral","salmon","olive",
            "maroon","turquoise","orchid"]
    attachments=[]
    for i,needed in enumerate(durations):
        length=round(max(1.4,needed+.5),2)
        output=pathlib.Path("/tmp/kolbo-phone-scene-%02d.mp4"%i)
        rect_x=(i*31)%175
        rect_y=(i*47)%286
        vf=(f"drawbox=x={rect_x}:y={rect_y}:w=70:h=84:"
            f"color={colors[i]}@1:t=fill")
        subprocess.run(["ffmpeg","-nostdin","-v","error","-y",
            "-f","lavfi","-i",
            f"testsrc2=size=256x384:rate=12:duration={length}",
            "-vf",vf,"-an","-c:v","libx264","-preset","ultrafast",
            "-crf","30","-pix_fmt","yuv420p","-movflags","+faststart",
            str(output)],check=True,timeout=55)
        scene=output.read_bytes()
        assert len(scene)>12000,(i,len(scene))
        attachments.append((i,scene))
    boundary="----KolboPhoneUniqueScenes20261103"
    parts=[]
    for i,scene in attachments:
        parts.append((f'--{boundary}\r\nContent-Disposition: form-data; '
            f'name="clip"; filename="original-scene-{i}.mp4"\r\n'
            'Content-Type: video/mp4\r\n\r\n').encode()+scene+b"\r\n")
    parts.append(f'--{boundary}--\r\n'.encode())
    payload=b"".join(parts)
    response,code=call("/api/jobs/"+job["id"]+"/ai-clips",
        payload,{"Content-Type":f"multipart/form-data; boundary={boundary}"},
        timeout=300)
    assert code==200,response[:400]
    movie_result=json.loads(response)
    print("REAL_RENDER_PHONE_UNIQUE_SCENES_MUXED",{
          "scene_count":count,"requested_seconds":soundtrack,
          "mode":movie_result["video_mode"]},flush=True)
    assert movie_result["video_mode"]=="ai_generated_client_fallback",movie_result
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
assert abs(duration-float(state.get("audio_seconds",0)))<.8,duration
subprocess.run(["ffmpeg","-v","error","-ss","24","-i",str(out),
                "-frames:v","1","-f","null","-"],check=True,timeout=25)
print("REAL_RENDER_PHONE_QUOTA_FALLBACK_MP4_PASS",{
    "mp4_bytes":len(mp4),"duration":duration,
    "origin":state.get("transcript_origin"),
    "mode":state.get("video_mode"),"shots":state.get("ai_clips_generated"),
    "coverage":state.get("visual_coverage")},flush=True)
