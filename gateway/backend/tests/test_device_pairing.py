"""One-time operator approval: no APK secret, code entry, or automatic anonymous access."""
import base64,os,time,secrets,pytest
from fastapi.testclient import TestClient
from cryptography.hazmat.primitives import serialization,hashes
from cryptography.hazmat.primitives.asymmetric import ec
import server
import device_pairing as pairing

@pytest.fixture
def device(monkeypatch):
    client=TestClient(server.app)
    secret=ec.generate_private_key(ec.SECP256R1())
    pub=secret.public_key().public_bytes(
        serialization.Encoding.DER,serialization.PublicFormat.SubjectPublicKeyInfo)
    encoded=base64.b64encode(pub).decode()
    digest,_=pairing.fingerprint_and_key(encoded)
    pairing.sessions.clear()
    pairing.used_nonces.clear()
    pairing.seen_pending.clear()
    monkeypatch.setenv('KOLBO_DEVICE_ALLOWLIST','')
    return client,secret,encoded,digest

def payload(secret,encoded,nonce=None):
    moment=int(time.time())
    nonce=nonce or secrets.token_urlsafe(24)
    msg=f'KOLBO-DEVICE-V1\n{moment}\n{nonce}'.encode('ascii')
    sign=secret.sign(msg,ec.ECDSA(hashes.SHA256()))
    return {'public_key_b64':encoded,'timestamp':moment,'nonce':nonce,
            'signature_b64':base64.b64encode(sign).decode()}

def test_fresh_install_can_register_without_any_code_but_cannot_render(device):
    client,secret,pub,digest=device
    response=client.post('/v1/device/register',json={'public_key_b64':pub})
    assert response.status_code==200
    assert response.json()['status']=='pending'
    assert response.json()['fingerprint']==digest
    assert response.json()['code_entry_required'] is False
    assert client.post('/v1/device/session',json=payload(secret,pub)).status_code==403
    assert client.get('/v1/health').status_code==401

def test_operator_allowlist_then_short_lived_device_session(device,monkeypatch):
    client,secret,pub,digest=device
    monkeypatch.setenv('KOLBO_DEVICE_ALLOWLIST',digest)
    assert client.post('/v1/device/register',json={'public_key_b64':pub}).json()['status']=='approved'
    signed=payload(secret,pub)
    res=client.post('/v1/device/session',json=signed)
    assert res.status_code==200,res.text
    token=res.json()['access_token']
    assert len(token)>40
    assert client.get('/v1/health',headers={'Authorization':'Bearer '+token}).status_code==200
    assert client.post('/v1/device/session',json=signed).status_code==409
    monkeypatch.setenv('KOLBO_DEVICE_ALLOWLIST','')
    assert client.get('/v1/health',headers={'Authorization':'Bearer '+token}).status_code==401

def test_wrong_key_cannot_forge_an_approved_session(device,monkeypatch):
    client,secret,pub,digest=device
    monkeypatch.setenv('KOLBO_DEVICE_ALLOWLIST',digest)
    impostor=ec.generate_private_key(ec.SECP256R1())
    forged=payload(impostor,pub)
    assert client.post('/v1/device/session',json=forged).status_code==401

def test_reject_old_signature_and_invalid_public_keys(device,monkeypatch):
    client,secret,pub,digest=device
    monkeypatch.setenv('KOLBO_DEVICE_ALLOWLIST',digest)
    old=payload(secret,pub)
    old['timestamp']=int(time.time())-2000
    assert client.post('/v1/device/session',json=old).status_code==401
    assert client.post('/v1/device/register',json={'public_key_b64':'A'*100}).status_code==422

def test_sessions_expire_and_never_auto_approve(device,monkeypatch):
    client,secret,pub,digest=device
    monkeypatch.setenv('KOLBO_DEVICE_ALLOWLIST',digest)
    response=client.post('/v1/device/session',json=payload(secret,pub))
    assert response.status_code==200
    token=response.json()['access_token']
    pairing.sessions[token]=(time.monotonic()-1,digest)
    assert client.get('/v1/health',headers={'Authorization':'Bearer '+token}).status_code==401
