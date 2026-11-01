"""Bounded public-provider sanity check; never uses a user's transcript.

Single synthetic 'moving red ball' clip, no private data, no retry storm.
A free ZeroGPU error is reported accurately; never assert a video exists
without a decoded MP4 from that provider.
"""
import json,pathlib,subprocess,sys,time,urllib.request,urllib.error
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from ai_video import _request_video_generation,_request_ltx25_generation,_download_public_video,AIVideoUnavailable
prompt=("A real handheld video of a bright red tennis ball bouncing twice "
        "on a plain table in daylight, continuous clear physical motion, "
        "no words or text.")
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
else:
    print('NO_PUBLIC_AI_PROVIDER_AVAILABLE',failures,flush=True)
    sys.exit(1)
