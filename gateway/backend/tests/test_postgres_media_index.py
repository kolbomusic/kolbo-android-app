"""Real temporary PostgreSQL ownership, immutable artifact, and expiry tests."""
import hashlib,os,secrets,time,uuid
from concurrent.futures import ThreadPoolExecutor
import pytest
import psycopg
import postgres_job_store as jobs
import postgres_media_index as media

PG=os.getenv('KOLBO_TEST_PG_DSN','')
pytestmark=pytest.mark.skipif(not PG,reason='Real Postgres fixture required')

@pytest.fixture
def account():
    store=jobs.PostgresJobStore(PG)
    store.bootstrap()
    idx=media.PostgresArtifactIndex(PG)
    idx.bootstrap()
    owner=hashlib.sha256(uuid.uuid4().bytes).hexdigest()
    with psycopg.connect(PG) as c:
        c.execute('INSERT INTO kolbo_wallets(owner_hash,balance) VALUES(%s,%s)',(owner,100))
    job=store.reserve(owner,secrets.token_urlsafe(30),
                      hashlib.sha256(uuid.uuid4().bytes).hexdigest(),12)
    return store,idx,owner,job

def params(owner,job,role='scene',sequence=0):
    return dict(job_id=job.id,owner_hash=owner,role=role,sequence_no=sequence,
       object_key=f'private/{owner}/{job.id}/{role}/{uuid.uuid4().hex}.mp4',
       sha256=hashlib.sha256(b'a secret AI movie').hexdigest(),
       media_type='video/mp4',byte_size=3000,
       expires_at=int(time.time())+7200)

def test_same_scene_registration_idempotent_cannot_overwrite(account):
    store,idx,owner,job=account
    data=params(owner,job)
    a=idx.attach(**data)
    b=idx.attach(**data)
    assert a.id==b.id
    with pytest.raises(media.ArtifactConflict):
        idx.attach(**(data|{'object_key':data['object_key'].replace('.mp4','_replacement.mp4')}))
    assert idx.get(artifact_id=a.id,job_id=job.id,owner_hash=owner)==a

def test_another_owner_cannot_reference_or_download_job_output(account):
    store,idx,owner,job=account
    data=params(owner,job,role='output')
    a=idx.attach(**data)
    attacker=hashlib.sha256(uuid.uuid4().bytes).hexdigest()
    with pytest.raises(media.ForeignArtifact):
        idx.attach(**(data|{'owner_hash':attacker,
            'object_key':data['object_key'].replace(owner,attacker)}))
    with pytest.raises(media.ForeignArtifact):
        idx.get(artifact_id=a.id,job_id=job.id,owner_hash=attacker)
    with pytest.raises(media.ForeignArtifact):
        idx.output_for_owner(job_id=job.id,owner_hash=attacker)

def test_output_requires_completed_job_and_never_exposes_draft(account):
    store,idx,owner,job=account
    data=params(owner,job,role='output')
    a=idx.attach(**data)
    with pytest.raises(media.ForeignArtifact):
        idx.output_for_owner(job_id=job.id,owner_hash=owner)
    store.transition(job.id,owner,'submitting',provider='mock_gpu')
    store.transition(job.id,owner,'accepted',task_id='mock_accepted_task_00001')
    store.transition(job.id,owner,'validating')
    store.transition(job.id,owner,'completed',verified_output=True)
    assert idx.output_for_owner(job_id=job.id,owner_hash=owner)==a
    with pytest.raises(media.ArtifactIndexError):
        idx.attach(**params(owner,job,role='reference'))

def test_scene_index_locks_across_concurrent_requests(account):
    store,idx,owner,job=account
    data=params(owner,job,role='scene')
    def insert(_):return idx.attach(**data)
    with ThreadPoolExecutor(max_workers=5) as pool:
        results=list(pool.map(insert,range(5)))
    assert len({r.id for r in results})==1

def test_expired_objects_remain_hidden_until_janitor_deleted(account):
    store,idx,owner,job=account
    data=params(owner,job)
    data['expires_at']=int(time.time())-100
    artifact=idx.attach(**data)
    with pytest.raises(media.ForeignArtifact):
        idx.get(artifact_id=artifact.id,job_id=job.id,owner_hash=owner)
    candidates=idx.expired()
    assert artifact.id in {x.id for x in candidates}
    idx.confirm_deleted(artifact.id)
    idx.confirm_deleted(artifact.id)
    assert artifact.id not in {x.id for x in idx.expired()}

def test_media_cannot_attach_wrong_owner_or_invalid_path(account):
    store,idx,owner,job=account
    data=params(owner,job)
    with pytest.raises(media.ArtifactIndexError):
        idx.attach(**(data|{'object_key':'private/other-object/not-valid'}))
    with pytest.raises(media.ArtifactIndexError):
        idx.attach(**(data|{'role':'reference','media_type':'video/mp4'}))
    with pytest.raises(media.ArtifactIndexError):
        idx.attach(**(data|{'sha256':'bad sha'}))
