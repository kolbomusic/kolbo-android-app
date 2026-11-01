"""Production acceptance: licensed Hebrew music backing and true story-only mode.

Generates synthetic footage, fictional Hebrew speech and a locally synthesized
440 Hz music file. No private user media and no copyrighted YouTube audio.
"""
import array,hashlib,json,math,pathlib,subprocess,time
from http.cookiejar import CookieJar
from urllib.request import Request,HTTPCookieProcessor,build_opener
BASE="https://kolbo-trance-studio.onrender.com"
ROOT=pathlib.Path("/tmp")
ORIGINAL=ROOT/"kolbo-rights-test-video.mp4"
MUSIC=ROOT/"kolbo-rights-test-music.mp3"
jar=CookieJar()
client=build_opener(HTTPCookieProcessor(jar))
def req(path,payload=None,headers=None,timeout=75):
    with client.open(Request(BASE+path,data=payload,headers=headers or {}),
                     timeout=timeout) as response:
        return response.read()
assert json.loads(req('/health',timeout=75)).get('ok')
req('/studio',timeout=75)
assert any(c.name=="kolbo_studio" for c in jar)
assert ORIGINAL.is_file() and MUSIC.is_file()
def submit(strategy,with_music):
    boundary="----KolboLicensedMusicVerification2026"
    parts=[]
    def add(name,val,filename=None,ctype=None):
        h=f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"'
        if filename:h+=f'; filename="{filename}"'
        h+='\r\n'
        if ctype:h+=f'Content-Type: {ctype}\r\n'
        parts.append(h.encode()+b'\r\n'+val+b'\r\n')
    video=ORIGINAL.read_bytes()
    add('audio',video,'whatsapp-test.mp4','video/mp4')
    if with_music:
        add('backing_music',MUSIC.read_bytes(),'royalty-free-original.mp3','audio/mpeg')
        add('music_license_ack',b'on')
    values={
        'video_strategy':strategy,'video_requested':'on','make_video':'on',
        'transcript':'שלום לכולם היום סיפור חדש','transcript_origin':'manual',
        'ai_video_consent':'off','source_hashes':hashlib.sha256(video).hexdigest(),
        'bpm':'145','seconds':'30','humor':'auto','fx_intensity':'2'}
    for name,value in values.items():add(name,value.encode())
    parts.append(f'--{boundary}--\r\n'.encode())
    job=json.loads(req('/api/jobs',b''.join(parts),
        {'Content-Type':f'multipart/form-data; boundary={boundary}'},timeout=75))
    assert job.get('status_url'),job
    print('ACCEPTED',strategy,job['id'],flush=True)
    deadline=time.monotonic()+410
    while time.monotonic()<deadline:
        time.sleep(3)
        state=json.loads(req(job['status_url'],timeout=75))
        if state['state'] in ('done','error'):return state
    raise AssertionError('PRODUCTION_JOB_TIMED_OUT: '+strategy)
a=submit('remix_original',True)
assert a['state']=='done',a
assert a['video_status']=='done',a
assert a['video_edit_shots']>=3,a
assert a['video_mode']=='original_input_video',a
song_file=ROOT/'kolbo-licensed-production-proof.mp3'
song_file.write_bytes(req(a['download_url'],timeout=90))
assert song_file.stat().st_size>20000
video_file=ROOT/'kolbo-licensed-production-proof.mp4'
video_file.write_bytes(req(a['video_url'],timeout=90))
info=json.loads(subprocess.check_output(['ffprobe','-v','error',
    '-show_format','-show_streams','-of','json',str(video_file)]))
assert {x['codec_type'] for x in info['streams']}=={'video','audio'}
assert float(info['format']['duration'])>29
samples=subprocess.check_output(['ffmpeg','-nostdin','-v','error',
    '-ss','0.3','-t','0.8','-i',str(song_file),'-ac','1','-ar','8000',
    '-f','f32le','pipe:1'],timeout=45)
w=array.array('f');w.frombytes(samples)
def tone(freq):
    x=sum(v*math.sin(2*math.pi*freq*i/8000) for i,v in enumerate(w))
    y=sum(v*math.cos(2*math.pi*freq*i/8000) for i,v in enumerate(w))
    return math.hypot(x,y)/len(w)
ratio=tone(440)/max(1e-8,tone(550))
assert ratio>4,('CUSTOM_MUSIC_NOT_HEARD',ratio)
print('LICENSED_MUSIC_REAL_MP3_AND_MP4_PASS',
      {'duration':info['format']['duration'],
       'shots':a['video_edit_shots'],'original_440_to_550':round(ratio,2)},
      flush=True)
# This is the user's requested distinction: never quietly reuse the original
# recording when they selected a new, independent story. It is acceptable for
# a free provider to report unavailable, but not to pass the old video as new.
b=submit('new_story',False)
assert b['state']=='done',b
assert b['video_mode']!='original_input_video',b
assert b.get('storyboard_source')!='original_shared_video',b
print('NEW_STORY_NEVER_REUSES_ORIGINAL_VIDEO_PASS',
      {'status':b.get('video_status'),
       'mode':b.get('video_mode'),
       'storyboard_source':b.get('storyboard_source')},flush=True)
