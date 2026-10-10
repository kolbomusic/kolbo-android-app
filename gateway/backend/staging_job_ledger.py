"""Staged transactional job/credit ledger using SQLite for isolated testing.

NOT automatically enabled in production. SQLite requires a persistent owned
volume, backups and a single-writer topology; Render Free's ephemeral FS cannot
provide durable state. Before paid launch, migrate the same transaction contract
to managed PostgreSQL and atomically verify Play purchases/AdMob receipts.
Only server-side verified wallet identities should be passed into this module.
"""
from __future__ import annotations
from contextlib import contextmanager
import re,sqlite3,threading,uuid
from dataclasses import dataclass

class LedgerError(RuntimeError): pass
class NoCredits(LedgerError): pass
class IdempotencyConflict(LedgerError): pass
class InvalidTransition(LedgerError): pass

_DIGEST=re.compile(r'[0-9a-f]{64}')
_IDEM=re.compile(r'[A-Za-z0-9_-]{24,128}')
_OWNER=re.compile(r'[0-9a-f]{64}')

SCHEMA="""
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS wallets (
  owner_hash TEXT PRIMARY KEY CHECK(length(owner_hash)=64),
  balance INTEGER NOT NULL CHECK(balance>=0)
);
CREATE TABLE IF NOT EXISTS generation_jobs (
  job_id TEXT PRIMARY KEY,
  owner_hash TEXT NOT NULL REFERENCES wallets(owner_hash),
  idempotency_key TEXT NOT NULL,
  spec_digest TEXT NOT NULL,
  state TEXT NOT NULL CHECK(state IN
    ('reserved','submitting','accepted','unknown_acceptance',
     'validating','completed','failed_refunded')),
  held_credits INTEGER NOT NULL CHECK(held_credits>=0),
  provider_task_id TEXT UNIQUE,
  UNIQUE(owner_hash,idempotency_key)
);
"""

@dataclass(frozen=True)
class JobView:
    id:str
    state:str
    reserved_points:int
    provider_task_id:str|None
    created_new:bool

_TRANSITIONS={
    'reserved':frozenset(('submitting','failed_refunded')),
    'submitting':frozenset(('accepted','unknown_acceptance','reserved',
                            'failed_refunded')),
    'unknown_acceptance':frozenset(('accepted','reserved')),
    'accepted':frozenset(('validating','failed_refunded')),
    'validating':frozenset(('completed','failed_refunded')),
    'completed':frozenset(),
    'failed_refunded':frozenset()
}

class StagingLedger:
    """Test-only local ACID model. No production-ready payment integration."""
    def __init__(self,connection:sqlite3.Connection):
        self.db=connection
        self.lock=threading.RLock()
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.executescript(SCHEMA)

    @contextmanager
    def _transaction(self):
        with self.lock:
            self.db.execute('BEGIN IMMEDIATE')
            try:
                yield
                self.db.commit()
            except BaseException:
                self.db.rollback()
                raise

    def balance(self,owner_hash:str)->int:
        with self.lock:
            row=self.db.execute(
                'SELECT balance FROM wallets WHERE owner_hash=?',
                (owner_hash,)).fetchone()
            if row is None:raise LedgerError('Unknown server-verified wallet')
            return row[0]

    def _view(self,row,*,is_new=False)->JobView:
        return JobView(row[0],row[1],row[2],row[3],is_new)

    def reserve(self,owner_hash:str,idempotency_key:str,spec_digest:str,
                credit_points:int)->JobView:
        if not _OWNER.fullmatch(owner_hash) or not _IDEM.fullmatch(idempotency_key):
            raise LedgerError('Invalid verified-owner or request identifier')
        if not _DIGEST.fullmatch(spec_digest):
            raise LedgerError('Invalid canonical request digest')
        if type(credit_points) is not int or not 0<=credit_points<=1000000:
            raise LedgerError('Invalid credit amount')
        with self._transaction():
            row=self.db.execute(
                '''SELECT job_id,state,held_credits,provider_task_id,spec_digest
                   FROM generation_jobs
                   WHERE owner_hash=? AND idempotency_key=?''',
                (owner_hash,idempotency_key)).fetchone()
            if row:
                if row[4]!=spec_digest or row[2]!=credit_points:
                    raise IdempotencyConflict('Idempotency key reused for different terms')
                return self._view(row)
            moved=self.db.execute(
                'UPDATE wallets SET balance=balance-? WHERE owner_hash=? AND balance>=?',
                (credit_points,owner_hash,credit_points))
            if moved.rowcount!=1:raise NoCredits('Insufficient verified credit balance')
            id=str(uuid.uuid4())
            self.db.execute('''INSERT INTO generation_jobs
                (job_id,owner_hash,idempotency_key,spec_digest,state,held_credits)
                VALUES (?,?,?,?,?,?)''',
                (id,owner_hash,idempotency_key,spec_digest,'reserved',credit_points))
            return JobView(id,'reserved',credit_points,None,True)

    def progress(self,job_id:str,state:str,*,provider_task_id:str|None=None,
                 rejection_verified:bool=False,qa_passed:bool=False)->JobView:
        """Never auto-resubmit an unknown submission or publish without QA."""
        with self._transaction():
            row=self.db.execute(
                '''SELECT job_id,state,held_credits,provider_task_id,owner_hash
                   FROM generation_jobs WHERE job_id=?''',(job_id,)).fetchone()
            if not row:raise LedgerError('Unknown job')
            old=row[1]
            if state==old and provider_task_id==row[3]:
                return self._view(row)
            if state not in _TRANSITIONS[old]:
                raise InvalidTransition(old+' -> '+state+' not permitted')
            if old=='unknown_acceptance' and state=='reserved':
                if not rejection_verified:
                    raise InvalidTransition('Provider acceptance must be reconciled first')
            if old=='submitting' and state=='reserved' and not rejection_verified:
                raise InvalidTransition('Explicit provider rejection is required to retry')
            if state=='completed' and not qa_passed:
                raise InvalidTransition('Video output QA evidence required')
            if state=='accepted':
                if not provider_task_id or len(provider_task_id)>150:
                    raise InvalidTransition('Accepted provider task ID is required')
                if row[3] and row[3]!=provider_task_id:
                    raise InvalidTransition('Cannot replace accepted provider task ID')
            elif provider_task_id is not None:
                raise InvalidTransition('Provider task ID only set upon acceptance')
            if state=='failed_refunded' and old=='submitting' and not rejection_verified:
                raise InvalidTransition('Cannot refund/resubmit an ambiguous submission')
            if state=='failed_refunded':
                self.db.execute('UPDATE wallets SET balance=balance+? WHERE owner_hash=?',
                    (row[2],row[4]))
            new_id=provider_task_id if state=='accepted' else row[3]
            self.db.execute('''UPDATE generation_jobs
                SET state=?,provider_task_id=? WHERE job_id=?''',
                (state,new_id,job_id))
            return JobView(job_id,state,row[2],new_id,False)

    def view(self,job_id:str)->JobView:
        with self.lock:
            row=self.db.execute('''SELECT job_id,state,held_credits,provider_task_id
                FROM generation_jobs WHERE job_id=?''',(job_id,)).fetchone()
            if not row:raise LedgerError('Unknown job')
            return self._view(row)

    def view_for_owner(self,owner_hash:str,job_id:str)->JobView:
        """Read only an owner's own receipt, never an arbitrary guessed job ID."""
        if not _OWNER.fullmatch(owner_hash):
            raise LedgerError('Invalid server-verified owner')
        with self.lock:
            row=self.db.execute('''SELECT job_id,state,held_credits,provider_task_id
                FROM generation_jobs WHERE job_id=? AND owner_hash=?''',
                (job_id,owner_hash)).fetchone()
            if row is None:raise LedgerError('Unknown job or owner')
            return self._view(row)

