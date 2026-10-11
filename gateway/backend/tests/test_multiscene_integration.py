"""Full ten-second, two-scene, PostgreSQL + FFmpeg exercise.

Uses synthetic frames and tones, NEVER claims AI character preservation.
Staged-only path validates model task receipts, crash-safe per-scene state,
actual audio continuity and exact duration before human identity QA.
"""
import hashlib,os,secrets,subprocess,uuid,shutil
from decimal import Decimal as D
from pathlib import Path
import pytest
import psycopg
import postgres_scene_store as stored
import scene_planner as planner
import scene_assembler as joiner
import execution_guard as guard

PG=os.getenv('KOLBO_TEST_PG_DSN','')
pytestmark=pytest.mark.skipif(
    not PG or not shutil.which('ffmpeg') or not shutil.which('ffprobe'),
    reason='Real PostgreSQL and ffmpeg needed')

def synthetic_media(path:Path,seconds:int,tone:int)->Path:
    path.parent.mkdir(parents=True,exist_ok=True)
    subprocess.run(['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y',
       '-f','lavfi','-i','testsrc2=size=256x144:rate=24',
       '-f','lavfi','-i',f'sine=frequency={tone}:sample_rate=48000',
       '-t',str(seconds),'-c:v','libx264','-preset','ultrafast',
       '-pix_fmt','yuv420p','-threads','2',
       '-c:a','aac','-b:a','96k','-movflags','+faststart',str(path)],
       check=True,capture_output=True,timeout=60)
    return path

def test_two_scene_recovery_compilation_audio_and_no_false_identity_claim(tmp_path):
    store=stored.SegmentStore(PG)
    store.bootstrap_segments()
    user=hashlib.sha256(uuid.uuid4().bytes).hexdigest()
    with psycopg.connect(PG) as db:
        db.execute('INSERT INTO kolbo_wallets(owner_hash,balance) VALUES(%s,100)',(user,))
    job=store.reserve(user,secrets.token_urlsafe(24),
        hashlib.sha256(b'approved ten second staged prompt').hexdigest(),20)
    slots=planner.plan_exact(10,(4,6,8),people=2)
    assert [x.duration_ms for x in slots]==[6000,4000]
    store.initialize(job.id,user,slots)
    source=tmp_path/'generated'
    clips=[]
    for i,scene in enumerate(slots):
        # A mock provider accepts each scene; the job ID must survive DB
        # reopening, and no new POST is sent during reconciliation.
        engine='agnes_flash' if i==0 else 'independent_gpu_mock'
        store.progress(job.id,user,i,'submitting',provider=engine)
        task='provider_job_'+secrets.token_hex(12)
        store.progress(job.id,user,i,'accepted',task_id=task)
        restarted=stored.SegmentStore(PG)
        same=restarted.list_for_owner(job.id,user)
        assert same[i].task_id==task and same[i].state=='accepted'
        f=synthetic_media(source/f'scene_{i}.mp4',scene.duration_ms//1000,440+i*220)
        clips.append(joiner.SourceClip(i,f,scene.duration_ms))
        actual,has_audio=joiner._probe_audio_video(f)
        assert abs(actual-scene.duration_ms)<=500 and has_audio
        # Media object key is hypothetical, no remote storage in this test.
        store.progress(job.id,user,i,'downloaded',
                       object_key=secrets.token_urlsafe(32))
        store.progress(job.id,user,i,'verified',verified_output=True)
    assembled=joiner.join(source,clips,tmp_path/'output',
                 require_audio=True,output_basename='staged-10s.mp4',
                 size=(320,180))
    assert abs(assembled.measured_ms-10000)<=500
    assert assembled.audio_present and assembled.clip_count==2
    segments=[
      guard.SegmentResult(scene.index,scene.start_ms,scene.end_ms,
        scene.duration_ms,True,True,
        source_identities_reviewed=False,lips_and_language_reviewed=False,
        continuity_with_previous_reviewed=False,
        signed_render_receipt=True) for scene in slots
    ]
    request=guard.VideoRequest(seconds=10,distinct_people=2,needs_audio=True,
       needs_lip_sync=True,requires_consistent_people=True,
       quality_preset='premium',max_authorized_spend_usd=D('0'),
       explicit_image_consent=True,commercial_use=False)
    report=guard.assess_output(request,segments)
    assert report.verdict is guard.PublishVerdict.NEEDS_REVIEW
    assert 'character_identity_unverified' in report.warnings
    assert 'lip_sync_or_language_unverified' in report.warnings
    assert 'cross_scene_continuity_unverified' in report.warnings
    assert store.balance(user)==80  # reserved for review; no refund duplication
