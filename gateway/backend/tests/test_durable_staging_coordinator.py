"""Simulated provider E2E through real PostgreSQL; no external AI API spending."""
from decimal import Decimal as D
import hashlib,os,uuid
import psycopg,pytest
import postgres_job_store as store
import durable_staging_coordinator as orchestration
import execution_guard as guard

PG=os.getenv('KOLBO_TEST_PG_DSN','')
pytestmark=pytest.mark.skipif(not PG,reason='PostgreSQL fixture unavailable')

def request():
    return guard.VideoRequest(seconds=8,distinct_people=2,needs_audio=True,
        needs_lip_sync=True,requires_consistent_people=True,quality_preset='premium',
        max_authorized_spend_usd=D('0'),explicit_image_consent=True,commercial_use=False)

def provider(name,*,refs=2,cost='0'):
    return guard.ProviderProof(name=name,max_independent_people=refs,
        supported_durations=(8,),can_sync_requested_language=True,
        supports_audio=True,keyframe_continuity=True,has_live_capacity=True,
        account_price_verified=True,unit_cost_usd=D(cost),
        is_active=True,terms_permit_requested_use=True)

def segment(**changes):
    values=dict(index=0,start_ms=0,end_ms=8000,measured_ms=8000,
        container_valid=True,audio_present=True,source_identities_reviewed=True,
        lips_and_language_reviewed=True,continuity_with_previous_reviewed=True,
        signed_render_receipt=True)
    return guard.SegmentResult(**(values|changes))

@pytest.fixture
def env():
    instance=store.PostgresJobStore(PG)
    instance.bootstrap()
    owner=hashlib.sha256(uuid.uuid4().bytes).hexdigest()
    with psycopg.connect(PG) as db:
        db.execute('INSERT INTO kolbo_wallets(owner_hash,balance) VALUES(%s,%s)',
                   (owner,100))
    key='video_req_'+uuid.uuid4().hex
    digest=hashlib.sha256(b'unchanged script and two photos').hexdigest()
    return instance,owner,key,digest

def create(coordinator,owner,key,digest,*,names=None,submit=None):
    return coordinator.submit(owner_hash=owner,request_key=key,
        spec_digest=digest,credit_points=20,request=request(),
        provider_proofs=names or [provider('agnes_flash')],
        provider_submit=submit or (lambda n:'task_realistic_mock_001'))

def test_full_verified_scene_and_single_credit_charge(env):
    instance,owner,key,digest=env
    coord=orchestration.DurableStagingCoordinator(instance)
    output=create(coord,owner,key,digest)
    assert output.status=='accepted'
    assert instance.balance(owner)==80
    other=orchestration.DurableStagingCoordinator(store.PostgresJobStore(PG))
    duplicate=create(other,owner,key,digest,submit=lambda n:pytest.fail('double POST'))
    assert duplicate.status=='existing_job'
    assert duplicate.job.id==output.job.id
    receipt=other.review(job_id=output.job.id,owner_hash=owner,
                         request=request(),segments=[segment()])
    assert receipt.published and receipt.job.state=='completed'
    assert instance.balance(owner)==80

def test_two_engines_only_fallback_on_unambiguous_queue_refusal(env):
    instance,owner,key,digest=env
    coord=orchestration.DurableStagingCoordinator(instance)
    attempts=[]
    def dispatch(name):
        attempts.append(name)
        if name=='a_busy':
            raise orchestration.DefinitelyRejected('queue full, not accepted')
        return 'task_second_engine_001'
    answer=create(coord,owner,key,digest,
        names=[provider('a_busy'),provider('b_available')],
        submit=dispatch)
    assert answer.status=='accepted'
    assert answer.sent_to==('a_busy','b_available')
    assert answer.job.provider_name=='b_available'
    assert instance.balance(owner)==80

def test_crash_during_submission_never_automatically_posts_again(env):
    instance,owner,key,digest=env
    coord=orchestration.DurableStagingCoordinator(instance)
    attempts=[]
    def timeout(name):
        attempts.append(name)
        raise TimeoutError('provider may have accepted before timeout')
    receipt=create(coord,owner,key,digest,
        names=[provider('first'),provider('second')],submit=timeout)
    assert receipt.status=='requires_supplier_reconciliation'
    assert receipt.sent_to==('first',)
    new_process=orchestration.DurableStagingCoordinator(store.PostgresJobStore(PG))
    pending=new_process.recover(owner_hash=owner,job_id=receipt.job.id)
    assert pending.state=='unknown_acceptance'
    duplicate=create(new_process,owner,key,digest,
        names=[provider('first'),provider('second')],
        submit=lambda name:pytest.fail('must not resubmit unknown request'))
    assert duplicate.status=='existing_job'
    completed_reconcile=new_process.recover(owner_hash=owner,
        job_id=receipt.job.id,accepted_task_id='recovered_original_task')
    assert completed_reconcile.state=='accepted'
    assert completed_reconcile.provider_name=='first'
    assert instance.balance(owner)==80

def test_three_second_video_or_missing_audio_cannot_deliver(env):
    instance,owner,key,digest=env
    coord=orchestration.DurableStagingCoordinator(instance)
    accepted=create(coord,owner,key,digest)
    failed=coord.review(owner_hash=owner,job_id=accepted.job.id,
                        request=request(),segments=[
                          segment(end_ms=3042,measured_ms=3042)])
    assert not failed.published
    assert failed.job.state=='failed_refunded'
    assert 'total_duration_mismatch' in failed.quality.blockers
    assert instance.balance(owner)==100

def test_identity_lips_uncertain_stays_unpublished(env):
    instance,owner,key,digest=env
    coord=orchestration.DurableStagingCoordinator(instance)
    accepted=create(coord,owner,key,digest)
    staged=coord.review(owner_hash=owner,job_id=accepted.job.id,
        request=request(),segments=[
            segment(source_identities_reviewed=False,lips_and_language_reviewed=False)])
    assert not staged.published
    assert staged.job.state=='validating'
    assert instance.balance(owner)==80
    verified=coord.review(owner_hash=owner,job_id=accepted.job.id,
        request=request(),segments=[segment()])
    assert verified.published and verified.job.state=='completed'

def test_wallet_and_owner_isolation_for_recovery(env):
    instance,owner,key,digest=env
    coord=orchestration.DurableStagingCoordinator(instance)
    accepted=create(coord,owner,key,digest)
    attacker=hashlib.sha256(uuid.uuid4().bytes).hexdigest()
    with pytest.raises(store.StoreError):
        coord.recover(owner_hash=attacker,job_id=accepted.job.id)
    with pytest.raises(store.StoreError):
        coord.review(owner_hash=attacker,job_id=accepted.job.id,
                     request=request(),segments=[segment()])
    assert instance.balance(owner)==80

def test_unverified_provider_cost_cannot_start_generation(env):
    instance,owner,key,digest=env
    coord=orchestration.DurableStagingCoordinator(instance)
    with pytest.raises(guard.GateRejected):
        create(coord,owner,key,digest,
               names=[provider('provider_with_unknown_price',cost='0.50')],
               submit=lambda n:pytest.fail('must not submit unauthorized spending'))
    assert instance.balance(owner)==100

def test_incompatible_single_image_fallback_cannot_replace_two_identities(env):
    instance,owner,key,digest=env
    coord=orchestration.DurableStagingCoordinator(instance)
    sent=[]
    def refuses(n):
        sent.append(n)
        raise orchestration.DefinitelyRejected()
    result=create(coord,owner,key,digest,
                  names=[provider('dual_identity'),provider('single_reference',refs=1)],
                  submit=refuses)
    assert result.status=='no_provider_accepted'
    assert sent==['dual_identity']
    assert instance.balance(owner)==100
