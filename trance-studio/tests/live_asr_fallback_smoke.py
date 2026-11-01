"""Live backend contract when the Android browser supplies NO transcript.

Uses synthetic tone, not a real Hebrew speaker. This validates ASR execution
and failure handling, NOT speech recognition quality or source matching.
"""
import hashlib
import io
import json
import math
import os
import struct
import time
import urllib.request
import wave
from http.cookiejar import CookieJar
from urllib.request import HTTPCookieProcessor, Request, build_opener

BASE=os.environ.get('KOLBO_TRANCE_URL','https://kolbo-trance-studio.onrender.com')
client=build_opener(HTTPCookieProcessor(CookieJar()))


def call(path,body=None,headers=None,timeout=60):
    with client.open(Request(BASE+path,data=body,headers=headers or {}),timeout=timeout) as r:
        return r.status,r.read()


def source():
    buf=io.BytesIO()
    with wave.open(buf,'wb') as w:
        sr=8000
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        sample=[int(8500*math.sin(2*math.pi*230*i/sr)) for i in range(2*sr)]
        w.writeframes(struct.pack('<%dh'%len(sample),*sample))
    return buf.getvalue()


def main():
    code,health=call('/health')
    meta=json.loads(health)
    assert code==200 and meta['ok'],meta
    assert meta.get('asr_preloaded') is True,('ASR model not baked into image',meta)
    assert call('/studio')[0]==200

    raw=source()
    boundary='----KolboASRSourceFallbackSmoke'
    fields=[('make_video','on'),('video_requested','on'),('transcript',''),
            ('transcript_origin','auto'),('seconds','30'),
            ('source_hashes',hashlib.sha256(raw).hexdigest())]
    parts=[]
    def part(name,value,filename=None):
        head='--'+boundary+'\r\nContent-Disposition: form-data; name="'+name+'"'
        if filename:head+='; filename="'+filename+'"'
        head+='\r\n\r\n'
        parts.append(head.encode()+value+b'\r\n')
    part('audio',raw,'original.wav')
    for name,value in fields:part(name,value.encode())
    parts.append(('--'+boundary+'--\r\n').encode())
    code,submitted=call('/api/jobs',b''.join(parts),{
        'Content-Type':'multipart/form-data; boundary='+boundary})
    assert code==202,(code,submitted.decode(errors='replace'))
    job=json.loads(submitted)
    result=None
    for _ in range(150):
        time.sleep(2)
        _,raw_status=call(job['status_url'])
        result=json.loads(raw_status)
        if result.get('state') in ('done','error'):break
    assert result is not None and result.get('state')=='done',result
    assert result.get('asr_recovery_attempted') is True,result
    assert result.get('asr_recovery_status') in ('unavailable','recognized'),result
    assert result.get('video_status') in ('unavailable','done','error'),result
    assert result.get('engine')=='semantic_footage_with_original_asr_recovery_v5',result
    message=result.get('video_error','')
    assert 'מנוע התמלול בשרת אינו מותקן' not in message, message
    assert 'לא ניתן לטעון את מודל זיהוי הדיבור' not in message, message
    assert result.get('download_url') and call(result['download_url'])[0]==200,result
    print(json.dumps({'result':'PASS','source':'synthetic_no_transcript',
        'asr_preloaded':meta['asr_preloaded'],
        'asr_status':result['asr_recovery_status'],
        'video_status':result['video_status'],
        'mp3_download':True},ensure_ascii=False))


if __name__=='__main__':main()
