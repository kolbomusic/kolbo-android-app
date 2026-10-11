"""One-image, silent *real model* trial with strict, non-durable free quota.

This is not commercial production infrastructure, nor a guarantee of availability.
Guest permissions are independent of owner/master credentials and do not unlock
the private v1/jobs endpoint. No provider key or payments. No quota circumvention.
"""
from __future__ import annotations
import os
import threading
import time
import hashlib
import re

from fastapi import HTTPException

LOCK=threading.RLock()
COUNTERS:dict[tuple,int]={}
GLOBAL_PER_UTC_DAY=2
PER_INSTALL_PER_UTC_DAY=1
MAX_ENTRIES=3000
ID=re.compile(r"^[0-9a-f]{64}$")


def enabled()->bool:
    return (os.getenv("KOLBO_GUEST_AI_TRIAL")=="EXPLICITLY_ENABLED"
        and os.getenv("KOLBO_ALLOW_EXTERNAL_TEST_MEDIA")=="EXPLICITLY_ENABLED")


def reserve(owner:str,now:int|None=None)->None:
    if not enabled():
        raise HTTPException(503,"ניסוי יצירת AI אינו זמין כעת")
    if not isinstance(owner,str) or ID.fullmatch(owner) is None:
        raise HTTPException(401,"נדרשת הרשאת ניסיון מוגבלת")
    day=int(time.time() if now is None else now)//86400
    with LOCK:
        # Free shared quota is finite; never force retries or other accounts.
        if len(COUNTERS)>MAX_ENTRIES:
            for key in list(COUNTERS):
                if key[0]!=day:COUNTERS.pop(key,None)
            if len(COUNTERS)>MAX_ENTRIES:
                raise HTTPException(503,"מכסת יצירות הניסוי מלאה")
        total=COUNTERS.get((day,"all"),0)
        personal=COUNTERS.get((day,owner),0)
        if total>=GLOBAL_PER_UTC_DAY or personal>=PER_INSTALL_PER_UTC_DAY:
            raise HTTPException(429,"מכסת ניסוי הווידאו החינמי נוצלה להיום",
                                headers={"Retry-After":"3600"})
        COUNTERS[(day,"all")]=total+1
        COUNTERS[(day,owner)]=personal+1


def advertised()->dict:
    return {"mode":"ai_one_image_trial",
            "ready":enabled(),
            "generates_new_visual_frames":True,
            "source":"public_huggingface_zerogpu_demo",
            "supported_image_counts":[1],
            "min_seconds":1,"max_seconds":5,
            "supports_audio":False,"supports_singing":False,
            "supports_lipsync":False,
            "supports_two_people_from_separate_photos":False,
            "external_upload":True,"external_consent_required":True,
            "max_global_submissions_per_day":GLOBAL_PER_UTC_DAY,
            "max_per_install_per_day":PER_INSTALL_PER_UTC_DAY,
            "availability_guaranteed":False,
            "semantic_adherence_verified":False,
            "commercial_rights_verified":False,
            "retry_unknown_acceptance":False}
