"""Real, consented synthetic Hebrew narration -> new AI H264/AAC movie on Render.

Not user audio. This proof must reject any original/source-footage substitution.
"""
import hashlib,json,pathlib,subprocess,time
from http.cookiejar import CookieJar
from urllib.request import Request,HTTPCookieProcessor,build_opener
BASE='https://kolbo-trance-studio.onrender.com'
ROOT=pathlib.Path('/tmp')
SOURCE=ROOT/'kolbo-fake-whatsapp.opus'
assert SOURCE.exists() and SOURCE.stat().st_size>1000
jar=CookieJar();client=build_opener(HTTPCookieProcessor(jar))
def get(path,body=None,headers=None,timeout=75):
    with client.open(Request(BASE+path,data=body,headers=headers or {}),
                     timeout=timeout) as response:return response.read()
assert json.loads(get('/health',timeout=80))['ok']
get('/studio')
assert any(c.name=='kolbo_studio' for c in jar)
raw=SOURCE.read_bytes()
boundary='----KolboLiveTrueAIGenerationNov2026'
parts=[]
def add(name,data,filename=None,typ=None):
    h='--'+boundary+'\r\nContent-Disposition: form-data; name="'+name+'"'
    if filename:h+='; filename="'+filename+'"'
    h+='\r\n'
    if typ:h+='Content-Type: '+typ+'\r\n'
    parts.append(h.encode()+b'\r\n'+data+b'\r\n')
add('audio',raw,'fictional-voice.opus','audio/ogg')
for name,value in {
 'transcript':'האיש רוקד במהירות על הבמה וכולם צוחקים.',
 'transcript_origin':'manual','video_strategy':'new_story',
 'ai_video_consent':'on','make_video':'on','video_requested':'on',
 'source_hashes':hashlib.sha256(raw).hexdigest(),'seconds':'30',
 'style':'israeli','bpm':'145','humor':'auto','fx_intensity':'2',
 'fx_gain':'1.3','mix_variation':'9'
}.items():add(name,value.encode())
parts.append(('--'+boundary+'--\r\n').encode())
job=json.loads(get('/api/jobs',b''.join(parts),{
 'Content-Type':'multipart/form-data; boundary='+boundary},timeout=75))
assert job.get('status_url'),job
print('PRODUCTION_NEW_AI_JOB',job['id'],flush=True)
deadline=time.monotonic()+390
while time.monotonic()<deadline:
    time.sleep(4)
    state=json.loads(get(job['status_url'],timeout=65))
    print('STATE',state.get('state'),state.get('percent'),str(state.get('label'))[:60],flush=True)
    if state.get('state') in ('done','error'):break
assert state.get('state')=='done',state
assert state.get('video_status')=='done',state
assert str(state.get('video_mode','')).startswith('ai_generated'),state
assert state.get('storyboard_source')!='original_shared_video',state
assert state.get('ai_clips_generated',0)>=1,state
movie=ROOT/'kolbo-full-new-ai-story-live.mp4'
movie.write_bytes(get(state['video_url'],timeout=90))
info=json.loads(subprocess.check_output([
 'ffprobe','-v','error','-show_format','-show_streams','-of','json',str(movie)],timeout=25))
tracks={s['codec_type']:s for s in info['streams']}
assert set(tracks)=={'video','audio'},info
assert tracks['video']['codec_name']=='h264',tracks
assert 28.5<=float(info['format']['duration'])<=40,info
assert movie.stat().st_size>35000
subprocess.run(['ffmpeg','-nostdin','-v','error','-ss','20','-i',str(movie),
 '-frames:v','1','-f','null','-'],timeout=25,check=True)
print('REAL_PRODUCTION_NEW_AI_STORY_MP4_PASS',json.dumps({
 'seconds':info['format']['duration'],'clip_count':state['ai_clips_generated'],
 'ai_motion_seconds':state.get('ai_clip_seconds'),
 'size':movie.stat().st_size,'width':tracks['video']['width'],
 'height':tracks['video']['height'],'codec':tracks['video']['codec_name']
},ensure_ascii=False),flush=True)
