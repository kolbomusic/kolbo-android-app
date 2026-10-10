"""Render readiness checks: these do NOT run a real model."""
import pathlib, sys
from fastapi.testclient import TestClient
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import server

def test_public_render_health_is_safe_and_not_claiming_generation():
    result=TestClient(server.app).get('/healthz')
    assert result.status_code==200
    assert result.json()=={'service':'kolbo-video-gateway','alive':True,'render_ready':False}
    assert 'AGNES_API_KEY' not in result.text

def test_no_provider_key_is_fail_closed(monkeypatch):
    monkeypatch.setattr(server,'TOKEN','a-valid-but-not-real-token-0123456789')
    monkeypatch.setattr(server,'RENDER_PROVIDER','agnes')
    monkeypatch.setattr(server,'AGNES_KEY','')
    monkeypatch.setattr(server,'AGNES_PROMO_ACK',False)
    client=TestClient(server.app)
    auth={'Authorization':'Bearer a-valid-but-not-real-token-0123456789'}
    r=client.get('/v1/health',headers=auth)
    assert r.status_code==200
    assert r.json()['status']=='not_ready'
    assert r.json()['price_promotion_verified_live'] is False
    r=client.post('/v1/jobs',headers=auth,json={'prompt':'Two singers on a concert stage','seconds':10})
    assert r.status_code==503
