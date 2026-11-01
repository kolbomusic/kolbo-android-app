"""PRODUCTION e2e: real MP4 upload -> beat-edited 30s H264/AAC movie.

The input is synthetic FFmpeg-generated moving video with synthesized Hebrew
speech, not a user's private WhatsApp file. Verifies the deployed service
actually exports an EDITED source video (not merely a re-dub of original).
"""
import hashlib
import json
import pathlib
import subprocess
import time
from http.cookiejar import CookieJar
from urllib.request import Request,HTTPCookieProcessor,build_opener
BASE="https://kolbo-trance-studio.onrender.com"
ORIGINAL=pathlib.Path("/tmp/kolbo-mock-whatsapp-video.mp4")
assert ORIGINAL.is_file() and ORIGINAL.stat().st_size>3000
jar=CookieJar();opener=build_opener(HTTPCookieProcessor(jar))
def fetch(path,body=None,headers=None,timeout=70):
    with opener.open(Request(BASE+path,data=body,headers=headers or {}),
                     timeout=timeout) as response:
        return response.read()
health=json.loads(fetch("/health",timeout=75))
assert health.get("ok"),health
fetch("/studio",timeout=75)
assert any(c.name=="kolbo_studio" for c in jar)
media=ORIGINAL.read_bytes()
boundary="----KolboVideoRemixIndependentProof"
parts=[]
def part(name,value,filename=None,mime=None):
    h='--'+boundary+'\r\nContent-Disposition: form-data; name="'+name+'"'
    if filename:h+='; filename="'+filename+'"'
    h+='\r\n'
    if mime:h+='Content-Type: '+mime+'\r\n'
    parts.append(h.encode()+b'\r\n'+value+b'\r\n')
part('audio',media,'WhatsApp-synthetic-test.mp4','video/mp4')
for k,v in {
    'make_video':'on','video_requested':'on','seconds':'30',
    'transcript':'','transcript_origin':'auto','bpm':'145',
    'humor':'auto','fx_intensity':'3','style':'mixed',
    'source_hashes':hashlib.sha256(media).hexdigest()
}.items():part(k,v.encode())
parts.append(('--'+boundary+'--\r\n').encode())
job=json.loads(fetch('/api/jobs',b''.join(parts),
        {'Content-Type':'multipart/form-data; boundary='+boundary},timeout=75))
assert job.get('status_url'),job
print('WHATSAPP_VIDEO_JOB_CREATED',job['id'],flush=True)
deadline=time.monotonic()+510
state=None
while time.monotonic()<deadline:
    time.sleep(3)
    state=json.loads(fetch(job['status_url'],timeout=65))
    print('VIDEO_EDIT_STAGE',state.get('state'),state.get('percent'),
          str(state.get('label',''))[:70],flush=True)
    if state.get('state') in ('done','error'):break
assert state and state.get('state')=='done',state
assert state.get('video_status')=='done',state
assert state.get('video_mode')=='original_input_video',state
assert state.get('video_edit_style')=='beat_cut_punch_in_speed_ramp',state
assert state.get('video_edit_shots',0)>=3,state
out=pathlib.Path('/tmp/kolbo-edited-whatsapp-live.mp4')
out.write_bytes(fetch(state['video_url'],timeout=90))
assert out.stat().st_size>25000
video=json.loads(subprocess.check_output([
    'ffprobe','-v','error','-show_streams','-show_format',
    '-of','json',str(out)]))
tracks={x['codec_type']:x for x in video['streams']}
assert set(tracks)=={'video','audio'},tracks
assert tracks['video']['codec_name']=='h264',tracks
assert (tracks['video']['width'],tracks['video']['height'])==(360,640)
duration=float(video['format']['duration'])
assert 29.0<=duration<=32.0,duration
subprocess.run(['ffmpeg','-nostdin','-v','error','-ss','24','-i',
                str(out),'-frames:v','1','-f','null','-'],
               check=True,timeout=30)
print('PRODUCTION_WHATSAPP_VIDEO_BEAT_EDIT_PASS',json.dumps({
    'input_bytes':len(media),'output_bytes':out.stat().st_size,
    'shot_count':state['video_edit_shots'],'bpm':145,
    'length':duration,'codec':tracks['video']['codec_name'],
    'coverage':state.get('visual_coverage'),
    'audio_codec':tracks['audio']['codec_name'],
},ensure_ascii=False),flush=True)
