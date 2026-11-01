"""Bounded public-provider sanity check; never uses a user's transcript.

Single synthetic 'moving red ball' clip, no private data, no retry storm.
A free ZeroGPU error is reported accurately; never assert a video exists
without a decoded MP4 from that provider.
"""
import json,pathlib,subprocess,sys,time,urllib.request,urllib.error
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from ai_video import _request_video_generation,_request_ltx25_generation,_download_public_video,AIVideoUnavailable
from narrative_plan import narrative_beats,scene_prompt
# Use the EXACT kind of mixed English+Hebrew scene prompt submitted by the
# Kolbo server, not a conveniently short English-only proof.
prompt=scene_prompt(narrative_beats("האיש רוקד במהירות על הבמה וכולם צוחקים.")[0])
def public_error_diagnostic(provider):
    """Only synthetic canary prompt; no user text is transmitted or printed."""
    if provider=='distilled':
        endpoint="https://lightricks-ltx-video-distilled.hf.space/gradio_api/call/text_to_video"
        payload={"data":[prompt,"bad quality, text",None,None,512,704,
                         "text-to-video",1,9,42,True,1.0,True]}
    else:
        endpoint="https://lightricks-ltx-2-5.hf.space/gradio_api/call/v2/run"
        payload={"prompt":prompt,"image_path":None,"height":512,
                 "width":768,"duration_s":1,"seed":42,
                 "decoder":"conv","auto_len":False,
                 "randomize_seed":False,"do_enhance":False}
    try:
        req=urllib.request.Request(endpoint,
              data=json.dumps(payload).encode('utf-8'),
              headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=15) as resp:
            event=json.load(resp)
        event_id=event.get('event_id')
        if not event_id:return {"submission":"missing_event_id"}
        uri=(endpoint.replace('/v2/run','/run') if provider=='ltx25' else endpoint)+'/'+event_id
        with urllib.request.urlopen(uri,timeout=20) as stream:
            for raw in stream:
                line=raw.decode('utf-8','replace').strip()
                if line.startswith('data:'):
                    data=line[5:].strip()
                    if data:
                        # Never print a prompt, traceback, provider secret,
                        # or full body; only the machine-readable error type.
                        try:
                            body=json.loads(data)
                            detail=str(body.get('error') or body.get('message')
                                       or body.get('detail') or '')
                            return {"payload_keys":list(body)[:6],
                                    "error_excerpt":detail[:140]}
                        except (ValueError,AttributeError):
                            return {"data_kind":"nonjson"}
        return {"status":"no_event"}
    except urllib.error.HTTPError as e:
        return {"http_status":e.code}
    except Exception as e:
        return {"exception":type(e).__name__}
failures=[]
for provider,fn in [
    ("distilled",lambda:_request_video_generation(prompt,duration=1,max_wait=58)),
    ("ltx25",lambda:_request_ltx25_generation(prompt,duration=1,max_wait=58))
]:
    try:
        print('PROVIDER_ATTEMPT',provider,flush=True)
        url=fn()
        path=pathlib.Path('/tmp/kolbo-public-video-canary.mp4')
        length=_download_public_video(url,path)
        info=json.loads(subprocess.check_output([
            'ffprobe','-v','error','-show_format','-show_streams',
            '-of','json',str(path)],timeout=25))
        video=next(s for s in info['streams'] if s['codec_type']=='video')
        assert path.stat().st_size>12000
        print('REAL_PUBLIC_AI_VIDEO_PASS',json.dumps({
            'provider':provider,'duration':length,
            'bytes':path.stat().st_size,'codec':video['codec_name'],
            'width':video['width'],'height':video['height']}),flush=True)
        break
    except (AIVideoUnavailable,urllib.error.URLError,OSError,
            subprocess.SubprocessError,AssertionError) as err:
        failures.append((provider,type(err).__name__,str(err)[:120]))
        print('PROVIDER_FAILED',*failures[-1],flush=True)
        print('PUBLIC_API_DIAGNOSTIC',provider,
              json.dumps(public_error_diagnostic(provider)),flush=True)
else:
    print('NO_PUBLIC_AI_PROVIDER_AVAILABLE',failures,flush=True)
    sys.exit(1)
