"""Agnes Video 2.5 Flash transport, with zero paid-model fallbacks.

No third-party provider keys in Android code, GitHub or provider URLs.
This adapter does NOT prove that Agnes currently charges $0; check your account.
"""
from __future__ import annotations
import ipaddress
import json
import re
import socket
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler

BASE = 'https://apihub.agnes-ai.com'
MODEL = 'agnes-video-2.5-flash'
MAX_RESULT_BYTES = 300 * 1024 * 1024

class AgnesError(RuntimeError):
    pass

class RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        raise AgnesError('הספק החזיר הפניה לא מאומתת לקובץ וידאו')

def api_json(method: str, path: str, api_key: str, payload: dict|None=None, timeout: int=35) -> dict:
    if not path.startswith('/') or '://' in path:
        raise ValueError('נתיב ספק לא מורשה')
    body = json.dumps(payload, ensure_ascii=False).encode('utf-8') if payload is not None else None
    headers={'Authorization':'Bearer '+api_key, 'User-Agent':'KolboVideo/AgnesFlashOnly',
             'Accept':'application/json'}
    if body is not None:headers['Content-Type']='application/json'
    req=Request(BASE+path, data=body, method=method, headers=headers)
    try:
        with build_opener(RejectRedirects()).open(req,timeout=timeout) as response:
            raw=response.read(512_001)
            if len(raw)>512_000:raise AgnesError('תשובת Agnes גדולה מדי')
            result=json.loads(raw)
            if not isinstance(result,dict):raise AgnesError('תשובה לא מוכרת מספק הווידאו')
            return result
    except HTTPError as e:
        # Do not echo provider dumps; raw errors can include personal information.
        if e.code==429:raise AgnesError('מגבלת קצב או תור מלא בשירות Agnes (429)') from e
        if e.code in (401,403):raise AgnesError('מפתח Agnes אינו מורשה להפקה (401/403)') from e
        if e.code in (402,):raise AgnesError('Agnes דורש חיוב: נחסמה ההפקה במקום לעבור למסלול בתשלום') from e
        if e.code==400:raise AgnesError('בקשת ההפקה נדחתה ב־Agnes (400); בדוק טווח משך וקישורי תמונות') from e
        raise AgnesError('שגיאת שירות Agnes: HTTP '+str(e.code)) from e
    except (URLError,TimeoutError) as e:
        raise AgnesError('לא ניתן ליצור קשר עם שירות Agnes') from e

def inspect_access_without_generation(api_key:str)->dict:
    """Read-only, non-generation API probe; never creates video, spend, or balance.
    Does not certify the current account price or guarantee queue capacity.
    """
    if not api_key or len(api_key)<12:
        return {'credential_state':'missing','model_visible':False,
                'pricing_verified':False,'generation_permitted':False}
    try:
        result=api_json('GET','/v1/models',api_key,timeout=18)
    except AgnesError as exc:
        safe=str(exc)
        return {'credential_state':'rejected' if '401/403' in safe else 'unverified',
                'model_visible':False,'pricing_verified':False,
                'generation_permitted':False,'detail':safe[:160]}
    models=result.get('data')
    ids={m.get('id') for m in models if isinstance(m,dict)} if isinstance(models,list) else set()
    match=next((m for m in models if isinstance(m,dict) and m.get('id')==MODEL),None) if isinstance(models,list) else None
    # Price detection is observational only. This endpoint is NOT a contractual
    # account-specific zero-spend lock, even when it reports a zero value.
    price_state='not_provided'
    if match is not None:
        pricing=match.get('pricing')
        rate=match.get('price_per_second')
        if isinstance(pricing,dict):
            rate=pricing.get('price_per_second',pricing.get('usd_per_second',rate))
        if isinstance(rate,(int,float,str)) and not isinstance(rate,bool):
            try:
                rate_float=float(rate)
                if rate_float==0:price_state='zero_metadata_unverified'
                elif rate_float>0:price_state='positive_rate_detected'
                else:price_state='unrecognized'
            except (TypeError,ValueError):
                price_state='unrecognized'
    return {'credential_state':'accepted' if isinstance(models,list) else 'unverified',
            'model_visible':MODEL in ids,
            'price_metadata_state':price_state,
            'pricing_verified':False,'generation_permitted':False}

def video_payload(prompt:str,seconds:int,reference_urls:list[str])->dict:
    if not 4<=seconds<=12:raise ValueError('Agnes Flash תומך ב־4 עד 12 שניות לכל סרטון')
    if not 0<=len(reference_urls)<=2:raise ValueError('בגרסה זו אפשר עד שתי תמונות ייחוס נפרדות')
    if not isinstance(prompt,str) or not 3<=len(prompt)<=4000:raise ValueError('תיאור הסרטון אינו תקין')
    intro=''
    if reference_urls:
        intro='Use <Picture 1> as character 1 visual identity reference. '
        if len(reference_urls)>1:
            intro+='Use <Picture 2> as distinct character 2. Preserve each face and original clothing separately, never blend, swap or invent principal subjects. '
    payload={'model':MODEL,'prompt':intro+prompt,'mode':'reference' if reference_urls else 'text',
             'seconds':str(seconds),'size':'720P','aspect_ratio':'16:9','n':1}
    if reference_urls:payload['images']=reference_urls
    return payload

def submit(prompt:str,seconds:int,urls:list[str],key:str)->str:
    data=api_json('POST','/v1/videos',key,video_payload(prompt,seconds,urls),timeout=70)
    video_id=data.get('video_id') or data.get('id')
    if not isinstance(video_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{4,128}',video_id):
        raise AgnesError('Agnes לא החזיר מזהה וידאו תקין')
    return video_id

def poll(video_id:str,key:str,deadline:float,on_progress=None)->str:
    if not re.fullmatch(r'[A-Za-z0-9_-]{4,128}',video_id):raise ValueError('מזהה וידאו לא תקין')
    path='/agnesapi?'+urlencode({'video_id':video_id,'model_name':MODEL})
    while time.monotonic()<deadline:
        data=api_json('GET',path,key,timeout=35)
        state=data.get('status')
        if state=='completed':
            metadata=data.get('metadata') if isinstance(data.get('metadata'),dict) else {}
            url=data.get('url') or metadata.get('url')
            if not isinstance(url,str) or not url:raise AgnesError('Agnes דיווח על הצלחה בלי קישור ל־MP4')
            return url
        if state=='failed':
            error=data.get('error')
            safe=(error.get('message') if isinstance(error,dict) else '') or ''
            raise AgnesError('Agnes לא הצליח להפיק סרטון'+(': '+str(safe)[:140] if safe else ''))
        if state not in ('queued','in_progress','pending','processing'):
            raise AgnesError('Agnes החזיר מצב עבודה לא מוכר')
        if on_progress:
            progress=data.get('progress',0)
            if isinstance(progress,(int,float)) and 0<=progress<=100:
                on_progress(f'מפיק סרטון דרך Agnes · {int(progress)}%')
        time.sleep(2.5)
    raise AgnesError('Agnes לא סיים את ההפקה בזמן. ייתכן שהשרת עמוס.')

def validate_download_url(value:str)->str:
    parts=urlsplit(value)
    if parts.scheme!='https' or not parts.hostname or parts.username or parts.password:
        raise AgnesError('כתובת תוצאת הווידאו חייבת להיות HTTPS מאובטח')
    if parts.port not in (None,443):raise AgnesError('פורט תוצאה לא מורשה')
    host=parts.hostname.lower()
    if host=='localhost' or host.endswith(('.local','.internal','.test')):
        raise AgnesError('קישור תוצאה לכתובת פנימית נחסם')
    try:
        ip=ipaddress.ip_address(host)
        if not ip.is_global:raise AgnesError('קישור תוצאה לכתובת פרטית נחסם')
    except ValueError:pass
    # Resolution guard. Disallow private/loopback names, not just private IP literals.
    try:
        addresses=socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(row[4][0]).is_global for row in addresses):
            raise AgnesError('קישור התוצאה מפנה לכתובת לא ציבורית')
    except socket.gaierror as e:
        raise AgnesError('קישור התוצאה אינו ניתן לאימות DNS') from e
    return value

def download_mp4(url:str)->bytes:
    url=validate_download_url(url)
    req=Request(url,headers={'User-Agent':'KolboVideo/AgnesFlashOnly'})
    try:
        with build_opener(RejectRedirects()).open(req,timeout=110) as resp:
            if resp.status!=200:raise AgnesError('לא הצלחנו להוריד את הסרטון')
            data=resp.read(MAX_RESULT_BYTES+1)
            if len(data)>MAX_RESULT_BYTES:raise AgnesError('הווידאו גדול מהמותר')
            if len(data)<10000 or data[4:8]!=b'ftyp':raise AgnesError('קובץ התוצאה אינו MP4 תקין')
            return data
    except (URLError,TimeoutError) as e:
        raise AgnesError('הורדת MP4 של Agnes לא הצליחה') from e
