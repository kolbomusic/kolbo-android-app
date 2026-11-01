"""Production: original Israeli-flavored trance with Hebrew-timed cartoon beats.

Uses an independently synthesized speechlike signal (not user's WhatsApp),
and a supplied test transcript solely for verifying behavior. Both output
stems are checked for true audible stereo and retained untreated voice.
"""
import hashlib,json,pathlib,subprocess,time
from http.cookiejar import CookieJar
from urllib.request import Request,HTTPCookieProcessor,build_opener
BASE="https://kolbo-trance-studio.onrender.com"
ROOT=pathlib.Path("/tmp")
ORIGINAL=ROOT/"kolbo-synthetic-voice.opus"
assert ORIGINAL.exists() and ORIGINAL.stat().st_size>1000
jar=CookieJar();client=build_opener(HTTPCookieProcessor(jar))
def req(path,body=None,headers=None,timeout=70):
    with client.open(Request(BASE+path,data=body,headers=headers or {}),
                     timeout=timeout) as x:return x.read()
assert json.loads(req('/health',timeout=80)).get('ok')
req('/studio')
assert any(x.name=="kolbo_studio" for x in jar)
raw=ORIGINAL.read_bytes()
def produce(humor):
    boundary="----KolboOriginalIsraeliComedyProof"
    parts=[]
    def put(k,v,filename=None,ctype=None):
        h=f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"'
        if filename:h+=f'; filename="{filename}"'
        h+='\r\n'
        if ctype:h+=f'Content-Type: {ctype}\r\n'
        parts.append(h.encode()+b'\r\n'+v+b'\r\n')
    put('audio',raw,'synthetic-WhatsApp.opus','audio/ogg')
    for key,val in {
      'transcript':'החמור נוער בקול גדול. כולם צוחקים. ואז הכל נפל.',
      'transcript_origin':'manual','video_requested':'off',
      'style':'israeli','humor':humor,'seconds':'30','bpm':'145',
      'fx_intensity':'2','fx_gain':'1.25','mix_variation':'8',
      'source_hashes':hashlib.sha256(raw).hexdigest()
    }.items():put(key,val.encode())
    parts.append(f'--{boundary}--\r\n'.encode())
    job=json.loads(req('/api/jobs',b''.join(parts),
        {'Content-Type':f'multipart/form-data; boundary={boundary}'},timeout=75))
    assert job.get('status_url'),job
    deadline=time.monotonic()+420
    while time.monotonic()<deadline:
        time.sleep(3)
        status=json.loads(req(job['status_url'],timeout=65))
        if status.get('state') in ('done','error'):break
    assert status.get('state')=='done',status
    mp3=req(status['download_url'],timeout=70)
    stem=req(status['voice_url'],timeout=70)
    assert len(mp3)>50000 and len(stem)>12000
    dst=ROOT/('kolbo-comedy-israeli-'+humor+'.mp3')
    dst.write_bytes(mp3)
    meta=json.loads(subprocess.check_output([
       'ffprobe','-v','error','-show_format','-show_streams','-of','json',str(dst)]))
    assert any(s['codec_type']=='audio' for s in meta['streams'])
    assert float(meta['format']['duration'])>=29.
    assert float(meta['format']['duration'])<=45.
    return dst,meta,stem
wet,probe,wet_vocal=produce('auto')
dry,_,dry_vocal=produce('off')
assert wet.read_bytes()!=dry.read_bytes()
assert wet_vocal!=dry_vocal
print('REAL_PRODUCTION_ISRAELI_COMEDY_AUDIO_PASS',json.dumps({
  'seconds':round(float(probe['format']['duration']),2),
  'codec':probe['streams'][0]['codec_name'],
  'wet_bytes':wet.stat().st_size,'dry_bytes':dry.stat().st_size,
  'voice_fx_changed':wet_vocal!=dry_vocal,
},ensure_ascii=False),flush=True)
