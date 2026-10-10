"""One permitted public Gradio provider test. Synthetic test image only; no customer data."""
import io, json, subprocess, time, sys
from pathlib import Path
import requests
from PIL import Image, ImageDraw
BASE='https://chopperblu-ltx-2-5-demo.hf.space'
out=Path('proof35');out.mkdir(exist_ok=True)
report={'provider':BASE,'synthetic_only':True,'duration_request':3,'success':False}
def get_event(obj):
    if isinstance(obj,dict):
        for k in ('url','video_url'):
            if isinstance(obj.get(k),str) and obj[k].startswith(BASE+'/'):return obj[k]
        for v in obj.values():
            r=get_event(v)
            if r:return r
    if isinstance(obj,list):
        for x in obj:
            r=get_event(x)
            if r:return r
    return None
try:
 im=Image.new('RGB',(512,512),(109,167,91));d=ImageDraw.Draw(im);d.ellipse((210,270,295,355),fill=(233,111,43),outline=(183,69,20),width=3)
 bio=io.BytesIO();im.save(bio,format='PNG')
 s=requests.Session();s.headers['User-Agent']='KolboVideo3.5 synthetic capability test'
 r=s.get(BASE+'/gradio_api/info',timeout=(8,25));r.raise_for_status()
 metadata=r.json();params=[p.get('parameter_name') for p in metadata['named_endpoints']['/generate_video']['parameters']]
 report['provider_parameters']=params
 print('Provider API metadata verified',params,flush=True)
 r=s.post(BASE+'/gradio_api/upload',files={'files':('synthetic.png',bio.getvalue(),'image/png')},timeout=(8,60));r.raise_for_status();p=r.json()[0]
 assert p.startswith('/') and '..' not in p
 image={'path':p,'orig_name':'synthetic.png','mime_type':'image/png','meta':{'_type':'gradio.FileData'}}
 prompt='An orange ball bounces once on fresh green meadow, locked camera, daylight, realistic physical motion, 3 seconds, no text or captions.'
 args=[prompt,image,512,512,3,False,42,False,'conv']
 r=s.post(BASE+'/gradio_api/call/generate_video',json={'data':args},timeout=(8,50));r.raise_for_status();ev=r.json()['event_id'];report['accepted_event_id']=bool(ev)
 print('VIDEO_GENERATION_JOB_SUBMITTED',flush=True)
 url=None;event='';data=[];deadline=time.monotonic()+720
 with s.get(BASE+'/gradio_api/call/generate_video/'+ev,headers={'Accept':'text/event-stream'},stream=True,timeout=(8,90)) as r:
  r.raise_for_status()
  for line in r.iter_lines(decode_unicode=True):
   if time.monotonic()>deadline:raise TimeoutError('REMOTE_GPU_TIMEOUT')
   if line is None:continue
   if isinstance(line,bytes):line=line.decode('utf8','replace')
   if line.startswith('event:'):event=line[6:].strip()
   elif line.startswith('data:'):data.append(line[5:].strip())
   elif line=='':
    if event=='error':raise RuntimeError('REMOTE_GPU_ERROR')
    if event=='complete':
     url=get_event(json.loads('\n'.join(data)));break
    event='';data=[]
 if not url:raise RuntimeError('NO_RETURNED_MEDIA')
 print('REMOTE_VIDEO_COMPLETED',flush=True)
 with s.get(url,stream=True,timeout=(8,60),allow_redirects=False) as rr:
  rr.raise_for_status();assert not rr.is_redirect
  n=0
  with (out/'remote.mp4').open('wb') as f:
   for chunk in rr.iter_content(65536):
    n+=len(chunk)
    if n>60_000_000:raise ValueError('OUTPUT_OVER_LIMIT')
    f.write(chunk)
 report['downloaded_bytes']=n
 meta=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(out/'remote.mp4')],timeout=20))
 report['actual_seconds']=float(meta['format']['duration']);report['has_video']=any(s['codec_type']=='video' for s in meta['streams']);report['has_audio']=any(s['codec_type']=='audio' for s in meta['streams']);report['success']=report['has_video'] and 2.65<=report['actual_seconds']<=3.35 and n>10000
 print('LIVE_VIDEO_RESULT',report,flush=True)
 if not report['success']:sys.exit(2)
except Exception as ex:
 report['error_type']=type(ex).__name__
 report['error_summary']=str(ex)[:100]
 print('LIVE_VIDEO_ERROR',report['error_type'],report['error_summary'],flush=True)
 sys.exit(1)
finally:
 (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))