"""Optional legacy Agnes Video v2.0 backend (NOT automatically zero-cost).

The documented API differs from Flash: text2video, single-image img2video,
or *keyframe morphing*. Two keyframes are NOT dual-person identity references.
Operator must separately enable this after verifying account-specific price.
"""
from __future__ import annotations
import re,time
from urllib.parse import urlencode
import agnes_adapter

MODEL='agnes-video-v2.0'

def payload(prompt:str,seconds:int,urls:list[str],*,two_reference_experimental=False)->dict:
    if not 4<=seconds<=12:raise ValueError('Legacy Agnes supports 4..12s in this app')
    if len(urls)>2:raise ValueError('At most two images')
    if len(urls)>1 and not two_reference_experimental:
        raise ValueError('Two independent identities require a validated dual-reference model')
    if not 3<=len(prompt)<=4000:raise ValueError('Invalid video prompt')
    frames=8*round((seconds*24-1)/8)+1
    result={'model':MODEL,'prompt':prompt,'width':1152,'height':768,
            'num_frames':frames,'frame_rate':24}
    if len(urls)==1:result['image']=urls[0]
    if len(urls)==2:
        # Keyframe interpolation can morph identity. Must be explicit.
        result['extra_body']={'mode':'keyframes','image':urls}
    return result

def submit(prompt:str,seconds:int,urls:list[str],key:str,*,two_reference_experimental=False)->str:
    info=agnes_adapter.api_json('POST','/v1/videos',key,
        payload(prompt,seconds,urls,two_reference_experimental=two_reference_experimental),
        timeout=70)
    task=info.get('video_id') or info.get('task_id') or info.get('id')
    if task is None:
        response=' '.join(str(info.get(f,''))[:140] for f in
                          ('code','message','error','status')).lower()
        if any(e in response for e in ('video_queue_full','queue_full','queue full','rate_limit')):
            raise agnes_adapter.AgnesQueueFull('Agnes v2.0 queue is full')
    if not isinstance(task,str) or not re.fullmatch(r'[A-Za-z0-9_-]{4,128}',task):
        raise agnes_adapter.AgnesError('Agnes v2.0 did not return a valid task ID')
    return task

def poll(video_id:str,key:str,deadline:float,on_progress=None)->str:
    if not isinstance(video_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{4,128}',video_id):
        raise ValueError('Invalid video task ID')
    path='/agnesapi?'+urlencode({'video_id':video_id,'model_name':MODEL})
    while time.monotonic()<deadline:
        info=agnes_adapter.api_json('GET',path,key,timeout=35)
        status=info.get('status')
        if status=='completed':
            meta=info.get('metadata') if isinstance(info.get('metadata'),dict) else {}
            url=info.get('video_url') or info.get('url') or meta.get('url')
            if not isinstance(url,str) or not url.startswith('https://'):
                raise agnes_adapter.AgnesError('Legacy Agnes returned no verified video URL')
            return url
        if status=='failed':
            raise agnes_adapter.AgnesError('Legacy Agnes could not complete the video')
        if status not in ('queued','in_progress','pending','processing'):
            raise agnes_adapter.AgnesError('Unexpected legacy provider status')
        if on_progress:
            n=info.get('progress',0)
            if isinstance(n,(int,float)) and 0<=n<=100:
                on_progress('Agnes v2.0 processing: '+str(int(n))+'%')
        time.sleep(2.5)
    raise agnes_adapter.AgnesError('Legacy Agnes timed out; do not resubmit automatically')
