"""Code-free Android device enrollment, WITHOUT bundling any reusable secret in APK.

Enrollment is not approval. Render operator allowlists the fingerprint using
KOLBO_DEVICE_ALLOWLIST only after confirming the device belongs to the owner.
Never auto-approve untrusted public registrations.
"""
from __future__ import annotations
import base64, hashlib, logging, os, re, secrets, threading, time
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

router=APIRouter()
lock=threading.RLock()
seen_pending:set[str]=set()
sessions:dict[str,tuple[float,str]]={}
used_nonces:dict[str,float]={}
SESSION_TTL=3600
CLOCK_SKEW=120

def fingerprint_and_key(encoded:str):
    try:
        der=base64.b64decode(encoded,validate=True)
        if not 60<=len(der)<=300:raise ValueError('invalid public key length')
        public=serialization.load_der_public_key(der)
        if not isinstance(public,ec.EllipticCurvePublicKey) or not isinstance(public.curve,ec.SECP256R1):
            raise ValueError('expected P-256 public key')
        canonical=public.public_bytes(serialization.Encoding.DER,
                                      serialization.PublicFormat.SubjectPublicKeyInfo)
        return hashlib.sha256(canonical).hexdigest(),public
    except (ValueError,TypeError) as error:
        raise HTTPException(422,'Invalid device public key') from error

def approved(fingerprint:str):
    allow={x.strip().lower() for x in os.getenv('KOLBO_DEVICE_ALLOWLIST','').split(',') if x.strip()}
    return fingerprint.lower() in allow

class RegisterInput(BaseModel):
    public_key_b64:str=Field(min_length=60,max_length=450)

class SessionInput(RegisterInput):
    timestamp:int
    nonce:str=Field(min_length=20,max_length=100)
    signature_b64:str=Field(min_length=32,max_length=200)

@router.post('/v1/device/register')
def register(record:RegisterInput):
    digest,_=fingerprint_and_key(record.public_key_b64)
    is_approved=approved(digest)
    with lock:
        if not is_approved and digest not in seen_pending:
            seen_pending.add(digest)
            logging.info('KOLBO_DEVICE_PENDING fingerprint_sha256=%s',digest)
    return {'status':'approved' if is_approved else 'pending',
            'fingerprint':digest,'code_entry_required':False,
            'approval':'server_operator_only'}

@router.post('/v1/device/session')
def session(record:SessionInput):
    digest,key=fingerprint_and_key(record.public_key_b64)
    if not approved(digest):
        raise HTTPException(403,'מכשיר ממתין לאישור בשרת; לא נדרש קוד')
    now=int(time.time())
    if abs(now-record.timestamp)>CLOCK_SKEW:
        raise HTTPException(401,'Device clock or request expired')
    if not re.fullmatch(r'[A-Za-z0-9_-]{20,100}',record.nonce):
        raise HTTPException(422,'Invalid nonce')
    message=('KOLBO-DEVICE-V1\n'+str(record.timestamp)+'\n'+record.nonce).encode('ascii')
    try:
        signature=base64.b64decode(record.signature_b64,validate=True)
        key.verify(signature,message,ec.ECDSA(hashes.SHA256()))
    except Exception as error:
        raise HTTPException(401,'Device signature invalid') from error
    with lock:
        stale=[n for n,t in used_nonces.items() if t<time.monotonic()]
        for nonce in stale:used_nonces.pop(nonce,None)
        replay=digest+'|'+record.nonce
        if replay in used_nonces:raise HTTPException(409,'Duplicate signed request')
        used_nonces[replay]=time.monotonic()+CLOCK_SKEW
        token=secrets.token_urlsafe(40)
        sessions[token]=(time.monotonic()+SESSION_TTL,digest)
    return {'access_token':token,'token_type':'Bearer','expires_in':SESSION_TTL}

def is_authorized_session(token:str):
    if len(token)<30 or len(token)>160:return False
    with lock:
        info=sessions.get(token)
        if not info:return False
        if time.monotonic()>=info[0] or not approved(info[1]):
            sessions.pop(token,None)
            return False
    return True
