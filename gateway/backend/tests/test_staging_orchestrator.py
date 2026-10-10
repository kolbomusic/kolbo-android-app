"""End-to-end simulated flow across ledger, verified routing, failover and QC."""
from decimal import Decimal as D
import hashlib,sqlite3
import pytest
import execution_guard as quality
import staging_job_ledger as ledger
import staging_orchestrator as orchestrator
import operations_feedback

OWNER='a'*64
SPEC=hashlib.sha256(b'8s two people on stage singing in Bukhori').hexdigest()
KEY='no_repeat_generation_0123456789abcdef'

def request(**updates):
    base=dict(seconds=8,distinct_people=2,needs_audio=True,needs_lip_sync=True,
      requires_consistent_people=True,quality_preset='premium',
      max_authorized_spend_usd=D('0'),explicit_image_consent=True,
      commercial_use=False)
    return quality.VideoRequest(**(base|updates))

def proof(name,**updates):
    base=dict(name=name,max_independent_people=2,
      supported_durations=(8,),can_sync_requested_language=True,
      supports_audio=True,keyframe_continuity=True,has_live_capacity=True,
      account_price_verified=True,unit_cost_usd=D('0'),
      is_active=True,terms_permit_requested_use=True)
    return quality.ProviderProof(**(base|updates))

def good_segment(**overrides):
    base=dict(index=0,start_ms=0,end_ms=8000,measured_ms=8000,
      container_valid=True,audio_present=True,source_identities_reviewed=True,
      lips_and_language_reviewed=True,continuity_with_previous_reviewed=True,
      signed_render_receipt=True)
    return quality.SegmentResult(**(base|overrides))

@pytest.fixture
def db(tmp_path):
    path=str(tmp_path/'state.db')
    cx=sqlite3.connect(path,check_same_thread=False,timeout=5)
    store=ledger.StagingLedger(cx)
    cx.execute('INSERT INTO wallets(owner_hash,balance) VALUES (?,?)',(OWNER,100))
    cx.commit()
    yield store,path
    cx.close()

def orchestrate(store,**overrides):
    stats=operations_feedback.Feedback()
    return orchestrator.StagingCoordinator(store,stats),stats

def submit(coordinator,*,spec_digest=SPEC,key=KEY,points=20,
           providers=None,request_spec=None,dispatch=None):
    return coordinator.submit(owner_hash=OWNER,idempotency_key=key,
       spec_digest=spec_digest,points=points,
       request=request_spec or request(),
       verified_providers=providers or [proof('provider_a')],
       dispatch=dispatch or (lambda _: 'valid_accepted_task123'))

def test_verified_two_person_clip_happy_path_and_exactly_once_points(db):
    store,_=db
    co,_=orchestrate(store)
    called=[]
    output=submit(co,dispatch=lambda name: called.append(name) or 'task_12345')
    assert output.outcome=='accepted'
    assert output.attempted==('provider_a',)
    assert store.balance(OWNER)==80
    duplicate=submit(co,dispatch=lambda _:pytest.fail('duplicate provider POST'))
    assert duplicate.outcome=='existing_job'
    assert duplicate.job.id==output.job.id
    assert store.balance(OWNER)==80
    result=co.deliver(owner_hash=OWNER,job_id=output.job.id,request=request(),
        segments=[good_segment()],provider='provider_a')
    assert result.available_to_customer
    assert result.job.state=='completed'
    replay=co.deliver(owner_hash=OWNER,job_id=output.job.id,request=request(),
        segments=[good_segment()],provider='provider_a')
    assert replay.job.state=='completed'
    assert store.balance(OWNER)==80

def test_two_engines_only_fallback_when_safely_refused(db):
    store,_=db
    co,_=orchestrate(store)
    attempts=[]
    def dispatch(name):
        attempts.append(name)
        if name=='a_first':raise orchestrator.RejectedBeforeAcceptance()
        return 'task_accepted_456'
    result=submit(co,providers=[proof('a_first'),proof('b_second')],
                  dispatch=dispatch)
    assert result.outcome=='accepted'
    assert attempts==['a_first','b_second']
    assert result.provider=='b_second'
    assert store.balance(OWNER)==80

def test_ambiguous_submission_keeps_credits_and_never_calls_backup(db):
    store,_=db
    co,_=orchestrate(store)
    attempts=[]
    def dispatch(name):
        attempts.append(name)
        raise orchestrator.UnknownSubmission()
    result=submit(co,providers=[proof('first'),proof('second')],
                  dispatch=dispatch)
    assert result.outcome=='provider_acceptance_unknown'
    assert not result.retry_safe
    assert result.job.state=='unknown_acceptance'
    assert attempts==['first']
    assert store.balance(OWNER)==80
    replay=submit(co,providers=[proof('first'),proof('second')],
                  dispatch=lambda _:pytest.fail('Must not resubmit unknown task'))
    assert replay.outcome=='existing_job'
    assert store.balance(OWNER)==80

def test_read_only_recovery_after_process_restart(db):
    store,path=db
    co,_=orchestrate(store)
    submission=submit(co,dispatch=lambda _:(_ for _ in ()).throw(
        orchestrator.UnknownSubmission()))
    new_conn=sqlite3.connect(path,check_same_thread=False)
    restarted_store=ledger.StagingLedger(new_conn)
    restarted_co=orchestrator.StagingCoordinator(restarted_store)
    try:
        pending=restarted_co.recover(submission.job.id,owner_hash=OWNER)
        assert pending.state=='unknown_acceptance'
        assert restarted_store.balance(OWNER)==80
        resolved=restarted_co.recover(submission.job.id,owner_hash=OWNER,
             accepted_task_id='task_accepted_before_restart')
        assert resolved.state=='accepted'
        result=restarted_co.deliver(owner_hash=OWNER,job_id=submission.job.id,
            request=request(),segments=[good_segment()],provider='provider_a')
        assert result.available_to_customer
        assert restarted_store.balance(OWNER)==80
    finally:new_conn.close()

def test_all_rejections_refund_exactly_once_and_do_not_publish(db):
    store,_=db
    co,_=orchestrate(store)
    output=submit(co,providers=[proof('provider_a'),proof('provider_b')],
      dispatch=lambda _:(_ for _ in ()).throw(
          orchestrator.RejectedBeforeAcceptance()))
    assert output.job.state=='failed_refunded'
    assert output.outcome=='all_explicitly_rejected'
    assert store.balance(OWNER)==100
    replay=submit(co,dispatch=lambda _:pytest.fail('duplicate supplier POST'))
    assert replay.outcome=='existing_job'
    assert store.balance(OWNER)==100

def test_lost_identity_or_three_second_video_refunds_points(db):
    store,_=db
    co,_=orchestrate(store)
    job=submit(co)
    failed=co.deliver(owner_hash=OWNER,job_id=job.job.id,request=request(),
      segments=[good_segment(end_ms=3000,measured_ms=3000)],
      provider='provider_a')
    assert failed.job.state=='failed_refunded'
    assert not failed.available_to_customer
    assert store.balance(OWNER)==100

def test_unverified_singing_or_face_identity_keeps_draft_unpublished(db):
    store,_=db
    co,_=orchestrate(store)
    job=submit(co)
    draft=co.deliver(owner_hash=OWNER,job_id=job.job.id,request=request(),
      segments=[good_segment(lips_and_language_reviewed=False,
                            source_identities_reviewed=False)],
      provider='provider_a')
    assert not draft.available_to_customer
    assert draft.quality.verdict is quality.PublishVerdict.NEEDS_REVIEW
    assert store.view(job.job.id).state=='validating'
    assert store.balance(OWNER)==80

def test_no_provider_price_evidence_means_no_job_or_debit(db):
    store,_=db
    co,_=orchestrate(store)
    with pytest.raises(quality.GateRejected):
        submit(co,providers=[proof('unknown',
            account_price_verified=False,unit_cost_usd=None)],
            dispatch=lambda _:pytest.fail('Provider should not be contacted'))
    assert store.balance(OWNER)==100

def test_one_identity_unsupported_by_backup_does_not_morph_faces(db):
    store,_=db
    co,_=orchestrate(store)
    bad=proof('backup_one_image',max_independent_people=1)
    primary=proof('agn_two_image')
    hits=[]
    def dispatch(engine):
        hits.append(engine)
        raise orchestrator.RejectedBeforeAcceptance()
    output=submit(co,providers=[primary,bad],dispatch=dispatch)
    assert hits==['agn_two_image']
    assert output.job.state=='failed_refunded'
    assert store.balance(OWNER)==100

def test_insufficient_credits_never_contacts_provider(db):
    store,_=db
    co,_=orchestrate(store)
    with pytest.raises(ledger.NoCredits):
        submit(co,points=120,dispatch=lambda _:pytest.fail('no credits'))
    assert store.balance(OWNER)==100


def test_owner_isolation_blocks_foreign_receipt_recovery_or_delivery(db):
    store,_=db
    co,_=orchestrate(store)
    sub=submit(co)
    outsider='b'*64
    with pytest.raises(ledger.LedgerError):
        co.recover(sub.job.id,owner_hash=outsider)
    with pytest.raises(ledger.LedgerError):
        co.deliver(owner_hash=outsider,job_id=sub.job.id,
            request=request(),segments=[good_segment()],provider='provider_a')
    assert store.view(sub.job.id).state=='accepted'
    assert store.balance(OWNER)==80
