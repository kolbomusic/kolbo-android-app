"""Prove original-upload fingerprint, honest semantic-only refusal, and MP3 on live Render."""
import hashlib
import io
import json
import math
import os
import pathlib
import struct
import subprocess
import time
import urllib.error
import urllib.request
import wave
from http.cookiejar import CookieJar
from urllib.request import HTTPCookieProcessor, Request, build_opener

BASE=os.environ.get('KOLBO_TRANCE_URL','https://kolbo-trance-studio.onrender.com')
jar=CookieJar()
browser=build_opener(HTTPCookieProcessor(jar))
def api(path,payload=None,headers=None,timeout=50):
    with browser.open(Request(BASE+path,data=payload,headers=headers or {}),timeout=timeout) as r:
        return r.read(),r.status

def main():
    data,status=api('/health')
    version=json.loads(data)['version']
    assert version=='1.13.0',('Old live server',version)
    _,status=api('/studio')
    assert status==200
    wav=io.BytesIO()
    with wave.open(wav,'wb') as w:
        sr=8000
        w.setnchannels(1);w.setsampwidth(2);w.setframerate(sr)
        samples=[int(12000*math.sin(2*math.pi*228*i/sr))
                 for i in range(sr*2)]
        w.writeframes(struct.pack('<%dh'%len(samples),*samples))
    raw=wav.getvalue()
    boundary='----KolboActualSourceOneClick'
    parts=[]
    def field(name,value,filename=None,content_type=None):
        head='--'+boundary+'\r\nContent-Disposition: form-data; name="'+name+'"'
        if filename:head+='; filename="'+filename+'"'
        head+='\r\n'
        if content_type:head+='Content-Type: '+content_type+'\r\n'
        parts.append(head.encode()+b'\r\n'+value+b'\r\n')
    field('audio',raw,'real-source.wav','audio/wav')
    for k,v in {
        'make_video':'on',
        'video_requested':'on',
        'transcript':'אני לא יודע מה קרה כאן. אולי מישהו יבוא אחר כך.',
        'transcript_origin':'auto',
        'source_hashes':hashlib.sha256(raw).hexdigest(),
        'seconds':'30',
        'fx_intensity':'2',
        'humor':'chaos'
    }.items():field(k,v.encode())
    parts.append(('--'+boundary+'--\r\n').encode())
    headers={'Content-Type':'multipart/form-data; boundary='+boundary}
    payload=b''.join(parts)
    body,status=api('/api/jobs',payload,headers,timeout=60)
    assert status==202,(status,body)
    path=json.loads(body)['status_url']
    result={}
    for _ in range(170):
        time.sleep(2)
        body,_=api(path,timeout=50)
        result=json.loads(body)
        if result.get('state') in ('done','error'):break
    else:raise TimeoutError('No response from free Render in 340 seconds')
    assert result.get('state')=='done',result
    assert result.get('video_status')=='unavailable',result
    assert result.get('storyboard_source')=='no_grounded_story',result
    assert 'video_url' not in result,result
    assert result.get('visual_coverage')=='none',result
    assert 'וידאו' in result.get('video_error',''),result
    audio,status=api(result['download_url'],timeout=60)
    assert status==200 and len(audio)>12000,(status,len(audio))
    print('PASS_NO_FALSE_STORY_VIDEO',json.dumps({
        'server':version,'mp3_bytes':len(audio),'no_waveform':True,
        'source_hash_bound':True,
        'scope':'synthetic speech transport test; not ASR quality'},ensure_ascii=False))

if __name__=='__main__':main()
