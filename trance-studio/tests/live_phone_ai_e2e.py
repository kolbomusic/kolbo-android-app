"""LIVE acceptance: spoken Hebrew -> private prompt -> free AI MP4 from
the caller's network -> authenticated upload -> full original soundtrack.

Synthetic voice only. Never commits or exports private WhatsApp recordings.
Requires production with version 1.14.0 and explicit AI consent. Browser CORS
is checked independently in Kolbo's cross-origin probe workflow.
"""
from __future__ import annotations
import hashlib
import http.cookiejar
import json
import os
import pathlib
import re
import subprocess
import time
import urllib.error
import urllib.request

BASE=os.environ.get("KOLBO_TRANCE_URL","https://kolbo-trance-studio.onrender.com")
VOICE=pathlib.Path("/tmp/kolbo-phone-ai-hebrew.opus")
assert VOICE.is_file() and VOICE.stat().st_size>1000
client=urllib.request.build_opener(
    urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

def request(url,body=None,headers=None,timeout=70):
    if url.startswith('/'):url=BASE+url
    req=urllib.request.Request(url,data=body,headers=headers or {})
    try:
        with client.open(req,timeout=timeout) as resp:
            return resp.read(),resp.status
    except urllib.error.HTTPError as exc:
        raise RuntimeError('HTTP '+str(exc.code)+' '+url.split('?')[0]+' '+exc.read(160).decode('utf-8','replace')) from exc

health=json.loads(request('/health')[0])
assert health.get('ok') and health.get('version')=='1.14.0',health
request('/studio')
voice=VOICE.read_bytes()
boundary='----KolboMobileOriginalSpeechCF2026'
parts=[]
def part(name,value,filename=None,mimetype=None):
    h='--'+boundary+'\r\nContent-Disposition: form-data; name="'+name+'"'
    if filename:h+='; filename="'+filename+'"'
    h+='\r\n'
    if mimetype:h+='Content-Type: '+mimetype+'\r\n'
    parts.append(h.encode()+b'\r\n'+value+b'\r\n')
part('audio',voice,'original.opus','audio/ogg')
for k,v in {'video_requested':'on','make_video':'on',
            'ai_video_consent':'on','source_hashes':hashlib.sha256(voice).hexdigest(),
            'transcript':'','transcript_origin':'auto','seconds':'30','bpm':'145',
            'humor':'auto','style':'mixed'}.items():
    part(k,str(v).encode())
parts.append(('--'+boundary+'--\r\n').encode())
body,code=request('/api/jobs',b''.join(parts),
    {'Content-Type':'multipart/form-data; boundary='+boundary},timeout=80)
assert code==202,(code,body[:300])
job=json.loads(body)
print('MOBILE_LIVE_HEBREW_JOB_ACCEPTED',job['id'],flush=True)
deadline=time.monotonic()+340
state={}
while time.monotonic()<deadline:
    time.sleep(3)
    state=json.loads(request(job['status_url'])[0])
    print('MOBILE_LIVE_STAGE',state.get('state'),state.get('percent'),
          state.get('label','')[:60],flush=True)
    if state.get('state') in ('done','error'):break
assert state.get('state')=='done',state
if state.get('video_status')=='done':
    print('SERVER_AI_ALREADY_PRODUCED_VIDEO',state.get('video_mode'),flush=True)
else:
    assert state.get('client_ai_fallback_available'),state
    plan=json.loads(request('/api/jobs/'+job['id']+'/ai-plan')[0])
    prompt=plan['prompts'][0]
    assert 20<len(prompt)<2000 and re.search('[א-ת]',prompt)
    print('CONSENTED_PRIVATE_HEBREW_PROMPT_RECEIVED','characters',len(prompt),flush=True)
    providers=[
      ('distilled','https://lightricks-ltx-video-distilled.hf.space',
       '/gradio_api/call/text_to_video',
       {'data':[prompt,'blurry, text, watermark','','',704,512,
                'text-to-video',1.0,9,42,True,1.0,True]},
       '/gradio_api/call/text_to_video/'),
      ('ltx25','https://lightricks-ltx-2-5.hf.space',
       '/gradio_api/call/v2/run',
       {'prompt':prompt,'image_path':None,'height':512,'width':768,'duration_s':1,
        'seed':42,'decoder':'conv','auto_len':False,'randomize_seed':False,
        'do_enhance':False},
       '/gradio_api/call/run/')
    ]
    video_bytes=None
    for name,base,route,payload,eventpath in providers:
        try:
            payload_raw=json.dumps(payload,ensure_ascii=False).encode('utf-8')
            initial=json.loads(request(base+route,payload_raw,
                       {'Content-Type':'application/json'},timeout=35)[0])
            event=initial['event_id']
            assert re.fullmatch('[a-f0-9]{24,80}',event)
            stream=request(base+eventpath+event,timeout=135)[0].decode('utf-8')
            video_url=None
            for b in reversed(stream.replace('\r\n','\n').split('\n\n')):
                typ=re.search(r'^event:\s*([^\n]+)',b,re.M)
                dat=re.search(r'^data:\s*([^\n]+)',b,re.M)
                if not typ or not dat:continue
                if typ.group(1)=='error':
                    raise RuntimeError('external free shared GPU returned error event')
                if typ.group(1)=='complete':
                    value=json.loads(dat.group(1))[0]
                    file=value.get('video',value)
                    video_url=file['url']
                    break
            if not video_url or not video_url.startswith(base+'/gradio_api/file='):
                raise RuntimeError('no verified mp4 URL')
            video_bytes,code=request(video_url,timeout=55)
            assert code==200 and 12000<len(video_bytes)<10*1024*1024
            assert video_bytes[4:8]==b'ftyp'
            print('MOBILE_DIRECT_AI_GENERATED',name,len(video_bytes),flush=True)
            break
        except Exception as exc:
            print('MOBILE_DIRECT_PROVIDER_UNAVAILABLE',name,type(exc).__name__,
                  str(exc)[:85],flush=True)
            video_bytes=None
    assert video_bytes,'Neither free public AI provider produced a direct original MP4'
    boundary='----KolboUploadOriginalAIMotion2026'
    payload=(('--'+boundary+'\r\nContent-Disposition: form-data; name="clip"; '
              'filename="real-moving.mp4"\r\nContent-Type: video/mp4\r\n\r\n').encode()
            +video_bytes+('\r\n--'+boundary+'--\r\n').encode())
    reply,code=request('/api/jobs/'+job['id']+'/ai-clips',
        payload,{'Content-Type':'multipart/form-data; boundary='+boundary},timeout=110)
    assert code==200,(code,reply[:400])
    result=json.loads(reply)
    assert result['video_status']=='done',result
    assert result['video_mode']=='ai_generated_client_fallback',result
    state=json.loads(request(job['status_url'])[0])
    assert state['video_status']=='done' and state.get('video_url'),state
movie,code=request(state['video_url'],timeout=100)
assert code==200 and len(movie)>25000
mp4=pathlib.Path('/tmp/kolbo-phone-ai-live-verified.mp4')
mp4.write_bytes(movie)
info=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams',
                                        '-show_format','-of','json',str(mp4)]))
tracks={s['codec_type'] for s in info['streams']}
assert tracks=={'audio','video'},tracks
video=next(s for s in info['streams'] if s['codec_type']=='video')
assert (video['codec_name'],video['width'],video['height'])==('h264',360,640),video
secs=float(info['format']['duration'])
assert 29<secs<32,secs
subprocess.run(['ffmpeg','-v','error','-ss','23','-i',str(mp4),
                '-frames:v','1','-f','null','-'],check=True)
print('LIVE_ORIGINAL_HEBREW_AUDIO_TO_MOBILE_FREE_AI_MP4_PASS',json.dumps({
    'video_mode':state.get('video_mode'),'duration':secs,
    'bytes':len(movie),'dimensions':[360,640],
    'visual_coverage':state.get('visual_coverage'),
    'speech_origin':state.get('transcript_origin'),
},ensure_ascii=False),flush=True)
