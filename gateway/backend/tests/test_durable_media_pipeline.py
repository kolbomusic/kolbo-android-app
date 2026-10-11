"""Real FFmpeg -> fake private object bucket -> real CI Postgres -> crash restore."""
import hashlib,os,secrets,subprocess,time,uuid
from pathlib import Path
import pytest
import psycopg
import postgres_job_store as jobstore
import postgres_media_index as registry
import private_media_store as objstore
import durable_media_pipeline as pipeline
from test_private_media_store import FakeS3

PG=os.getenv('KOLBO_TEST_PG_DSN','')
pytestmark=pytest.mark.skipif(not PG,reason='Requires real temporary PostgreSQL test database')

def video(path:Path,seconds=1.0,frequency=440):
    path.parent.mkdir(parents=True,exist_ok=True)
    cmd=['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y',
         '-f','lavfi','-i','testsrc2=size=320x180:rate=24',
         '-f','lavfi','-i',f'sine=frequency={frequency}:sample_rate=48000',
         '-t',str(seconds),'-c:v','libx264','-preset','ultrafast',
         '-threads','2','-pix_fmt','yuv420p','-c:a','aac','-b:a','96k',
         '-movflags','+faststart',str(path)]
    subprocess.run(cmd,capture_output=True,check=True,timeout=30)
    return path

@pytest.fixture
def setup(tmp_path):
    jobs=jobstore.PostgresJobStore(PG);jobs.bootstrap()
    index=registry.PostgresArtifactIndex(PG);index.bootstrap()
    owner=hashlib.sha256(uuid.uuid4().bytes).hexdigest()
    foreign=hashlib.sha256(uuid.uuid4().bytes).hexdigest()
    with psycopg.connect(PG) as con:
        con.execute('INSERT INTO kolbo_wallets(owner_hash,balance) VALUES (%s,100)',(owner,))
        con.execute('INSERT INTO kolbo_wallets(owner_hash,balance) VALUES (%s,100)',(foreign,))
    job=jobs.reserve(owner,secrets.token_urlsafe(32),
          hashlib.sha256(uuid.uuid4().bytes).hexdigest(),20)
    jobs.transition(job.id,owner,'submitting',provider='independent_gpu')
    jobs.transition(job.id,owner,'accepted',task_id='accepted_video_task_'+uuid.uuid4().hex)
    fake=FakeS3()
    storage=objstore.PrivateObjectStore(fake,'private-kolbo-test-objects',
                                        clock=lambda:time.time())
    worker=pipeline.DurableMediaPipeline(jobs,index,storage)
    return jobs,index,storage,fake,owner,foreign,job,worker,tmp_path

def test_scenes_and_final_survive_new_worker_without_double_billing(setup):
    jobs,index,storage,fake,owner,foreign,job,worker,tmp=setup
    scene=video(tmp/'scene0.mp4')
    saved=worker.upload_scene(owner_hash=owner,job_id=job.id,index=0,
       file=scene,expected_ms=1000,require_audio=True)
    assert saved.media_type=='video/mp4'
    assert jobs.balance(owner)==80
    # Simulate cloud worker restart. No in-memory job registry remains.
    resumed=pipeline.DurableMediaPipeline(
        jobstore.PostgresJobStore(PG),registry.PostgresArtifactIndex(PG),
        objstore.PrivateObjectStore(fake,storage.bucket,clock=lambda:time.time()))
    file=resumed.restore_scene(owner_hash=owner,job_id=job.id,index=0,
       destination_directory=tmp/'restored')
    assert file.read_bytes()==scene.read_bytes()
    duplicate=resumed.upload_scene(owner_hash=owner,job_id=job.id,index=0,
       file=scene,expected_ms=1000,require_audio=True)
    assert duplicate.id==saved.id
    assert jobs.balance(owner)==80
    assert len(fake.data)==1

    jobs.transition(job.id,owner,'validating')
    output=resumed.save_final_draft(owner_hash=owner,job_id=job.id,
       file=file,expected_ms=1000,require_audio=True)
    with pytest.raises(registry.ForeignArtifact):
        resumed.final_download_url(owner_hash=owner,job_id=job.id)
    with pytest.raises(registry.ForeignArtifact):
        resumed.final_download_url(owner_hash=foreign,job_id=job.id)
    # Human-reviewed QA would be a separate trusted step; this test only
    # simulates that state transition and DOES NOT assert identity/lip sync.
    jobs.transition(job.id,owner,'completed',verified_output=True)
    url=resumed.final_download_url(owner_hash=owner,job_id=job.id)
    assert url.startswith('https://private-object.example.com/')
    assert output.role=='output'
    assert jobs.balance(owner)==80

def test_short_or_silent_video_rejected_before_storage(setup):
    jobs,index,storage,fake,owner,foreign,job,worker,tmp=setup
    short=video(tmp/'short.mp4',seconds=1)
    with pytest.raises(pipeline.PipelineError,match='shorter or longer'):
        worker.upload_scene(owner_hash=owner,job_id=job.id,index=0,
          file=short,expected_ms=4000,require_audio=True)
    assert not fake.data

def test_foreign_account_cannot_restore_scene(setup):
    jobs,index,storage,fake,owner,foreign,job,worker,tmp=setup
    original=video(tmp/'scene.mp4')
    worker.upload_scene(owner_hash=owner,job_id=job.id,index=0,
      file=original,expected_ms=1000,require_audio=True)
    with pytest.raises(jobstore.StoreError):
        worker.restore_scene(owner_hash=foreign,job_id=job.id,index=0,
          destination_directory=tmp/'bad')
    assert not (tmp/'bad').exists()

def test_changed_scene_rejected_by_integrity_contract(setup):
    jobs,index,storage,fake,owner,foreign,job,worker,tmp=setup
    scene_a=video(tmp/'scene_a.mp4',frequency=440)
    scene_b=video(tmp/'scene_b.mp4',frequency=660)
    worker.upload_scene(owner_hash=owner,job_id=job.id,index=0,
        file=scene_a,expected_ms=1000,require_audio=True)
    with pytest.raises(registry.ArtifactConflict):
        worker.upload_scene(owner_hash=owner,job_id=job.id,index=0,
            file=scene_b,expected_ms=1000,require_audio=True)
    assert len(fake.data)==1
