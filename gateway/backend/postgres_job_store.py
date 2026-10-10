"""Durable Postgres-backed job/credit transaction contract (STAGING ONLY).

No live credits are issued and no provider jobs are submitted by this module.
Works only when an operator configures an independently managed PostgreSQL
database; Render Free's filesystem is not enough. Store no prompts, images,
provider URLs, secrets or actual customer payment tokens.

A supplier request is marked "submitting" BEFORE network I/O. If the process
dies during submission, operators reconcile with the supplier by querying its
recorded task ID; an unknown task is NEVER submitted again automatically.
"""
from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass
from typing import Literal

import psycopg

class StoreError(RuntimeError):pass
class InsufficientCredits(StoreError):pass
class DuplicateKeyConflict(StoreError):pass
class InvalidState(StoreError):pass

OWNER_RE=re.compile(r"^[a-f0-9]{64}$")
DIGEST_RE=re.compile(r"^[a-f0-9]{64}$")
IDEM_RE=re.compile(r"^[A-Za-z0-9_-]{24,128}$")
PROVIDER_RE=re.compile(r"^[a-z0-9_-]{3,64}$")
TASK_RE=re.compile(r"^[A-Za-z0-9_-]{4,150}$")
STATES=("reserved","submitting","unknown_acceptance","accepted",
        "validating","completed","failed_refunded")

SCHEMA="""
CREATE TABLE IF NOT EXISTS kolbo_wallets (
    owner_hash TEXT PRIMARY KEY CHECK(length(owner_hash)=64),
    balance BIGINT NOT NULL CHECK (balance>=0)
);
CREATE TABLE IF NOT EXISTS kolbo_generation_jobs (
    job_id UUID PRIMARY KEY,
    owner_hash TEXT NOT NULL REFERENCES kolbo_wallets(owner_hash),
    idempotency_key TEXT NOT NULL,
    spec_digest TEXT NOT NULL,
    state TEXT NOT NULL CHECK(state IN (
        'reserved','submitting','unknown_acceptance','accepted',
        'validating','completed','failed_refunded')),
    held_credits BIGINT NOT NULL CHECK(held_credits>=0),
    provider_name TEXT,
    provider_task_id TEXT UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(owner_hash,idempotency_key)
);
CREATE INDEX IF NOT EXISTS kolbo_jobs_owner_state_idx
    ON kolbo_generation_jobs(owner_hash,state);
"""

@dataclass(frozen=True)
class JobReceipt:
    id:str
    owner_hash:str
    state:str
    held_credits:int
    provider_name:str|None
    provider_task_id:str|None
    created_new:bool=False

def _input(owner_hash:str|None=None,key:str|None=None,
           digest:str|None=None,points:int|None=None):
    if owner_hash is not None and not OWNER_RE.fullmatch(owner_hash):
        raise StoreError("Invalid server-verified owner")
    if key is not None and not IDEM_RE.fullmatch(key):
        raise StoreError("Invalid request idempotency key")
    if digest is not None and not DIGEST_RE.fullmatch(digest):
        raise StoreError("Invalid canonical request digest")
    if points is not None and (type(points)is not int or not 0<=points<=1000000):
        raise StoreError("Invalid credit amount")

def _parse(row,*,created_new=False)->JobReceipt:
    return JobReceipt(str(row[0]),row[1],row[2],int(row[3]),
                      row[4],row[5],created_new)

class PostgresJobStore:
    """Production-shaped staging component, tested against real PostgreSQL.

    A fresh connection per operation prevents shared-connection races. Bootstrapping
    schema is an explicit operator step. Wallet funding must come from a
    separately verified and atomic payment/ad-credit issuance process.
    """
    def __init__(self,conninfo:str):
        if not conninfo or not conninfo.startswith(("postgres://","postgresql://")):
            raise StoreError("Postgres connection URL required")
        self.conninfo=conninfo

    def _open(self):
        return psycopg.connect(self.conninfo,connect_timeout=5)

    def bootstrap(self):
        with self._open() as connection:
            connection.execute(SCHEMA)

    def balance(self,owner_hash:str)->int:
        _input(owner_hash=owner_hash)
        with self._open() as c:
            row=c.execute("SELECT balance FROM kolbo_wallets WHERE owner_hash=%s",
                         (owner_hash,)).fetchone()
            if row is None:raise StoreError("Unknown verified wallet")
            return int(row[0])

    def reserve(self,owner_hash:str,idempotency_key:str,
                spec_digest:str,credit_points:int)->JobReceipt:
        _input(owner_hash,idempotency_key,spec_digest,credit_points)
        with self._open() as c:
            # Transaction-scoped lock per owner/request. Two simultaneous
            # requests cannot race between checking ID and debiting balance.
            lock_key=owner_hash+":"+idempotency_key
            c.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                      (lock_key,))
            row=c.execute("""
                SELECT job_id,owner_hash,state,held_credits,provider_name,
                       provider_task_id,spec_digest
                  FROM kolbo_generation_jobs
                 WHERE owner_hash=%s AND idempotency_key=%s FOR UPDATE
                """,(owner_hash,idempotency_key)).fetchone()
            if row:
                if row[6]!=spec_digest or int(row[3])!=credit_points:
                    raise DuplicateKeyConflict(
                        "Idempotency key reused with different generation terms")
                return _parse(row)
            wallet=c.execute("""
                UPDATE kolbo_wallets SET balance=balance-%s
                 WHERE owner_hash=%s AND balance>=%s RETURNING balance""",
                (credit_points,owner_hash,credit_points)).fetchone()
            if wallet is None:raise InsufficientCredits("No verified points available")
            id=str(uuid.uuid4())
            row=c.execute("""
                INSERT INTO kolbo_generation_jobs
                  (job_id,owner_hash,idempotency_key,spec_digest,state,held_credits)
                VALUES (%s,%s,%s,%s,'reserved',%s)
                RETURNING job_id,owner_hash,state,held_credits,
                          provider_name,provider_task_id
                """,(id,owner_hash,idempotency_key,spec_digest,credit_points)).fetchone()
            return _parse(row,created_new=True)

    def get(self,job_id:str,owner_hash:str)->JobReceipt:
        _input(owner_hash=owner_hash)
        try:uuid.UUID(job_id)
        except (TypeError,ValueError) as e:raise StoreError("Unknown job") from e
        with self._open() as c:
            row=c.execute("""
                SELECT job_id,owner_hash,state,held_credits,
                       provider_name,provider_task_id
                  FROM kolbo_generation_jobs
                 WHERE job_id=%s AND owner_hash=%s""",
                (job_id,owner_hash)).fetchone()
            if row is None:raise StoreError("Unknown job or unauthorized owner")
            return _parse(row)

    def transition(self,job_id:str,owner_hash:str,new_state:str,
                   *,provider:str|None=None,task_id:str|None=None,
                   verified_rejection:bool=False,
                   verified_output:bool=False)->JobReceipt:
        _input(owner_hash=owner_hash)
        if new_state not in STATES:raise InvalidState("Unknown target state")
        if provider is not None and not PROVIDER_RE.fullmatch(provider):
            raise InvalidState("Invalid provider identifier")
        if task_id is not None and not TASK_RE.fullmatch(task_id):
            raise InvalidState("Invalid provider task ID")
        try:uuid.UUID(job_id)
        except (TypeError,ValueError) as e:raise StoreError("Unknown job") from e
        with self._open() as c:
            row=c.execute("""
                SELECT job_id,owner_hash,state,held_credits,
                       provider_name,provider_task_id
                  FROM kolbo_generation_jobs
                 WHERE job_id=%s AND owner_hash=%s FOR UPDATE
                """,(job_id,owner_hash)).fetchone()
            if row is None:raise StoreError("Unknown job or unauthorized owner")
            old=row[2]
            if old==new_state and provider in (None,row[4]) and task_id in (None,row[5]):
                return _parse(row)  # idempotent state lookup, never a second credit movement
            legal={
               "reserved":{"submitting","failed_refunded"},
               "submitting":{"unknown_acceptance","accepted","reserved","failed_refunded"},
               "unknown_acceptance":{"accepted","reserved"},
               "accepted":{"validating","failed_refunded"},
               "validating":{"completed","failed_refunded"},
               "completed":set(),
               "failed_refunded":set()
            }
            if new_state not in legal[old]:
                raise InvalidState("Invalid state transition")
            selected=row[4]
            accepted=row[5]
            if new_state=="submitting":
                if provider is None or task_id is not None or accepted:
                    raise InvalidState("Provider must be recorded before network submission")
                selected=provider
            elif provider is not None and provider!=selected:
                raise InvalidState("Provider change requires explicit rejection and reset")
            if new_state=="accepted":
                if not task_id or not selected:
                    raise InvalidState("Provider task ID required")
                if accepted and accepted!=task_id:
                    raise InvalidState("Provider task ID cannot change")
                accepted=task_id
            elif task_id is not None:
                raise InvalidState("Task ID is only recorded on provider acceptance")
            if new_state=="reserved":
                if not verified_rejection or accepted:
                    raise InvalidState("Never retry unknown accepted task")
                selected=None
            if new_state=="failed_refunded" and old in ("submitting","reserved"):
                if not verified_rejection:
                    raise InvalidState("Cannot refund uncertain supplier submission")
            if new_state=="completed" and not verified_output:
                raise InvalidState("Output quality verification required")
            if new_state=="failed_refunded":
                c.execute("UPDATE kolbo_wallets SET balance=balance+%s WHERE owner_hash=%s",
                          (row[3],owner_hash))
            updated=c.execute("""
                UPDATE kolbo_generation_jobs
                   SET state=%s,provider_name=%s,provider_task_id=%s,
                       updated_at=now()
                 WHERE job_id=%s AND owner_hash=%s
                RETURNING job_id,owner_hash,state,held_credits,
                          provider_name,provider_task_id
                """,(new_state,selected,accepted,job_id,owner_hash)).fetchone()
            return _parse(updated)

    def unresolved(self)->list[JobReceipt]:
        """Query for operator reconciliation after a crash, no automatic POST."""
        with self._open() as c:
            rows=c.execute("""
                SELECT job_id,owner_hash,state,held_credits,
                       provider_name,provider_task_id
                  FROM kolbo_generation_jobs
                 WHERE state IN ('submitting','unknown_acceptance',
                                 'accepted','validating')
                 ORDER BY created_at LIMIT 100
                """).fetchall()
            return [_parse(r) for r in rows]
