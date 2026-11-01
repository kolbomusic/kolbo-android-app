"""Live regression: missing browser transcript must not reject an upload.

An artificial tone contains NO intelligible speech and is not a valid test
of Hebrew transcription accuracy. This only tests that server-side original
media ASR is attempted, never fabricates a story, and always returns an MP3.
"""
import io, json, math, struct, time, urllib.request, urllib.error, wave
from http.cookiejar import CookieJar
from urllib.request import HTTPCookieProcessor, Request, build_opener

BASE="https://kolbo-trance-studio.onrender.com"
opener=build_opener(HTTPCookieProcessor(CookieJar()))

def fetch(path,data=None,headers=None,timeout=30):
    with opener.open(Request(BASE+path,data=data,headers=headers or {}),timeout=timeout) as r:
        return r.status,r.read()

def main():
    status,raw=fetch('/health')
    meta=json.loads(raw)
    assert status==200 and meta['ok'],meta
    fetch('/studio')
    source=io.BytesIO()
    with wave.open(source,'wb') as wav:
        sr=8000
        wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(sr)
        samples=[int(10000*math.sin(2*math.pi*400*t/sr))
                 for t in range(sr*2)]
        wav.writeframes(struct.pack('<%dh'%len(samples),*samples))
    boundary="----KolboOriginalASRRecoveryNov01"
    parts=[]
    def field(name,value,filename=None,typ=None):
        header="--"+boundary+"\r\nContent-Disposition: form-data; name=\""+name+"\""
        if filename:header+="; filename=\""+filename+"\""
        header+="\r\n"
        if typ:header+="Content-Type: "+typ+"\r\n"
        parts.append(header.encode()+b"\r\n"+value+b"\r\n")
    field('audio',source.getvalue(),'original-no-speech.wav','audio/wav')
    for k,v in {'make_video':'on','video_requested':'on',
                'transcript':'','transcription_failed':'on',
                'transcript_origin':'auto','seconds':'30','humor':'auto'}.items():
        field(k,v.encode())
    parts.append(("--"+boundary+"--\r\n").encode())
    status,raw=fetch('/api/jobs',b''.join(parts),
        {'Content-Type':'multipart/form-data; boundary='+boundary},timeout=60)
    assert status==202,(status,raw[:400])
    job=json.loads(raw)
    result={}
    for _ in range(195):
        time.sleep(2)
        _,raw=fetch(job['status_url'],timeout=30)
        result=json.loads(raw)
        if result.get('state') in ('done','error'):break
    else:raise TimeoutError("Server original ASR recovery did not finish")
    assert result.get('state')=='done',result
    assert result.get('engine')=='semantic_footage_with_original_asr_recovery_v5',result
    assert result.get('video_status')=='unavailable',(
        "A synthetic tone must not hallucinate a real-life video!",result)
    assert result.get('storyboard_source')=='original_asr_failed',result
    assert result.get('voice_coverage')=='full',result
    assert 'video_url' not in result,result
    s,mp3=fetch(result['download_url'],timeout=60)
    assert s==200 and len(mp3)>12000,len(mp3)
    print(json.dumps({'status':'passed','mp3_bytes':len(mp3),
        'video_status':result.get('video_status'),'cloud_version':meta.get('version'),
        'scope':'No speech; recovery pathway and honest refusal only'}))
if __name__=="__main__":main()
