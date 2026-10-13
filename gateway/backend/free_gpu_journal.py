"""Crash-conservative local job journal for *experimental free* GPU submissions.

SQLite needs a genuinely persistent private volume to survive deploy/restarts.
No image, prompt, token, audio, user identity, URL or paid credit is stored.
A committed 'submitting' record is never automatically retried: acceptance may
be unknown even after a network timeout. This is a journal, NOT a GPU worker.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import re
import sqlite3
import stat
import uuid

HEX = re.compile(r"^[0-9a-f]{64}$")
UUID = re.compile(r"^[0-9a-f-]{36}$")
TASK = re.compile(r"^[A-Za-z0-9_-]{4,150}$")
STATES = {"prepared", "submitting", "acceptance_unknown", "accepted",
          "validating", "completed", "rejected_before_submission", "failed_unverified"}

class JournalError(RuntimeError): pass
class Conflict(JournalError): pass
class InvalidTransition(JournalError): pass

SCHEMA = """
CREATE TABLE IF NOT EXISTS free_gpu_jobs(
    job_id TEXT PRIMARY KEY,
    owner_hash TEXT NOT NULL,
    idem_key TEXT NOT NULL,
    spec_digest TEXT NOT NULL,
    state TEXT NOT NULL,
    provider TEXT,
    provider_task_id TEXT,
    media_sha256 TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(owner_hash, idem_key)
);
CREATE INDEX IF NOT EXISTS free_gpu_jobs_state_idx ON free_gpu_jobs(state);
"""

@dataclass(frozen=True)
class Receipt:
    job_id: str
    state: str
    created_new: bool
    provider: str | None = None
    provider_task_id: str | None = None
    media_sha256: str | None = None

def _is_hex(value: str) -> bool:
    return isinstance(value,str) and HEX.fullmatch(value) is not None

class FreeGpuJournal:
    def __init__(self, path: str | Path):
        path = Path(path)
        if not path.is_absolute() or path.suffix != ".sqlite3":
            raise JournalError("Private absolute SQLite path required")
        if path.parent.is_symlink() or not path.parent.is_dir():
            raise JournalError("Parent must be an existing private directory")
        if path.parent.stat().st_mode & 0o077:
            raise JournalError("Journal directory must be accessible only to owner")
        if path.is_symlink():
            raise JournalError("Refuse symlink database")
        if path.exists() and (not path.is_file() or path.stat().st_mode & 0o077):
            raise JournalError("Database must be a private regular file")
        self.path = path
        self._bootstrap()

    def _connect(self):
        if self.path.is_symlink():
            raise JournalError("Database path changed to symlink")
        conn = sqlite3.connect(str(self.path), timeout=10, isolation_level=None)
        conn.execute("PRAGMA busy_timeout=10000")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=FULL")
        conn.row_factory=sqlite3.Row
        return conn

    def _bootstrap(self):
        conn = self._connect()
        try:
            os.chmod(self.path, 0o600)
            conn.executescript(SCHEMA)
        finally:
            conn.close()

    @staticmethod
    def _receipt(row, fresh=False):
        return Receipt(row["job_id"],row["state"],fresh,row["provider"],
                       row["provider_task_id"],row["media_sha256"])

    @staticmethod
    def _id(value):
        if not isinstance(value,str) or not UUID.fullmatch(value):
            raise JournalError("Invalid job identifier")
        try:
            if str(uuid.UUID(value)) != value: raise ValueError()
        except ValueError as exc:
            raise JournalError("Invalid job UUID") from exc

    def reserve(self, owner: str, key: str, spec_digest: str) -> Receipt:
        if not all(_is_hex(value) for value in (owner,key,spec_digest)):
            raise JournalError("Owner, key and digest must be opaque SHA256 strings")
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row=conn.execute("SELECT * FROM free_gpu_jobs WHERE owner_hash=? AND idem_key=?",
                             (owner,key)).fetchone()
            if row:
                if row["spec_digest"] != spec_digest:
                    raise Conflict("An existing idempotency key has different terms")
                return self._receipt(row)
            job_id=str(uuid.uuid4())
            conn.execute("INSERT INTO free_gpu_jobs "
                         "(job_id,owner_hash,idem_key,spec_digest,state) "
                         "VALUES(?,?,?,?,'prepared')",(job_id,owner,key,spec_digest))
            row=conn.execute("SELECT * FROM free_gpu_jobs WHERE job_id=?",(job_id,)).fetchone()
            return self._receipt(row,True)

    def get(self, job_id: str, owner: str) -> Receipt:
        self._id(job_id)
        if not _is_hex(owner): raise JournalError("Invalid owner")
        with self._connect() as conn:
            row=conn.execute("SELECT * FROM free_gpu_jobs "
                             "WHERE job_id=? AND owner_hash=?",(job_id,owner)).fetchone()
            if row is None:raise JournalError("Unknown job or unauthorized owner")
            return self._receipt(row)

    def change(self, job_id: str, owner: str, target: str, *,
               provider: str | None = None, provider_task_id: str | None = None,
               verified_media_digest: str | None = None,
               explicit_provider_rejection: bool = False) -> Receipt:
        self._id(job_id)
        if not _is_hex(owner):raise JournalError("Invalid owner")
        allowed = {
            "prepared":{"submitting","rejected_before_submission"},
            "submitting":{"acceptance_unknown","accepted","failed_unverified"},
            "acceptance_unknown":{"accepted","failed_unverified"},
            "accepted":{"validating","failed_unverified"},
            "validating":{"completed","failed_unverified"},
            "completed":set(),
            "rejected_before_submission":set(),
            "failed_unverified":set()
        }
        if target not in STATES:raise InvalidTransition("Invalid target state")
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row=conn.execute("SELECT * FROM free_gpu_jobs WHERE job_id=? AND owner_hash=?",
                             (job_id,owner)).fetchone()
            if row is None:raise JournalError("Unknown job or unauthorized owner")
            if target == row["state"]:
                if provider is None and provider_task_id is None and verified_media_digest is None:
                    return self._receipt(row)
                raise InvalidTransition("Repeated transition with new evidence")
            if target not in allowed[row["state"]]:
                raise InvalidTransition("Illegal transition; never silently resubmit")
            current_provider=row["provider"]
            current_task=row["provider_task_id"]
            current_media=row["media_sha256"]
            if target=="submitting":
                if not isinstance(provider,str) or not re.fullmatch(r"[a-z][a-z0-9_-]{2,63}",provider):
                    raise InvalidTransition("Verified provider name required before submission")
                current_provider=provider
            elif provider is not None:
                raise InvalidTransition("Provider can only be set before submission")
            if target=="accepted":
                if not isinstance(provider_task_id,str) or not TASK.fullmatch(provider_task_id):
                    raise InvalidTransition("Provider task ID required")
                current_task=provider_task_id
            elif provider_task_id is not None:
                raise InvalidTransition("Task ID only allowed at acceptance")
            if target=="completed":
                if not _is_hex(verified_media_digest):
                    raise InvalidTransition("Verified media SHA256 required")
                current_media=verified_media_digest
            elif verified_media_digest is not None:
                raise InvalidTransition("Media proof only allowed at completion")
            if target=="failed_unverified" and row["state"] in ("submitting","acceptance_unknown"):
                if not explicit_provider_rejection:
                    raise InvalidTransition("Unknown accepted GPU request cannot be marked safe to retry")
            conn.execute("UPDATE free_gpu_jobs SET state=?,provider=?,provider_task_id=?,"
                         "media_sha256=?,updated_at=CURRENT_TIMESTAMP WHERE job_id=? AND owner_hash=?",
                         (target,current_provider,current_task,current_media,job_id,owner))
            return self._receipt(conn.execute("SELECT * FROM free_gpu_jobs WHERE job_id=?",
                                              (job_id,)).fetchone())

    def unresolved(self) -> list[Receipt]:
        """Operator-only call, never expose an unscoped list to mobile/guests."""
        with self._connect() as conn:
            rows=conn.execute("SELECT * FROM free_gpu_jobs WHERE state NOT IN "
                "('completed','rejected_before_submission','failed_unverified') "
                "ORDER BY created_at LIMIT 100").fetchall()
            return [self._receipt(row) for row in rows]
