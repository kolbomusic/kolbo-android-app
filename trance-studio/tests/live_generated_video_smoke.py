"""Live Render proof: source Hebrew speech -> consented free AI-generated video.

Synthetic words only. No customer recordings or credentials are persisted.
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
FILE=pathlib.Path("/tmp/kolbo-ai-original-hebrew.opus")
assert FILE.is_file() and FILE.stat().st_size>1000
voice=FILE.read_bytes()
jar=CookieJar()
client=build_opener(HTTPCookieProcessor(jar))

def request(path,body=None,headers=None,timeout=50):
    try:
        with client.open(Request(BASE+path,data=body,headers=headers or {}),timeout=timeout) as r:
            return r.read(),r.status
    except urllib.error.HTTPError as exc:
        raise AssertionError(f"HTTP {exc.code}: "+exc.read(800).decode(errors='replace')) from exc

health=json.loads(request('/health',timeout=60)[0])
assert health.get('ok') and health.get('asr_preloaded'),health
request('/studio',timeout=65)
assert any(c.name=='kolbo_studio' for c in jar)
boundary='----KolboAIRealSpeechZ0GPU2026'
parts=[]
def part(k,value,filename=None,mime=None):
    h=f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"'
    if filename:h+=f'; filename="{filename}"'
    h+='\r\n'
    if mime:h+=f'Content-Type: {mime}\r\n'
    parts.append(h.encode()+b'\r\n'+value+b'\r\n')
part('audio',voice,'original-hebrew.opus','audio/ogg')
for key,value in {
  'make_video':'on','video_requested':'on','ai_video_consent':'on',
  'transcript':'','transcript_origin':'auto',
  'source_hashes':hashlib.sha256(voice).hexdigest(),
  'style':'mixed','bpm':'145','seconds':'30','humor':'auto'
}.items():
    part(key,str(value).encode())
parts.append(f'--{boundary}--\r\n'.encode())
body,code=request('/api/jobs',b''.join(parts),
    {'Content-Type':f'multipart/form-data; boundary={boundary}'})
assert code==202
job=json.loads(body)
print('LIVE_AI_NARRATION_JOB_ACCEPTED',job['id'],flush=True)
deadline=time.monotonic()+540
status={}
while time.monotonic()<deadline:
    time.sleep(4)
    status=json.loads(request(job['status_url'])[0])
    print('LIVE_AI_STAGE',status.get('state'),status.get('percent'),
          status.get('label','')[:60],flush=True)
    if status.get('state') in ('error','done'):
        break
assert status.get('state')=='done',status
if status.get('video_status')!='done':
    raise AssertionError('AI generation was not available in this free-space window: '+
                         str(status.get('video_error',''))[:280])
assert status.get('video_mode')=='ai_generated_experimental',status
assert status.get('visual_coverage')=='approximate',status
assert status.get('transcript_origin')=='server_original_asr',status
assert status.get('ai_clip_seconds',0)>0.5,status
movie,_=request(status['video_url'],timeout=120)
assert len(movie)>25000
out=pathlib.Path('/tmp/kolbo-ai-production.mp4')
out.write_bytes(movie)
probe=json.loads(subprocess.check_output([
    'ffprobe','-v','error','-show_streams','-show_format','-of','json',str(out)]))
media={s['codec_type'] for s in probe['streams']}
assert media=={'audio','video'},media
v=next(s for s in probe['streams'] if s['codec_type']=='video')
assert (v['codec_name'],v['width'],v['height'])==('h264',360,640),v
duration=float(probe['format']['duration'])
assert 29<duration<32,duration
subprocess.run(['ffmpeg','-v','error','-ss','25','-i',str(out),
                '-frames:v','1','-f','null','-'],check=True,timeout=30)
print('LIVE_HEBREW_VOICE_TO_ORIGINAL_GENERATED_MP4_PASS',
      json.dumps({'duration':duration,'bytes':len(movie),
                  'distinct_ai_shots':status.get('ai_clips_generated'),
                  'origin':status['transcript_origin'],
                  'coverage':status['visual_coverage']},ensure_ascii=False),
      flush=True)
