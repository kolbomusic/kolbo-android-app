"""PostgreSQL artifact index for private S3 media (STAGING ONLY).

The index references existing generation_jobs and validates its owner. A
media receipt alone never proves image consent, identity similarity, billing,
video quality or actual S3 object retention. The operator must supply a durable
PostgreSQL cluster and private object bucket before deployment.
"""
from __future__ import annotations
from dataclasses import dataclass
import re,uuid,datetime
import psycopg

_OWNER=re.compile(r'^[a-f0-9]{64}$')
_SHA=re.compile(r'^[a-f0-9]{64}$')
_ROLE=('reference','scene','output')
_TYPE={'reference':('image/jpeg','image/png','image/webp'),
       'scene':('video/mp4',),'output':('video/mp4',)}

SCHEMA="""
CREATE TABLE IF NOT EXISTS kolbo_job_artifacts (
    artifact_id UUID PRIMARY KEY,
    job_id UUID NOT NULL REFERENCES kolbo_generation_jobs(job_id),
    owner_hash TEXT NOT NULL REFERENCES kolbo_wallets(owner_hash),
    role TEXT NOT NULL CHECK(role IN ('reference','scene','output')),
    sequence_no SMALLINT NOT NULL CHECK(sequence_no BETWEEN 0 AND 99),
    object_key TEXT NOT NULL UNIQUE,
    sha256 TEXT NOT NULL CHECK(length(sha256)=64),
    media_type TEXT NOT NULL,
    byte_size BIGINT NOT NULL CHECK(byte_size>0 AND byte_size<=314572800),
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(job_id,role,sequence_no)
);
CREATE INDEX IF NOT EXISTS kolbo_artifacts_expiry_idx
    ON kolbo_job_artifacts(expires_at);
"""

class ArtifactIndexError(RuntimeError):pass
class ForeignArtifact(ArtifactIndexError):pass
class ArtifactConflict(ArtifactIndexError):pass

@dataclass(frozen=True)
class Artifact:
    id:str
    job_id:str
    owner_hash:str
    role:str
    sequence_no:int
    object_key:str
    sha256:str
    media_type:str
    byte_size:int
    expires_at:datetime.datetime

def _row(row):
    return Artifact(str(row[0]),str(row[1]),row[2],row[3],int(row[4]),
                    row[5],row[6],row[7],int(row[8]),row[9])

_COLUMNS=("artifact_id,job_id,owner_hash,role,sequence_no,object_key,"
          "sha256,media_type,byte_size,expires_at")

class PostgresArtifactIndex:
    def __init__(self,conninfo:str):
        if not isinstance(conninfo,str) or not conninfo.startswith(
                ('postgresql://','postgres://')):
            raise ArtifactIndexError('Durable PostgreSQL DSN required')
        self.conninfo=conninfo

    def _connection(self):
        return psycopg.connect(self.conninfo,connect_timeout=5)

    def bootstrap(self):
        with self._connection() as c:c.execute(SCHEMA)

    def attach(self,*,job_id:str,owner_hash:str,role:str,
               sequence_no:int,object_key:str,sha256:str,
               media_type:str,byte_size:int,expires_at:int)->Artifact:
        if not _OWNER.fullmatch(owner_hash):
            raise ForeignArtifact('Invalid server-verified owner')
        try:uuid.UUID(job_id)
        except (TypeError,ValueError) as e:
            raise ArtifactIndexError('Invalid job ID') from e
        if role not in _ROLE or type(sequence_no)is not int or not 0<=sequence_no<=99:
            raise ArtifactIndexError('Invalid media role/scene number')
        if media_type not in _TYPE[role] or not _SHA.fullmatch(sha256):
            raise ArtifactIndexError('Invalid media type or checksum')
        prefix=f'private/{owner_hash}/{job_id}/{role}/'
        if not isinstance(object_key,str) or not object_key.startswith(prefix) or len(object_key)>260:
            raise ArtifactIndexError('Media does not belong to this owner/job')
        if (type(byte_size)is not int or not 64<=byte_size<=314572800 or
            type(expires_at)is not int or not 0<expires_at<4102444800):
            raise ArtifactIndexError('Invalid media size or expiry')
        with self._connection() as c:
            ownership=c.execute(
                'SELECT state FROM kolbo_generation_jobs WHERE job_id=%s AND owner_hash=%s FOR UPDATE',
                (job_id,owner_hash)).fetchone()
            if not ownership:raise ForeignArtifact('Job is not owned by this account')
            # No late changes to media from a completed/refunded job.
            if ownership[0] in ('completed','failed_refunded'):
                raise ArtifactIndexError('Cannot attach media to terminal job')
            existing=c.execute(
                f'SELECT {_COLUMNS} FROM kolbo_job_artifacts '
                'WHERE job_id=%s AND role=%s AND sequence_no=%s FOR UPDATE',
                (job_id,role,sequence_no)).fetchone()
            if existing:
                if (existing[5],existing[6],existing[7],existing[8])!=(
                    object_key,sha256,media_type,byte_size):
                    raise ArtifactConflict('Cannot overwrite a committed scene or output')
                return _row(existing)
            artifact_id=str(uuid.uuid4())
            result=c.execute(
                f'''INSERT INTO kolbo_job_artifacts
                (artifact_id,job_id,owner_hash,role,sequence_no,object_key,
                 sha256,media_type,byte_size,expires_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,to_timestamp(%s))
                RETURNING {_COLUMNS}''',
                (artifact_id,job_id,owner_hash,role,sequence_no,object_key,
                 sha256,media_type,byte_size,expires_at)).fetchone()
            return _row(result)

    def get(self,*,artifact_id:str,job_id:str,owner_hash:str)->Artifact:
        if not _OWNER.fullmatch(owner_hash):
            raise ForeignArtifact('Invalid owner')
        try:uuid.UUID(artifact_id);uuid.UUID(job_id)
        except (TypeError,ValueError) as e:raise ForeignArtifact('Unknown artifact') from e
        with self._connection() as c:
            item=c.execute(
                f'SELECT {_COLUMNS} FROM kolbo_job_artifacts '
                'WHERE artifact_id=%s AND job_id=%s AND owner_hash=%s '
                'AND expires_at>now()',
                (artifact_id,job_id,owner_hash)).fetchone()
            if not item:raise ForeignArtifact('Unknown, expired, or unauthorized artifact')
            return _row(item)

    def output_for_owner(self,*,job_id:str,owner_hash:str)->Artifact:
        if not _OWNER.fullmatch(owner_hash):
            raise ForeignArtifact('Invalid owner')
        with self._connection() as c:
            row=c.execute(
                f'SELECT {_COLUMNS} FROM kolbo_job_artifacts a '
                'JOIN kolbo_generation_jobs j USING(job_id) '
                'WHERE a.job_id=%s AND a.owner_hash=%s AND a.role=%s '
                'AND a.expires_at>now() AND j.state=%s ',
                (job_id,owner_hash,'output','completed')).fetchone()
            if not row:raise ForeignArtifact('No approved final output for owner')
            return _row(row)

    def expired(self,*,limit:int=100)->list[Artifact]:
        if type(limit)is not int or not 1<=limit<=1000:
            raise ArtifactIndexError('Invalid janitor limit')
        with self._connection() as c:
            rows=c.execute(
                f'SELECT {_COLUMNS} FROM kolbo_job_artifacts '
                'WHERE expires_at<=now() ORDER BY expires_at ASC LIMIT %s',
                (limit,)).fetchall()
            return [_row(row) for row in rows]

    def confirm_deleted(self,artifact_id:str)->None:
        """Only invoke AFTER object deletion succeeded. Idempotent cleanup."""
        try:uuid.UUID(artifact_id)
        except (TypeError,ValueError) as e:
            raise ArtifactIndexError('Unknown artifact') from e
        with self._connection() as c:
            c.execute('DELETE FROM kolbo_job_artifacts WHERE artifact_id=%s',
                      (artifact_id,))
