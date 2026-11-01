"""Live remote HTTP contract test: real uploaded audio -> MP3 and authentic licensed live video MP4.
No login secrets. A short synthetic voice-like waveform is used instead of
claiming that an actual Hebrew WhatsApp recording was provided.
"""
import io, json, math, os, struct, subprocess, time, urllib.request, urllib.error, wave
from http.cookiejar import CookieJar
from urllib.request import HTTPCookieProcessor, Request, build_opener

BASE=os.environ.get('KOLBO_TRANCE_URL','https://kolbo-trance-studio.onrender.com')
jar=CookieJar()
client=build_opener(HTTPCookieProcessor(jar))
def call(path,body=None,headers=None,timeout=35):
    with client.open(Request(BASE+path,data=body,headers=headers or {}),
                     timeout=timeout) as r:
        return r.read(),dict(r.headers),r.status

def main():
    d,_,_=call('/health')
    meta=json.loads(d)
    assert meta.get('ok'),meta
    assert meta.get('version')=='1.13.0',meta
    page,_,_=call('/studio')
    assert b'videoResult' in page and b'videoNotice' in page and b'transcriptDetails' not in page
    assert any(c.name=='kolbo_studio' for c in jar),'server studio session cookie missing'
    wav=io.BytesIO()
    with wave.open(wav,'wb') as w:
        w.setnchannels(1);w.setsampwidth(2);w.setframerate(8000)
        samples=[int(9000*math.sin(2*math.pi*251*i/8000)) for i in range(8000*2)]
        w.writeframes(struct.pack('<%dh'%len(samples),*samples))
    boundary='----KolboSmokeContractBound6cbb'
    parts=[]
    def field(name,content,filename=None,ctype=None):
        h='--'+boundary+'\r\nContent-Disposition: form-data; name="'+name+'"'
        if filename:h+='; filename="'+filename+'"'
        h+='\r\n'
        if ctype:h+='Content-Type: '+ctype+'\r\n'
        parts.append(h.encode()+b'\r\n'+content+b'\r\n')
    field('audio',wav.getvalue(),'smoke.wav','audio/wav')
    for k,v in {'make_video':'on','video_requested':'on',
                'transcript':'. '.join(['כולם רוקדים במסיבה','אני נוסע באוטו']*4)+'.',
                'transcript_origin':'auto','seconds':'60','humor':'auto','fx_intensity':'2','fx_gain':'1.25'}.items():
        field(k,v.encode())
    parts.append(('--'+boundary+'--\r\n').encode())
    try:
        body,_,status=call('/api/jobs',b''.join(parts),{'Content-Type':'multipart/form-data; boundary='+boundary},timeout=50)
    except urllib.error.HTTPError as e:
        raise AssertionError('POST failed '+str(e.code)+' '+e.read().decode(errors='replace')[:400])
    assert status==202,(status,body)
    state=json.loads(body)
    path=state['status_url']
    for i in range(180):
        time.sleep(2)
        d,_,_=call(path)
        result=json.loads(d)
        if result['state'] in ('done','error'):break
    else:raise TimeoutError('remote job did not complete in six minutes')
    assert result['state']=='done',result
    assert result.get('engine')=='semantic_footage_with_original_asr_recovery_v5', result
    assert result['video_status']=='done',result
    assert result['storyboard_source']=='automatic_transcript_grounded_longform',result
    preview,headers,status_code=call(result['video_preview_url'],timeout=75)
    assert status_code==200
    assert 'attachment' not in headers.get('Content-Disposition',''),headers
    assert b'ftyp' in preview[:24]
    audio,_,_=call(result['download_url'],timeout=75)
    video,_,_=call(result['video_url'],timeout=75)
    storyboard,_,_=call(result['storyboard_url'])
    assert audio[:3]==b'ID3' or audio[:2] in (b'\\xff\\xfb',b'\\xff\\xf3'),audio[:12]
    assert b'ftyp' in video[:24],video[:24]
    assert len(video)>25000
    scenes=json.loads(storyboard)['scenes']
    assert [s['action'] for s in scenes]==['person_dance','car_drive']*4,scenes
    assert result.get('visual_beats')==8,result
    assert result.get('unmatched_clauses')==0,result
    with open('/tmp/kolbo-story-smoke.mp4','wb') as f:f.write(video)
    probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams',
            '-show_format','-of','json','/tmp/kolbo-story-smoke.mp4']))
    tracks={stream['codec_type'] for stream in probe['streams']}
    assert tracks=={'audio','video'},tracks
    duration=float(probe['format']['duration'])
    assert 59<=duration<=85,duration
    print(json.dumps({'status':'passed','api_version':meta['version'],
        'mp4_bytes':len(video),'mp3_bytes':len(audio),'duration':duration,
        'scene_types':[s['action'] for s in scenes],
        'tracks':sorted(tracks)},ensure_ascii=False))
if __name__=='__main__':main()
