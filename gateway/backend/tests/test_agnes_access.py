"""Read-only Agnes credential verification must never send POST /v1/videos."""
import pathlib,sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
import agnes_adapter as agnes
import server

def test_missing_key_is_not_recognized(monkeypatch):
    monkeypatch.setattr(server,'TOKEN','safe-test-gateway-token-more-than-24')
    monkeypatch.setattr(server,'RENDER_PROVIDER','agnes')
    monkeypatch.setattr(server,'AGNES_KEY','')
    r=TestClient(server.app).get('/v1/agnes/access',
        headers={'Authorization':'Bearer safe-test-gateway-token-more-than-24'})
    assert r.status_code==200 and r.json()['credential_state']=='missing'
    assert r.json()['generation_permitted'] is False

def test_probing_never_creates_video_or_asserts_zero_price(monkeypatch):
    calls=[]
    def fake_call(method,path,key,payload=None,timeout=35):
        calls.append((method,path))
        assert method=='GET' and path=='/v1/models'
        assert payload is None
        return {'object':'list','data':[{'id':'agnes-video-2.5-flash'},{'id':'agnes-video-2.5'}]}
    monkeypatch.setattr(agnes,'api_json',fake_call)
    monkeypatch.setattr(server,'TOKEN','safe-test-gateway-token-more-than-24')
    monkeypatch.setattr(server,'RENDER_PROVIDER','agnes')
    monkeypatch.setattr(server,'AGNES_KEY','test-agnes-key-safely-not-public')
    monkeypatch.setattr(server,'AGNES_PROMO_ACK',False)
    r=TestClient(server.app).get('/v1/agnes/access',
       headers={'Authorization':'Bearer safe-test-gateway-token-more-than-24'})
    assert r.status_code==200
    assert r.json()['credential_state']=='accepted'
    assert r.json()['model_visible'] is True
    assert r.json()['pricing_verified'] is False
    assert r.json()['generation_permitted'] is False
    assert r.json()['provider_account_price_verified'] is False
    assert calls==[('GET','/v1/models')]

def test_probe_rejects_unauthenticated_client():
    r=TestClient(server.app).get('/v1/agnes/access')
    assert r.status_code in (401,503)

def test_provider_auth_failure_reports_rejected_without_key_material(monkeypatch):
    monkeypatch.setattr(agnes,'api_json',lambda *a,**k: (_ for _ in ()).throw(
        agnes.AgnesError('מפתח Agnes אינו מורשה להפקה (401/403)')))
    r=agnes.inspect_access_without_generation('example-agnes-secret-no-output')
    assert r['credential_state']=='rejected'
    assert not r['generation_permitted']
    assert 'example-agnes' not in str(r)
