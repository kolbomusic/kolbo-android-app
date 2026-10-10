"""Google AdMob rewarded-view verification for future Kolbo Video credits.

STAGED ONLY: This module has no live ad inventory, payout, or provider billing
integration. No credits may be granted until the real Google AdMob ECDSA SSV
callback is verified and an atomic durable store records its transaction ID.

A rewarded-ad completion is NOT a dollar payment to a video provider.
"""
from __future__ import annotations
import base64
from dataclasses import dataclass
import re,time
from urllib.parse import parse_qsl
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import ec

# Per Google's AdMob SSV specification the final two parameters are always
# signature and key_id. The message consists of ALL preceding query bytes in
# exactly the received order and encoding; never reserialize or reorder.
_SIGNED_END=re.compile(r'^(?P<message>.+)&signature=(?P<signature>[A-Za-z0-9_-]+)&key_id=(?P<key_id>[0-9]{1,20})$')
_TX=re.compile(r'^[0-9a-fA-F]{20,128}$')
_NONCE=re.compile(r'^[A-Za-z0-9_-]{24,120}$')
_USER=re.compile(r'^[a-f0-9]{64}$')

class UnverifiedReward(ValueError):
    pass

@dataclass(frozen=True)
class RewardEvidence:
    transaction_id:str
    intent_nonce:str
    owner_fingerprint:str
    ad_unit:str
    received_ms:int
    points:int

def verify_admob_reward(raw_query:str,public_key_pem_by_id:dict[int,str],
                         *,expected_ad_unit:str,expected_reward_item:str,
                         expected_reward_amount:int,
                         now_ms:int|None=None)->RewardEvidence:
    """Verify only Google's signed SSV event.  The caller must additionally
    validate a pending owner-bound intent and commit with a UNIQUE tx ID in a
    durable ACID store before granting any credits.
    """
    if not isinstance(raw_query,str) or not 30<=len(raw_query)<=6000:
        raise UnverifiedReward('Bad callback length')
    match=_SIGNED_END.fullmatch(raw_query)
    if not match:raise UnverifiedReward('Missing ordered signature fields')
    signed=match.group('message')
    try:
        fields=parse_qsl(signed,keep_blank_values=True,strict_parsing=True,
                         max_num_fields=25)
    except (ValueError,TypeError) as exc:
        raise UnverifiedReward('Invalid callback format') from exc
    data={}
    for name,value in fields:
        if name in data:raise UnverifiedReward('Duplicate field')
        data[name]=value
    if data.get('ad_unit')!=expected_ad_unit:
        raise UnverifiedReward('Unknown ad unit')
    if data.get('reward_item')!=expected_reward_item:
        raise UnverifiedReward('Reward item mismatch')
    try:
        if int(data.get('reward_amount','-1'))!=expected_reward_amount:
            raise UnverifiedReward('Reward amount mismatch')
        when=int(data['timestamp'])
        key_id=int(match.group('key_id'))
    except (KeyError,TypeError,ValueError) as exc:
        raise UnverifiedReward('Malformed numeric fields') from exc
    now=int(time.time()*1000) if now_ms is None else now_ms
    if when>now+300000 or when<now-48*3600*1000:
        raise UnverifiedReward('Old or future callback')
    transaction=data.get('transaction_id','')
    if not _TX.fullmatch(transaction):
        raise UnverifiedReward('Bad transaction ID')
    # The Android app generates a random nonce via the server prior to ad
    # display. Its association with the authorized device is stored ONLY
    # on the server (no phone-provided balance or transaction IDs).
    nonce=data.get('custom_data','')
    if not _NONCE.fullmatch(nonce):
        raise UnverifiedReward('Missing owner-bound ad intent')
    owner=data.get('user_id','')
    if not _USER.fullmatch(owner):
        raise UnverifiedReward('Missing approved owner fingerprint')
    pem=public_key_pem_by_id.get(key_id)
    if not pem:raise UnverifiedReward('No trusted Google verification key')
    try:
        key=serialization.load_pem_public_key(pem.encode('ascii'))
        if not isinstance(key,ec.EllipticCurvePublicKey):
            raise UnverifiedReward('Invalid Google key type')
        signature=match.group('signature')
        signature_bytes=base64.urlsafe_b64decode(
            signature+'='*((-len(signature))%4))
        key.verify(signature_bytes,signed.encode('utf-8'),
                   ec.ECDSA(hashes.SHA256()))
    except (InvalidSignature,ValueError,TypeError) as exc:
        raise UnverifiedReward('Invalid signature') from exc
    return RewardEvidence(transaction,nonce,owner,
        expected_ad_unit,when,expected_reward_amount)

def funding_estimate_impressions(cost_usd:float,ecpm_usd:float)->int:
    """Illustrative planning ONLY: AdMob earnings are not guaranteed."""
    import math
    if cost_usd<0 or not 0<ecpm_usd<1e6:
        raise ValueError('Cost and eCPM must be nonnegative/positive')
    return math.ceil(cost_usd*1000/ecpm_usd)

def reward_schema_sql()->str:
    """Intentionally not executed on Render Free's ephemeral local filesystem.

    Use a separate durable PostgreSQL database with backups. AdMob SSV
    grants must be committed atomically before any redeemed credits.
    """
    return '''
    CREATE TABLE IF NOT EXISTS kolbo_ad_intents (
        nonce text PRIMARY KEY,
        owner_fingerprint text NOT NULL,
        created_ms bigint NOT NULL,
        state text NOT NULL CHECK(state IN ('pending','credited','expired'))
    );
    CREATE TABLE IF NOT EXISTS kolbo_ad_credits (
        transaction_id text PRIMARY KEY,
        nonce text UNIQUE NOT NULL REFERENCES kolbo_ad_intents(nonce),
        owner_fingerprint text NOT NULL,
        points integer NOT NULL CHECK(points>0),
        verified_at_ms bigint NOT NULL
    );
    CREATE INDEX IF NOT EXISTS kolbo_ad_credits_owner_idx
        ON kolbo_ad_credits(owner_fingerprint);
    '''
