"""PostgreSQL durability and scene-by-scene failover. Mock providers; no billing."""
import hashlib,os,secrets,uuid
import pytest
import psycopg
import scene_planner as plan
import postgres_scene_store as media
import postgres_job_store as wallet

PG=os.getenv('KOLBO_TEST_PG_DSN','')
pytestmark=pytest.mark.skipif(not PG,reason='PostgreSQL CI fixture unavailable')

@pytest.fixture
def env():
    store=media.SegmentStore(PG)
    store.bootstrap_segments()
    owner=hashlib.sha256(uuid.uuid4().bytes).hexdigest()
    other=hashlib.sha256(uuid.uuid4().bytes).hexdigest()
    with psycopg.connect(PG) as db:
        db.execute('INSERT INTO kolbo_wallets(owner_hash,balance) VALUES (%s,100),(%s,100)',
                    (owner,other))
    job=store.reserve(owner,secrets.token_urlsafe(24),
                      hashlib.sha256(b'2 people, 10 seconds').hexdigest(),25)
    yield store,owner,other,job

def test_exact_duration_minimum_cuts_and_no_invented_frames():
    scenes=plan.plan_exact(10,(4,6,8),people=2)
    assert [(s.index,s.start_ms,s.end_ms,s.previous_scene_index) for s in scenes]==[
        (0,0,6000,None),(1,6000,10000,0)]
    assert sum(s.duration_ms for s in scenes)==10000
    with pytest.raises(plan.UnsupportedPlan):
        plan.plan_exact(10,(3,8),people=2)
    with pytest.raises(plan.UnsupportedPlan):
        plan.plan_exact(10,(4,),people=2,max_scenes=2)
    with pytest.raises(plan.UnsupportedPlan):
        plan.plan_exact(10,(3,),people=3)

def test_initialize_is_idempotent_and_rejects_modified_continuity(env):
    store,user,other,job=env
    scenes=plan.plan_exact(10,(4,6,8),people=2)
    first=store.initialize(job.id,user,scenes)
    assert len(first)==2
    assert first[1].state=='planned'
    assert store.initialize(job.id,user,scenes)==first
    with pytest.raises(media.SegmentError,match='Scene plan differs'):
        store.initialize(job.id,user,plan.plan_exact(10,(5,),people=2))
    with pytest.raises(media.SegmentError):
        store.initialize(job.id,other,scenes)

def test_crash_after_post_is_not_blindly_restarted(env):
    store,user,other,job=env
    scenes=plan.plan_exact(10,(4,6,8),people=2)
    store.initialize(job.id,user,scenes)
    store.progress(job.id,user,0,'submitting',provider='agnes_flash')
    # Simulate timeout/restart with new database adapter instance.
    restarted=media.SegmentStore(PG)
    recovered=restarted.list_for_owner(job.id,user)
    assert recovered[0].provider=='agnes_flash'
    assert recovered[0].state=='submitting'
    with pytest.raises(media.SegmentError):
        restarted.progress(job.id,user,0,'planned')
    restarted.progress(job.id,user,0,'unknown_acceptance')
    with pytest.raises(media.SegmentError):
        restarted.progress(job.id,user,0,'planned')
    with pytest.raises(media.SegmentError):
        restarted.progress(job.id,user,1,'submitting',provider='other_gpu')
    accepted=restarted.progress(job.id,user,0,'accepted',task_id='original_task_001')
    assert accepted.task_id=='original_task_001'
    with pytest.raises(media.SegmentError):
        restarted.progress(job.id,user,0,'submitting',provider='other_gpu')

def test_safely_rejected_engine_can_change_before_any_task_id(env):
    store,user,other,job=env
    store.initialize(job.id,user,plan.plan_exact(10,(4,6,8),people=2))
    store.progress(job.id,user,0,'submitting',provider='agnes_flash')
    reset=store.progress(job.id,user,0,'planned',verified_rejection=True)
    assert reset.provider is None
    sent=store.progress(job.id,user,0,'submitting',provider='independent_gpu')
    assert sent.provider=='independent_gpu'
    accepted=store.progress(job.id,user,0,'accepted',task_id='gpu_render_task_123')
    assert accepted.task_id=='gpu_render_task_123'

def test_next_scene_requires_verified_previous_and_correct_media_receipt(env):
    store,user,other,job=env
    store.initialize(job.id,user,plan.plan_exact(10,(4,6,8),people=2))
    with pytest.raises(media.SegmentError,match='Prior scene'):
        store.progress(job.id,user,1,'submitting',provider='independent_gpu')
    store.progress(job.id,user,0,'submitting',provider='agnes_flash')
    store.progress(job.id,user,0,'accepted',task_id='agn_task_for_scene_0')
    with pytest.raises(media.SegmentError):
        store.progress(job.id,user,0,'verified',verified_output=True)
    store.progress(job.id,user,0,'downloaded',object_key=secrets.token_urlsafe(28))
    with pytest.raises(media.SegmentError):
        store.progress(job.id,user,0,'verified')
    store.progress(job.id,user,0,'verified',verified_output=True)
    second=store.progress(job.id,user,1,'submitting',provider='independent_gpu')
    assert second.state=='submitting'
    store.progress(job.id,user,1,'accepted',task_id='gpu_task_for_scene_1')
    store.progress(job.id,user,1,'downloaded',object_key=secrets.token_urlsafe(28))
    store.progress(job.id,user,1,'review_required')
    recovered=media.SegmentStore(PG).list_for_owner(job.id,user)
    assert [x.state for x in recovered]==['verified','review_required']
    store.progress(job.id,user,1,'verified',verified_output=True)
    assert all(x.state=='verified' for x in store.list_for_owner(job.id,user))

def test_no_cross_account_segment_access_and_no_filename_paths(env):
    store,user,other,job=env
    store.initialize(job.id,user,plan.plan_exact(10,(4,6,8),people=2))
    with pytest.raises(media.SegmentError):
        store.list_for_owner(job.id,other)
    with pytest.raises(media.SegmentError):
        store.progress(job.id,other,0,'submitting',provider='independent_gpu')
    store.progress(job.id,user,0,'submitting',provider='independent_gpu')
    store.progress(job.id,user,0,'accepted',task_id='good_task_12345')
    for bad in ['/etc/passwd','../other-owner.mp4','a'*4]:
        with pytest.raises(media.SegmentError):
            store.progress(job.id,user,0,'downloaded',object_key=bad)
    assert store.list_for_owner(job.id,user)[0].state=='accepted'

def test_job_completion_forbids_late_scene_modifications(env):
    store,user,other,job=env
    store.initialize(job.id,user,plan.plan_exact(10,(5,),people=2))
    store.transition(job.id,user,'failed_refunded',verified_rejection=True)
    with pytest.raises(media.SegmentError,match='finalized'):
        store.progress(job.id,user,0,'submitting',provider='any_engine')
