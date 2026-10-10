"""Verify transactional credit reservations and recovery across process restart."""
import hashlib,sqlite3,threading
import pytest
import staging_job_ledger as ledger

OWNER='a'*64
OTHER='b'*64
KEY='client_token_24chars_abcdefgh'
SPEC=hashlib.sha256(b'canonical safe reference specification').hexdigest()

@pytest.fixture
def storage(tmp_path):
    path=tmp_path/'staging.sqlite'
    conn=sqlite3.connect(str(path),timeout=7,check_same_thread=False)
    conn.execute('INSERT OR IGNORE INTO wallets(owner_hash,balance) VALUES (?,?)',
                 (OWNER,100)) if False else None
    obj=ledger.StagingLedger(conn)
    conn.execute('INSERT INTO wallets(owner_hash,balance) VALUES (?,?)',(OWNER,100))
    conn.commit()
    yield obj,path
    conn.close()

def test_same_request_never_double_debits(storage):
    store,_=storage
    original=store.reserve(OWNER,KEY,SPEC,15)
    assert original.created_new is True
    repeated=store.reserve(OWNER,KEY,SPEC,15)
    assert repeated.id==original.id
    assert not repeated.created_new
    assert store.balance(OWNER)==85

def test_changed_request_under_same_key_is_blocked(storage):
    store,_=storage
    store.reserve(OWNER,KEY,SPEC,15)
    with pytest.raises(ledger.IdempotencyConflict):
        store.reserve(OWNER,KEY,hashlib.sha256(b'different clip').hexdigest(),15)
    with pytest.raises(ledger.IdempotencyConflict):
        store.reserve(OWNER,KEY,SPEC,20)
    assert store.balance(OWNER)==85

def test_no_credit_never_creates_generation(storage):
    store,_=storage
    with pytest.raises(ledger.NoCredits):
        store.reserve(OWNER,KEY,SPEC,110)
    assert store.balance(OWNER)==100

def test_rejected_before_provider_acceptance_refunds_exactly_once(storage):
    store,_=storage
    job=store.reserve(OWNER,KEY,SPEC,30)
    store.progress(job.id,'submitting')
    failed=store.progress(job.id,'failed_refunded',rejection_verified=True)
    assert failed.state=='failed_refunded'
    assert store.balance(OWNER)==100
    with pytest.raises(ledger.InvalidTransition):
        store.progress(job.id,'failed_refunded',rejection_verified=True)
    assert store.balance(OWNER)==100

def test_ambiguous_request_cannot_resubmit_or_fraudulently_refund(storage):
    store,_=storage
    job=store.reserve(OWNER,KEY,SPEC,20)
    store.progress(job.id,'submitting')
    store.progress(job.id,'unknown_acceptance')
    with pytest.raises(ledger.InvalidTransition):
        store.progress(job.id,'reserved')
    with pytest.raises(ledger.InvalidTransition):
        store.progress(job.id,'failed_refunded')
    assert store.balance(OWNER)==80
    store.progress(job.id,'reserved',rejection_verified=True)
    store.progress(job.id,'submitting')
    store.progress(job.id,'accepted',provider_task_id='real_provider_task')
    assert store.balance(OWNER)==80

def test_unverified_but_accepted_job_requires_qa_before_completion(storage):
    store,_=storage
    job=store.reserve(OWNER,KEY,SPEC,50)
    store.progress(job.id,'submitting')
    with pytest.raises(ledger.InvalidTransition):
        store.progress(job.id,'accepted')
    store.progress(job.id,'accepted',provider_task_id='task-id-1')
    with pytest.raises(ledger.InvalidTransition):
        store.progress(job.id,'accepted',provider_task_id='task-id-2')
    store.progress(job.id,'validating')
    with pytest.raises(ledger.InvalidTransition):
        store.progress(job.id,'completed')
    store.progress(job.id,'completed',qa_passed=True)
    assert store.balance(OWNER)==50
    with pytest.raises(ledger.InvalidTransition):
        store.progress(job.id,'failed_refunded')

def test_qa_failed_video_refunds_customer_though_supplier_may_have_charged(storage):
    store,_=storage
    job=store.reserve(OWNER,KEY,SPEC,40)
    store.progress(job.id,'submitting')
    store.progress(job.id,'accepted',provider_task_id='task-id-qa')
    store.progress(job.id,'validating')
    store.progress(job.id,'failed_refunded')
    assert store.balance(OWNER)==100

def test_job_and_balance_survive_sqlite_reopen_in_test_environment(storage):
    store,path=storage
    job=store.reserve(OWNER,KEY,SPEC,15)
    conn=sqlite3.connect(str(path),timeout=7,check_same_thread=False)
    reopened=ledger.StagingLedger(conn)
    try:
        assert reopened.view(job.id).state=='reserved'
        assert reopened.balance(OWNER)==85
        repeated=reopened.reserve(OWNER,KEY,SPEC,15)
        assert repeated.id==job.id
    finally:
        conn.close()

def test_concurrent_identical_requests_charge_once(storage):
    store,_=storage
    requests=[]
    failures=[]
    def task():
        try:
            requests.append(store.reserve(OWNER,KEY,SPEC,40))
        except Exception as e:failures.append(e)
    runners=[threading.Thread(target=task) for _ in range(8)]
    for runner in runners:runner.start()
    for runner in runners:runner.join()
    assert not failures
    assert len({j.id for j in requests})==1
    assert store.balance(OWNER)==60

def test_invalid_owner_and_idempotency_key_rejected(storage):
    store,_=storage
    with pytest.raises(ledger.LedgerError):
        store.reserve('123',KEY,SPEC,10)
    with pytest.raises(ledger.LedgerError):
        store.reserve(OWNER,'guessable',SPEC,10)
    with pytest.raises(ledger.LedgerError):
        store.reserve(OWNER,KEY,SPEC,-1)
