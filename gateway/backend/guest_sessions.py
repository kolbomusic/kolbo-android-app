"""No-setup guest sessions scoped EXCLUSIVELY to low-cost CPU photo edits.

A public bootstrap without login CANNOT verify the true app owner. This is
a deliberately bounded guest/demo capability, not an authorization scheme for
private accounts, paid GPU, uploads to AI vendors or production-scale service.

All counters are in-process on Render Free and reset on restart. Server global
capacity and Render free quotas must additionally constrain actual deployment.
"""
from __future__ import annotations
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time
from dataclasses import dataclass

from fastapi import HTTPException

INSTALL_ID = re.compile(r"^[0-9a-f]{32}$")
TTL_SECONDS = 3600
MAX_SESSION_ISSUES_DAILY = 100
MAX_SESSIONS_PER_INSTALL_DAILY = 5
MAX_CPU_SECONDS_GLOBAL_DAILY = 60
MAX_CPU_SECONDS_PER_INSTALL_DAILY = 24
LOCK = threading.RLock()
COUNTERS: dict[tuple, int] = {}
MAX_ROWS = 3000


@dataclass(frozen=True)
class Guest:
    owner: str
    expires_at: int


def enabled() -> bool:
    return (os.getenv("KOLBO_GUEST_CPU_BOOTSTRAP") == "EXPLICITLY_ENABLED"
            and len(os.getenv("KOLBO_GUEST_CPU_SESSION_SECRET", "")) >= 48)


def _secret() -> bytes:
    secret = os.getenv("KOLBO_GUEST_CPU_SESSION_SECRET","")
    if not enabled() or len(secret) < 48:
        raise HTTPException(503, "חיבור אורח אוטומטי אינו זמין בשרת")
    return secret.encode("utf-8")


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64(data: str) -> bytes:
    return base64.urlsafe_b64decode(data+"="*((-len(data))%4))


def _period(now: int) -> int:
    return now//86400


def _reduce(now: int) -> None:
    if len(COUNTERS)>MAX_ROWS:
        day=_period(now)
        for key in list(COUNTERS):
            if key[0] < day:
                COUNTERS.pop(key,None)
        if len(COUNTERS)>MAX_ROWS:
            raise HTTPException(503,"מכסת רישומים מלאה; נסה שוב מאוחר יותר")


def issue(install_id:str, now:int|None=None) -> dict:
    secret=_secret()
    if not isinstance(install_id,str) or not INSTALL_ID.fullmatch(install_id):
        raise HTTPException(422,"זהות התקנה אינה תקינה")
    moment=int(time.time() if now is None else now)
    today=_period(moment)
    owner=hashlib.sha256(install_id.encode("ascii")).hexdigest()
    with LOCK:
        _reduce(moment)
        if (COUNTERS.get((today,"sessions_all"),0)>=MAX_SESSION_ISSUES_DAILY
            or COUNTERS.get((today,"sessions",owner),0)>=MAX_SESSIONS_PER_INSTALL_DAILY):
            raise HTTPException(429,"מכסת חיבורים חינמית נוצלה זמנית")
        COUNTERS[(today,"sessions_all")]=COUNTERS.get((today,"sessions_all"),0)+1
        COUNTERS[(today,"sessions",owner)]=COUNTERS.get((today,"sessions",owner),0)+1
    claims={"v":1,"scope":"cpu_photo_motion_only",
            "owner":owner,"exp":moment+TTL_SECONDS,"iat":moment,
            "jti":secrets.token_hex(12)}
    payload=_b64(json.dumps(claims,sort_keys=True,separators=(",",":")).encode())
    msg="g1."+payload
    sig=_b64(hmac.digest(secret,msg.encode("ascii"),"sha256"))
    return {"token":msg+"."+sig,"expires_in_seconds":TTL_SECONDS,
            "mode":"cpu_photo_motion","ai_generation":False,
            "rights":"temporary_guest_cpu_only","free_unlimited":False}


def verify(authorization:str|None,now:int|None=None)->Guest:
    secret=_secret()
    if not isinstance(authorization,str) or not authorization.startswith("Bearer g1."):
        raise HTTPException(401,"נדרש אישור עריכה זמני")
    token=authorization[len("Bearer "):]
    parts=token.split(".")
    if len(parts)!=3 or parts[0]!="g1" or len(token)>1200:
        raise HTTPException(401,"אישור העריכה אינו תקין")
    signed=parts[0]+"."+parts[1]
    try:
        given=_unb64(parts[2])
        expected=hmac.digest(secret,signed.encode("ascii"),"sha256")
        if not hmac.compare_digest(given,expected):
            raise ValueError("Bad MAC")
        claims=json.loads(_unb64(parts[1]))
        now_int=int(time.time() if now is None else now)
        if (claims.get("v")!=1 or claims.get("scope")!="cpu_photo_motion_only"
            or not isinstance(claims.get("owner"),str)
            or not re.fullmatch("[0-9a-f]{64}",claims["owner"])
            or type(claims.get("iat"))!=int or type(claims.get("exp"))!=int
            or claims["exp"]<=now_int or claims["iat"]>now_int+60
            or claims["exp"]-claims["iat"]>TTL_SECONDS):
            raise ValueError("Bad claims")
        return Guest(claims["owner"],claims["exp"])
    except (UnicodeError,ValueError,KeyError,TypeError,OverflowError) as exc:
        raise HTTPException(401,"אישור העריכה פג או אינו תקין") from exc


def reserve_seconds(owner:str,seconds:int,now:int|None=None)->None:
    if not enabled():
        raise HTTPException(503,"עריכת אורח אינה פעילה")
    if not re.fullmatch(r"[0-9a-f]{64}",owner) or type(seconds)!=int \
        or not 2<=seconds<=12:
        raise HTTPException(422,"בקשת עריכה אינה תקינה")
    moment=int(time.time() if now is None else now)
    day=_period(moment)
    with LOCK:
        _reduce(moment)
        global_so_far=COUNTERS.get((day,"seconds_all"),0)
        own_so_far=COUNTERS.get((day,"seconds",owner),0)
        if global_so_far+seconds>MAX_CPU_SECONDS_GLOBAL_DAILY:
            raise HTTPException(429,"מכסת עריכת הווידאו החינמית היומית של השרת נוצלה")
        if own_so_far+seconds>MAX_CPU_SECONDS_PER_INSTALL_DAILY:
            raise HTTPException(429,"מכסת העריכה החינמית היומית נוצלה בהתקנה זו")
        COUNTERS[(day,"seconds_all")]=global_so_far+seconds
        COUNTERS[(day,"seconds",owner)]=own_so_far+seconds


def capabilities()->dict:
    return {"guest_bootstrap_enabled":enabled(),
            "cpu_photo_studio":True,
            "ai_video_generation":False,
            "no_input_or_master_key_required":True,
            "auth_strength":"anonymous_rate_limited_guest_not_verified_owner",
            "daily_global_render_seconds":MAX_CPU_SECONDS_GLOBAL_DAILY,
            "daily_per_install_seconds":MAX_CPU_SECONDS_PER_INSTALL_DAILY,
            "durable_quota":False,
            "provider_payment_or_gpu":False}
