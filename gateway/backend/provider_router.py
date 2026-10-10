"""Kolbo Video provider orchestration (conservative; never creates phantom capacity).

Routes only documented compatible inputs, and automatically falls back only when
the preceding submission was explicitly REJECTED without a provider task ID.
Separate contracts per provider: a provider with keyframes is NOT a guaranteed
two-person identity-reference service.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib, json, os, pathlib, tempfile, threading, time
from typing import Callable

@dataclass(frozen=True)
class Provider:
    name:str
    model:str
    max_independent_references:int
    promotional_zero_price:bool
    enabled:bool

FLASH=Provider('agnes_flash','agnes-video-2.5-flash',2,True,True)
V20=Provider('agnes_legacy','agnes-video-v2.0',1,True,False)

class NoCompatibleProvider(RuntimeError):
    pass

class ProviderQueueExhausted(RuntimeError):
    pass

class Breaker:
    def __init__(self,clock:Callable[[],float]|None=None):
        self.clock=clock or time.monotonic
        self.until:dict[str,float]={}
        self.lock=threading.RLock()
    def available(self,provider_name:str)->bool:
        with self.lock:return self.clock()>=self.until.get(provider_name,0)
    def rejected(self,provider_name:str,cooldown:int=90):
        with self.lock:self.until[provider_name]=self.clock()+cooldown
    def reset(self,provider_name:str):
        with self.lock:self.until.pop(provider_name,None)

BREAKER=Breaker()

def candidates(reference_count:int, *,flash_enabled=True,
               v20_enabled=False,v20_cost_approved=False,
               experimental_two_ref=False,breaker:Breaker|None=None)->list[Provider]:
    if reference_count not in (0,1,2):
        raise ValueError('at most two reference images')
    available=[]
    if flash_enabled:available.append(FLASH)
    # Agnes 2.0 has a different API and its multi-image *keyframes*
    # is NOT independent two-person identity conditioning. Do not
    # silently degrade a two-photo request.
    if v20_enabled and v20_cost_approved and (
            reference_count<=1 or experimental_two_ref):
        available.append(Provider('agnes_legacy','agnes-video-v2.0',
                    2 if experimental_two_ref else 1,True,True))
    check=breaker or BREAKER
    return [p for p in available if check.available(p.name)]

def select_and_submit(reference_count:int,submit:Callable[[Provider],str],
                      is_explicit_rejection:Callable[[Exception],bool],
                      *,flash_enabled=True,v20_enabled=False,
                      v20_cost_approved=False,experimental_two_ref=False,
                      breaker:Breaker|None=None)->tuple[Provider,str]:
    check=breaker or BREAKER
    providers=candidates(reference_count,flash_enabled=flash_enabled,
       v20_enabled=v20_enabled,v20_cost_approved=v20_cost_approved,
       experimental_two_ref=experimental_two_ref,breaker=check)
    if not providers:
        raise NoCompatibleProvider(
            'אין מנוע הפקה תואם ופנוי. לשתי תמונות נדרש מנוע עם תמיכה נפרדת בשתי זהויות.')
    failed=[]
    for provider in providers:
        try:
            accepted=submit(provider)
        except Exception as exc:
            # Only definite rejection before task creation is safe to retry
            # with a second provider. Never retry timeouts, 5xx ambiguous
            # responses, or error after acceptance.
            if not is_explicit_rejection(exc):raise
            check.rejected(provider.name)
            failed.append(provider.name)
            continue
        if not isinstance(accepted,str) or not accepted:
            raise ValueError('Provider returned an invalid task identifier')
        check.reset(provider.name)
        return provider,accepted
    raise ProviderQueueExhausted(
        'כל מנועי ההפקה התואמים דחו את הבקשה בגלל עומס או מגבלת קצב. לא נוצר סרטון.')

def snapshot(work_dir:pathlib.Path,job_id:str,mode:str,reference_count:int,
             seconds:int,provider:str|None,status:str,attempt:int=0):
    """Private, non-sensitive local checkpoint. NOT durable on Render Free redeploy.
    No prompt, user media, photo names, source URLs, tokens or device identifiers.
    """
    folder=work_dir/'job_state'
    folder.mkdir(mode=0o700,parents=True,exist_ok=True)
    if not all(c in '0123456789abcdef-' for c in job_id.lower()) or len(job_id)>50:
        raise ValueError('Invalid job ID')
    destination=folder/(job_id+'.json')
    record={'schema':1,'id':job_id,'mode':mode,
        'reference_count':reference_count,'seconds':seconds,
        'provider':provider,'status':status,'attempt':attempt,'at':int(time.time()),
        'persistent_storage':False}
    fd,tmp=tempfile.mkstemp(prefix='.checkpoint-',dir=folder)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as file:
            os.fchmod(file.fileno(),0o600)
            json.dump(record,file,ensure_ascii=False)
            file.flush();os.fsync(file.fileno())
        os.replace(tmp,destination)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)
    return destination
