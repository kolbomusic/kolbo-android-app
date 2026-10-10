"""Real PostgreSQL ACID integration tests, without any provider or payment calls."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import os
import secrets
import uuid
import pytest
import psycopg
import postgres_job_store as durable

PG=os.getenv("KOLBO_TEST_PG_DSN","")
pytestmark=pytest.mark.skipif(not PG,reason="Live PostgreSQL fixture not configured")

def owner():
    return hashlib.sha256(uuid.uuid4().bytes).hexdigest()

def terms():
    return secrets.token_urlsafe(32),hashlib.sha256(uuid.uuid4().bytes).hexdigest()

@pytest.fixture
def account():
    store=durable.PostgresJobStore(PG)
    store.bootstrap()
    user=owner()
    with psycopg.connect(PG) as c:
        c.execute("INSERT INTO kolbo_wallets (owner_hash,balance) VALUES (%s,%s)",
                  (user,100))
    return store,user

def test_balance_and_atomic_idempotency(account):
    store,user=account
    key,digest=terms()
    first=store.reserve(user,key,digest,30)
    assert first.created_new and first.state=="reserved"
    assert store.balance(user)==70
    again=store.reserve(user,key,digest,30)
    assert first.id==again.id and not again.created_new
    assert store.balance(user)==70
    with pytest.raises(durable.DuplicateKeyConflict):
        store.reserve(user,key,hashlib.sha256(b"other").hexdigest(),30)
    assert store.balance(user)==70

def test_two_simultaneous_reservations_only_debit_once(account):
    store,user=account
    key,digest=terms()
    with ThreadPoolExecutor(max_workers=8) as pool:
        results=list(pool.map(lambda _:store.reserve(user,key,digest,40),range(8)))
    assert len({r.id for r in results})==1
    assert sum(int(r.created_new) for r in results)==1
    assert store.balance(user)==60

def test_insufficient_balance_creates_no_job(account):
    store,user=account
    key,digest=terms()
    with pytest.raises(durable.InsufficientCredits):
        store.reserve(user,key,digest,101)
    assert store.balance(user)==100
    with psycopg.connect(PG) as c:
        count=c.execute("SELECT count(*) FROM kolbo_generation_jobs WHERE owner_hash=%s",
                        (user,)).fetchone()[0]
    assert count==0

def test_durable_provider_acceptance_survives_connection_reopen(account):
    store,user=account
    key,digest=terms()
    job=store.reserve(user,key,digest,25)
    current=store.transition(job.id,user,"submitting",provider="agnes_flash")
    assert current.provider_name=="agnes_flash"
    # Simulate a crashed process with a fresh database adapter instance.
    recovered=durable.PostgresJobStore(PG)
    pending=recovered.unresolved()
    same=next(r for r in pending if r.id==job.id)
    assert same.state=="submitting"
    assert same.provider_name=="agnes_flash"
    # Network timeout after POST must not trigger an automatic second POST.
    recovered.transition(job.id,user,"unknown_acceptance")
    assert recovered.get(job.id,user).state=="unknown_acceptance"
    with pytest.raises(durable.InvalidState):
        recovered.transition(job.id,user,"reserved")
    with pytest.raises(durable.InvalidState):
        recovered.transition(job.id,user,"failed_refunded",verified_rejection=True)
    accepted=recovered.transition(job.id,user,"accepted",task_id="provider_accepted_001")
    assert accepted.provider_task_id=="provider_accepted_001"
    recovered.transition(job.id,user,"validating")
    with pytest.raises(durable.InvalidState):
        recovered.transition(job.id,user,"completed")
    complete=recovered.transition(job.id,user,"completed",verified_output=True)
    assert complete.state=="completed"
    assert recovered.balance(user)==75

def test_verified_queue_refusal_allows_new_engine_after_reset(account):
    store,user=account
    key,digest=terms()
    job=store.reserve(user,key,digest,10)
    store.transition(job.id,user,"submitting",provider="agnes_flash")
    with pytest.raises(durable.InvalidState):
        store.transition(job.id,user,"reserved")
    reset=store.transition(job.id,user,"reserved",verified_rejection=True)
    assert reset.provider_name is None
    store.transition(job.id,user,"submitting",provider="independent_gpu")
    store.transition(job.id,user,"accepted",task_id="gpu_job_001")
    assert store.get(job.id,user).provider_name=="independent_gpu"

def test_refund_exactly_once_and_reject_post_terminal_state(account):
    store,user=account
    key,digest=terms()
    job=store.reserve(user,key,digest,60)
    store.transition(job.id,user,"submitting",provider="agnes_flash")
    failed=store.transition(job.id,user,"failed_refunded",verified_rejection=True)
    assert failed.state=="failed_refunded"
    assert store.balance(user)==100
    replay=store.transition(job.id,user,"failed_refunded",verified_rejection=True)
    assert replay.id==job.id and store.balance(user)==100
    with pytest.raises(durable.InvalidState):
        store.transition(job.id,user,"submitting",provider="agnes_flash")
    assert store.balance(user)==100

def test_cross_account_own_job_access_prohibited(account):
    store,user=account
    key,digest=terms()
    job=store.reserve(user,key,digest,10)
    stranger=owner()
    with pytest.raises(durable.StoreError):
        store.get(job.id,stranger)
    with pytest.raises(durable.StoreError):
        store.transition(job.id,stranger,"failed_refunded",verified_rejection=True)
    assert store.get(job.id,user).state=="reserved"

def test_invalid_identifiers_and_provider_names_rejected(account):
    store,user=account
    key,digest=terms()
    with pytest.raises(durable.StoreError):
        store.reserve("impostor",key,digest,10)
    with pytest.raises(durable.StoreError):
        store.reserve(user,key,"injected SQL",10)
    with pytest.raises(durable.StoreError):
        store.reserve(user,key,digest,-1)
    job=store.reserve(user,key,digest,10)
    with pytest.raises(durable.InvalidState):
        store.transition(job.id,user,"submitting",provider="https://invalid/key")
    assert store.get(job.id,user).state=="reserved"
