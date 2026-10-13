"""Isolated SQLite contract tests: no provider, API, user photo or billing."""
import hashlib
import os
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
import pytest

from free_gpu_journal import FreeGpuJournal, Conflict, JournalError, InvalidTransition, QuotaExceeded

OWNER = "a" * 64
OTHER = "b" * 64
KEY = "1" * 64
DIGEST = "2" * 64

@pytest.fixture
def journal(tmp_path):
    root=tmp_path/"private"
    root.mkdir(mode=0o700)
    path=root/"jobs.sqlite3"
    return FreeGpuJournal(path)

def test_first_submission_unique_across_reopen(journal):
    one=journal.reserve(OWNER,KEY,DIGEST)
    assert one.created_new and one.state=="prepared"
    again=FreeGpuJournal(journal.path).reserve(OWNER,KEY,DIGEST)
    assert not again.created_new and again.job_id==one.job_id
    assert len(journal.unresolved())==1

def test_same_key_other_payload_fails_closed(journal):
    journal.reserve(OWNER,KEY,DIGEST)
    with pytest.raises(Conflict):
        journal.reserve(OWNER,KEY,"c"*64)

def test_restart_after_submission_never_becomes_new_job(journal):
    job=journal.reserve(OWNER,KEY,DIGEST)
    sending=journal.change(job.job_id,OWNER,"submitting",provider="wan_fast")
    assert sending.state=="submitting"
    restarted=FreeGpuJournal(journal.path)
    assert restarted.get(job.job_id,OWNER).state=="submitting"
    replay=restarted.reserve(OWNER,KEY,DIGEST)
    assert not replay.created_new
    assert replay.state=="submitting"
    with pytest.raises(InvalidTransition):
        restarted.change(job.job_id,OWNER,"submitting",provider="wan_fast")
    with pytest.raises(InvalidTransition):
        restarted.change(job.job_id,OWNER,"completed",verified_media_digest="c"*64)

def test_timeout_is_unknown_and_blocks_resubmission(journal):
    job=journal.reserve(OWNER,KEY,DIGEST)
    journal.change(job.job_id,OWNER,"submitting",provider="wan_fast")
    journal.change(job.job_id,OWNER,"acceptance_unknown")
    with pytest.raises(InvalidTransition):
        journal.change(job.job_id,OWNER,"submitting",provider="second_gpu")
    with pytest.raises(InvalidTransition):
        journal.change(job.job_id,OWNER,"failed_unverified")
    assert journal.get(job.job_id,OWNER).state=="acceptance_unknown"

def test_accepted_job_must_validate_and_supply_digest(journal):
    job=journal.reserve(OWNER,KEY,DIGEST)
    journal.change(job.job_id,OWNER,"submitting",provider="wan_fast")
    journal.change(job.job_id,OWNER,"accepted",provider_task_id="remote_task_111")
    journal.change(job.job_id,OWNER,"validating")
    with pytest.raises(InvalidTransition):
        journal.change(job.job_id,OWNER,"completed")
    end=journal.change(job.job_id,OWNER,"completed",verified_media_digest="d"*64)
    assert end.state=="completed" and end.media_sha256=="d"*64
    assert not FreeGpuJournal(journal.path).unresolved()
    with pytest.raises(InvalidTransition):
        journal.change(job.job_id,OWNER,"submitting",provider="wan_fast")

def test_owner_scoped_and_no_raw_personal_media_storage(journal):
    job=journal.reserve(OWNER,KEY,DIGEST)
    with pytest.raises(JournalError):
        journal.get(job.job_id,OTHER)
    with pytest.raises(JournalError):
        journal.change(job.job_id,OTHER,"submitting",provider="wan_fast")
    with sqlite3.connect(journal.path) as c:
        schema=[x[1] for x in c.execute("PRAGMA table_info(free_gpu_jobs)")]
        assert "prompt" not in schema
        assert "image" not in schema
        assert "access_token" not in schema
        assert "email" not in schema

def test_parallel_request_reserves_only_one_id(journal):
    def reserve(i):
        worker=FreeGpuJournal(journal.path)
        return worker.reserve(OWNER,KEY,DIGEST)
    with ThreadPoolExecutor(max_workers=5) as pool:
        ids=list(pool.map(reserve, range(10)))
    assert len({r.job_id for r in ids})==1
    assert sum(r.created_new for r in ids)==1

def test_private_directory_and_symlinks_are_mandatory(tmp_path):
    root=tmp_path/"unsafe";root.mkdir()
    root.chmod(0o755)
    with pytest.raises(JournalError):
        FreeGpuJournal(root/"job.sqlite3")
    root.chmod(0o700)
    real=root/"actual.sqlite3"
    FreeGpuJournal(real)
    link=root/"fake.sqlite3"
    link.symlink_to(real)
    with pytest.raises(JournalError):
        FreeGpuJournal(link)

def test_invalid_ids_not_executed_or_accepted(journal):
    with pytest.raises(JournalError):
        journal.reserve(OWNER,"prompt-and-image-text",DIGEST)
    one=journal.reserve(OWNER,KEY,DIGEST)
    with pytest.raises(JournalError):
        journal.get("../../etc/passwd",OWNER)
    with pytest.raises(InvalidTransition):
        journal.change(one.job_id,OWNER,"submitting",provider="http://other-site")
    assert journal.get(one.job_id,OWNER).state=="prepared"

def test_rejection_before_submit_is_terminal(journal):
    r=journal.reserve(OWNER,KEY,DIGEST)
    journal.change(r.job_id,OWNER,"rejected_before_submission")
    repeat=journal.reserve(OWNER,KEY,DIGEST)
    assert repeat.state=="rejected_before_submission" and not repeat.created_new
    with pytest.raises(InvalidTransition):
        journal.change(r.job_id,OWNER,"submitting",provider="wan_fast")

def test_persistent_daily_cap_survives_restart(journal):
    first=journal.reserve(OWNER,KEY,DIGEST,max_daily_owner=1,max_daily_global=2)
    assert first.created_new
    again=FreeGpuJournal(journal.path).reserve(OWNER,KEY,DIGEST,max_daily_owner=1,max_daily_global=2)
    assert not again.created_new and again.job_id==first.job_id
    with pytest.raises(QuotaExceeded):
        journal.reserve(OWNER,"3"*64,"4"*64,max_daily_owner=1,max_daily_global=2)
    other=FreeGpuJournal(journal.path).reserve(OTHER,"5"*64,"6"*64,
        max_daily_owner=1,max_daily_global=2)
    assert other.created_new
    with pytest.raises(QuotaExceeded):
        journal.reserve("c"*64,"7"*64,"8"*64,max_daily_owner=1,max_daily_global=2)
