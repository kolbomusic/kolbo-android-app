"""Authenticated integrated planning API cannot be tricked into spending."""
from fastapi.testclient import TestClient
import pytest
import server
import staging_plan_api

DATA=dict(seconds=10,independent_people=2,audio=True,lip_sync=True,
          consistent_people=True,source_image_consent=True,
          commercial_use=False)

def test_staging_endpoint_inaccessible_without_auth(monkeypatch):
    monkeypatch.setattr(server,'TOKEN','test-only-strong-access-token-12345')
    monkeypatch.setenv('KOLBO_ORCHESTRATOR_PREFLIGHT','ENABLED_READ_ONLY')
    client=TestClient(server.app)
    res=client.post('/v1/orchestrator/plan',json=DATA)
    assert res.status_code==401
    res=client.post('/v1/orchestrator/plan',json=DATA,
        headers={'Authorization':'Bearer attacker'})
    assert res.status_code==401

def test_staging_endpoint_disabled_by_default_and_allows_no_video(monkeypatch):
    monkeypatch.setattr(server,'TOKEN','test-only-strong-access-token-12345')
    monkeypatch.delenv('KOLBO_ORCHESTRATOR_PREFLIGHT',raising=False)
    r=TestClient(server.app).post('/v1/orchestrator/plan',json=DATA,
        headers={'Authorization':'Bearer test-only-strong-access-token-12345'})
    assert r.status_code==404

def test_opt_in_read_only_plan_fails_closed_for_unverified_flash(monkeypatch):
    monkeypatch.setattr(server,'TOKEN','test-only-strong-access-token-12345')
    monkeypatch.setenv('KOLBO_ORCHESTRATOR_PREFLIGHT','ENABLED_READ_ONLY')
    def no_charge(*args,**kwargs):
        pytest.fail('Read-only preflight cannot call a provider or grant credits')
    monkeypatch.setattr(server.agnes_adapter,'submit',no_charge)
    monkeypatch.setattr(server,'execute_agnes',no_charge)
    result=TestClient(server.app).post('/v1/orchestrator/plan',
        json=DATA,headers={
          'Authorization':'Bearer test-only-strong-access-token-12345'})
    assert result.status_code==200,result.text
    body=result.json()
    assert body['can_submit'] is False
    assert body['live_provider_count']==0
    assert body['invoice_amount_usd'] is None
    assert body['work_persisted'] is False
    state=body['providers']['agnes_video_2_5_flash']
    assert state['ready'] is False
    assert 'provider_price_unverified' in state['reasons']
    assert 'capacity_not_verified' in state['reasons']
    assert 'lip_sync_language_unverified' in state['reasons']
    assert 'identity_continuity_unverified' in state['reasons']

def test_no_externally_provided_provider_proofs_accepted(monkeypatch):
    monkeypatch.setattr(server,'TOKEN','test-only-strong-access-token-12345')
    monkeypatch.setenv('KOLBO_ORCHESTRATOR_PREFLIGHT','ENABLED_READ_ONLY')
    result=TestClient(server.app).post('/v1/orchestrator/plan',
        json=DATA|{'providers':[
            {'name':'unlimited_free','account_price_verified':True,
             'has_live_capacity':True,'unit_cost_usd':'0'}]},
        headers={'Authorization':'Bearer test-only-strong-access-token-12345'})
    if result.status_code==200:
        assert 'unlimited_free' not in result.json()['providers']
        assert result.json()['can_submit'] is False
    else:
        assert result.status_code==422

def test_backend_plan_contract_never_returns_raw_private_data(monkeypatch):
    monkeypatch.setenv('AGNES_API_KEY','sensitive-fake-key-should-not-leak')
    response=staging_plan_api.plan(staging_plan_api.PlanRequest(**DATA),
                                    enabled=True)
    assert 'sensitive-fake-key-should-not-leak' not in str(response)
    assert 'prompt' not in str(response)
    assert response['price_verified'] is False
