"""Prove original upload bytes, authenticated job and fallback MP4 on live Render."""
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
    assert version=='1.11.1',('Old live server',version)
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
    assert result.get('video_status')=='done',result
    assert result.get('video_mode')=='voice_reactive',result
    assert result.get('visual_coverage')=='voice_only',result
    movie,status=api(result['video_url'],timeout=90)
    assert status==200 and b'ftyp' in movie[:28],(status,movie[:28])
    output=pathlib.Path('/tmp/kolbo-voice-fallback-live.mp4')
    output.write_bytes(movie)
    meta=json.loads(subprocess.check_output(['ffprobe','-v','quiet',
        '-show_format','-show_streams','-of','json',str(output)]))
    duration=float(meta['format']['duration'])
    assert 29<=duration<=32,duration
    assert {s['codec_type'] for s in meta['streams']}=={'audio','video'}
    print('SUCCESS_ORIGINAL_SOURCE_HEBREW_FALLBACK',json.dumps({
        'server':version,'mp4_bytes':len(movie),'duration':duration,
        'mode':result['video_mode'],'source_hash_bound':True,
        'scope':'synthetic audio transport test, not Hebrew ASR quality'},ensure_ascii=False))
if __name__=='__main__':main()
