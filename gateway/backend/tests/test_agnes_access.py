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

def test_25_flash_metadata_url_when_task_completes(monkeypatch):
    import time
    seen=[]
    def fake_api(method,path,key,payload=None,timeout=35):
        seen.append((method,path))
        return {'status':'completed','metadata':{'url':'https://cdn.example.com/agnes-flash.mp4'}}
    monkeypatch.setattr(agnes,'api_json',fake_api)
    link=agnes.poll('video_reference_12345','example-key',time.monotonic()+10)
    assert link=='https://cdn.example.com/agnes-flash.mp4'
    assert len(seen)==1 and seen[0][0]=='GET'
    assert 'model_name=agnes-video-2.5-flash' in seen[0][1]

def test_optional_model_price_metadata_never_unlocks_spending(monkeypatch):
    for rate,expected in [(0,'zero_metadata_unverified'),
                          ('0','zero_metadata_unverified'),
                          ('0.025','positive_rate_detected')]:
        monkeypatch.setattr(agnes,'api_json',lambda *a,**k: {
          'data':[{'id':agnes.MODEL,'pricing':{'usd_per_second':rate}}]})
        state=agnes.inspect_access_without_generation('safe-example-long-key-123456')
        assert state['price_metadata_state']==expected
        assert state['pricing_verified'] is False
        assert state['generation_permitted'] is False

def test_no_price_data_reports_unknown(monkeypatch):
    monkeypatch.setattr(agnes,'api_json',lambda *a,**k: {
      'data':[{'id':agnes.MODEL}]})
    state=agnes.inspect_access_without_generation('safe-example-long-key-123456')
    assert state['price_metadata_state']=='not_provided'
    assert state['generation_permitted'] is False

def test_explicit_owner_trial_does_not_claim_account_price_verified(monkeypatch):
    monkeypatch.setattr(server,'TOKEN','long-test-gateway-token-over-24-characters')
    monkeypatch.setattr(server,'RENDER_PROVIDER','agnes')
    monkeypatch.setattr(server,'AGNES_KEY','example-accepted-test-api-key')
    monkeypatch.setattr(server,'AGNES_PROMO_ACK',True)
    monkeypatch.setattr(server,'AGNES_ACTIVATION_MODE','USER_APPROVED_FLASH_TRIAL')
    monkeypatch.setattr(server,'PUBLIC_BASE','https://gateway.example.org')
    ready=TestClient(server.app).get('/v1/health',headers={
        'Authorization':'Bearer long-test-gateway-token-over-24-characters'})
    assert ready.status_code==200
    info=ready.json()
    assert info['owner_authorized_flash_trial'] is True
    assert info['operator_price_confirmation'] is False
    assert info['price_promotion_verified_live'] is False
    assert info['possible_billing_if_promotion_changes'] is True
    assert info['provider']=='agnes-video-2.5-flash'

def test_explicit_agnes_queue_full_rejected_without_video_id(monkeypatch):
    import pytest
    for response in (
        {'code':'video_queue_full','message':'busy'},
        {'error':{'code':'queue_full','message':'later'}},
        {'status':'video_queue_full'},
    ):
        monkeypatch.setattr(agnes,'api_json',lambda *a,**k:response)
        with pytest.raises(agnes.AgnesQueueFull):
            agnes.submit('Two singers on a stage',8,[],'mock-access-key')

def test_queue_busy_retries_only_without_accepted_job(monkeypatch,tmp_path):
    import time
    import server
    from fastapi.testclient import TestClient
    monkeypatch.setattr(server,'TOKEN','mock-kolbo-owner-token-abcdef-12345')
    monkeypatch.setattr(server,'RENDER_PROVIDER','agnes')
    monkeypatch.setattr(server,'AGNES_KEY','mock-agnes-key-12345')
    monkeypatch.setattr(server,'AGNES_PROMO_ACK',True)
    monkeypatch.setattr(server,'PUBLIC_BASE','https://gateway.example.com')
    monkeypatch.setattr(server,'WORK_DIR',tmp_path)
    delays=[]
    monkeypatch.setattr(server.time,'sleep',lambda n:delays.append(n))
    calls=[]
    def submit(*args):
        calls.append(1)
        if len(calls)<3:raise agnes.AgnesQueueFull('queue full')
        return 'confirmed_video_abc123'
    monkeypatch.setattr(agnes,'submit',submit)
    monkeypatch.setattr(agnes,'poll',lambda *a:'https://cdn.example.org/example.mp4')
    monkeypatch.setattr(agnes,'download_mp4',
                        lambda *a:(_ for _ in ()).throw(agnes.AgnesError('test download stop')))
    client=TestClient(server.app)
    response=client.post('/v1/jobs',
        headers={'Authorization':'Bearer mock-kolbo-owner-token-abcdef-12345'},
        json={'prompt':'Two people dancing','seconds':8})
    assert response.status_code==202,response.text
    jobid=response.json()['job_id']
    for _ in range(150):
        job=client.get('/v1/jobs/'+jobid,
            headers={'Authorization':'Bearer mock-kolbo-owner-token-abcdef-12345'}).json()
        if job['state']=='failed':break
        time.sleep(0.01)
    assert len(calls)==3
    assert delays[:2]==[20,40]
    assert job['state']=='failed'
    assert 'download stop' in job['error']
    # No other model, no automatic retry after Agnes accepted a valid ID.

def test_persistent_queue_full_stops_after_bounded_attempts(monkeypatch,tmp_path):
    import time
    import server
    from fastapi.testclient import TestClient
    monkeypatch.setattr(server,'TOKEN','mock-kolbo-owner-token-abcdef-12345')
    monkeypatch.setattr(server,'RENDER_PROVIDER','agnes')
    monkeypatch.setattr(server,'AGNES_KEY','mock-agnes-key-12345')
    monkeypatch.setattr(server,'AGNES_PROMO_ACK',True)
    monkeypatch.setattr(server,'PUBLIC_BASE','https://gateway.example.com')
    monkeypatch.setattr(server,'WORK_DIR',tmp_path)
    delays=[]
    monkeypatch.setattr(server.time,'sleep',lambda n:delays.append(n))
    calls=[]
    def submit(*args):
        calls.append(1)
        raise agnes.AgnesQueueFull('queue full')
    monkeypatch.setattr(agnes,'submit',submit)
    client=TestClient(server.app)
    response=client.post('/v1/jobs',
        headers={'Authorization':'Bearer mock-kolbo-owner-token-abcdef-12345'},
        json={'prompt':'Two people dancing','seconds':8})
    assert response.status_code==202
    jobid=response.json()['job_id']
    for _ in range(150):
        job=client.get('/v1/jobs/'+jobid,
            headers={'Authorization':'Bearer mock-kolbo-owner-token-abcdef-12345'}).json()
        if job['state']=='failed':break
        time.sleep(0.01)
    assert len(calls)==5
    assert delays[:4]==[20,40,80,120]
    assert job['state']=='failed' and 'חמישה ניסיונות' in job['error']

def test_soft_queue_rejection_detected_in_nested_response_fields(monkeypatch):
    import pytest
    samples=[
        {'error':{'code':'video_queue_full','message':'Video queue is full'}},
        {'error':'video_queue_full'},
        {'message':'video_queue_full'},
        {'detail':'queue full'},
        {'code':'rate_limit'},
    ]
    for response in samples:
        monkeypatch.setattr(agnes,'api_json',lambda *a,**k:response)
        with pytest.raises(agnes.AgnesQueueFull):
            agnes.submit('Two singers performing in Caesarea',8,[],
                         'test-credential-not-real')

def test_task_id_is_not_retried_even_when_status_looks_busy(monkeypatch):
    response={'video_id':'task_accepted123','message':'queue_full','status':'queued'}
    monkeypatch.setattr(agnes,'api_json',lambda *a,**k:response)
    assert agnes.submit('Two performers dancing',8,[],
                        'test-credential-not-real')=='task_accepted123'

def test_bad_request_maps_only_whitelisted_error_category(monkeypatch):
    import pytest
    from urllib.error import HTTPError
    from io import BytesIO
    details=b'{"code":"video_queue_full","message":"queue is full"}'
    def fake_open(*a,**k):
        raise HTTPError('https://apihub.agnes-ai.com/v1/videos',400,
                        'Bad Request',{},BytesIO(details))
    monkeypatch.setattr(agnes,'build_opener',lambda *a: type(
        'FakeOpener',(),{'open':staticmethod(fake_open)})())
    with pytest.raises(agnes.AgnesQueueFull):
        agnes.api_json('POST','/v1/videos','test-credential-not-real',
                       {'model':agnes.MODEL,'mode':'text','prompt':'test'})

def test_agnes_http_503_with_explicit_full_queue_triggers_safe_retry(monkeypatch):
    from urllib.error import HTTPError
    from io import BytesIO
    import pytest
    bodies=[
      b'{"code":"video_queue_full","message":"video queue is full, please retry later"}',
      b'video_queue_full',
      b'{"error":{"code":"queue_full"}}',
    ]
    for body in bodies:
        def reject(*a,**k):
            raise HTTPError('https://apihub.agnes-ai.com/v1/videos',503,
                            'Service Unavailable',{},BytesIO(body))
        monkeypatch.setattr(agnes,'build_opener',lambda *a: type(
            'RejectedQueue',(),{'open':staticmethod(reject)})())
        with pytest.raises(agnes.AgnesQueueFull):
            agnes.api_json('POST','/v1/videos','test-only-agn-key',
                           {'model':agnes.MODEL,'prompt':'Two performers','mode':'text'})

def test_ambiguous_http_503_never_retries_and_never_logs_body(monkeypatch):
    from urllib.error import HTTPError
    from io import BytesIO
    import pytest
    body=b'Internal temporary failure. reference photo secret and user prompt.'
    def reject(*a,**k):
        raise HTTPError('https://apihub.agnes-ai.com/v1/videos',503,
                        'Service Unavailable',{},BytesIO(body))
    monkeypatch.setattr(agnes,'build_opener',lambda *a: type(
        'AmbiguousProviderError',(),{'open':staticmethod(reject)})())
    with pytest.raises(agnes.AgnesError) as exc:
        agnes.api_json('POST','/v1/videos','test-only-agn-key',
                       {'model':agnes.MODEL,'prompt':'Two performers','mode':'text'})
    assert not isinstance(exc.value,agnes.AgnesQueueFull)
    assert '503' in str(exc.value)
    assert 'photo secret' not in str(exc.value)
