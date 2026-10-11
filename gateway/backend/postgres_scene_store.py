"""PostgreSQL scene journal: per-scene task IDs and crash reconciliation.

STAGING ONLY. No live provider calls, public storage, real wallet grants,
or user-media persistence. Must be invoked solely by an authenticated server
after an independent provider/identity/price capability check.
"""
from __future__ import annotations
from dataclasses import dataclass
from uuid import UUID
import re
import postgres_job_store as base
import scene_planner

SCHEMA="""
CREATE TABLE IF NOT EXISTS kolbo_generation_segments (
 job_id UUID NOT NULL REFERENCES kolbo_generation_jobs(job_id),
 segment_index INTEGER NOT NULL CHECK(segment_index BETWEEN 0 AND 23),
 owner_hash TEXT NOT NULL CHECK(length(owner_hash)=64),
 start_ms INTEGER NOT NULL CHECK(start_ms >= 0),
 end_ms INTEGER NOT NULL CHECK(end_ms > start_ms),
 subject_count SMALLINT NOT NULL CHECK(subject_count BETWEEN 0 AND 2),
 previous_index INTEGER,
 state TEXT NOT NULL CHECK(state IN
   ('planned','submitting','unknown_acceptance','accepted','downloaded','verified','review_required','failed')),
 provider_name TEXT,
 provider_task_id TEXT,
 object_key TEXT,
 updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 PRIMARY KEY(job_id,segment_index),
 UNIQUE(provider_name,provider_task_id)
);
CREATE INDEX IF NOT EXISTS kolbo_segments_unresolved_idx
  ON kolbo_generation_segments(state,updated_at);
"""

NAME=re.compile(r'^[a-z0-9_-]{3,64}$')
TASK=re.compile(r'^[A-Za-z0-9_-]{4,150}$')
OBJECT=re.compile(r'^[A-Za-z0-9_-]{24,160}$')

class SegmentError(base.StoreError):pass

@dataclass(frozen=True)
class SegmentReceipt:
    job_id:str
    index:int
    start_ms:int
    end_ms:int
    people:int
    state:str
    provider:str|None
    task_id:str|None
    object_key:str|None

def parse(row)->SegmentReceipt:
    return SegmentReceipt(str(row[0]),int(row[1]),int(row[2]),int(row[3]),
        int(row[4]),row[5],row[6],row[7],row[8])

_COLUMNS="""job_id,segment_index,start_ms,end_ms,subject_count,state,
           provider_name,provider_task_id,object_key"""

class SegmentStore(base.PostgresJobStore):
    def bootstrap_segments(self):
        self.bootstrap()
        with self._open() as db:db.execute(SCHEMA)

    def _job_owner(self,db,job_id:str,owner_hash:str):
        try:UUID(job_id)
        except (ValueError,TypeError) as e:raise SegmentError('Unknown job') from e
        base._input(owner_hash=owner_hash)
        row=db.execute(
           'SELECT state FROM kolbo_generation_jobs WHERE job_id=%s AND owner_hash=%s FOR UPDATE',
            (job_id,owner_hash)).fetchone()
        if row is None:raise SegmentError('Unknown job or owner')
        return row[0]

    def initialize(self,job_id:str,owner_hash:str,
                   scenes:tuple[scene_planner.PlannedScene,...])->tuple[SegmentReceipt,...]:
        if not scenes or len(scenes)>24:
            raise SegmentError('Invalid scene count')
        if [s.index for s in scenes]!=list(range(len(scenes))):
            raise SegmentError('Scenes must be contiguous and ordered')
        if scenes[0].start_ms!=0:
            raise SegmentError('First scene must start at zero')
        for i,s in enumerate(scenes):
            if not 0<=s.identity_slots<=2 or s.end_ms<=s.start_ms or s.duration_ms!=s.end_ms-s.start_ms:
                raise SegmentError('Invalid scene timing or identity slots')
            if i and s.start_ms!=scenes[i-1].end_ms:
                raise SegmentError('Gap or overlap in requested scenes')
            if s.previous_scene_index!=(i-1 if i else None):
                raise SegmentError('Missing continuity predecessor')
        with self._open() as db:
            state=self._job_owner(db,job_id,owner_hash)
            if state not in ('reserved','submitting','unknown_acceptance','accepted','validating'):
                raise SegmentError('Job cannot initialize scenes in a final state')
            rows=db.execute(
                f'SELECT {_COLUMNS} FROM kolbo_generation_segments WHERE job_id=%s ORDER BY segment_index',
                (job_id,)).fetchall()
            if rows:
                if len(rows)!=len(scenes) or any(
                    existing[1]!=planned.index or existing[2]!=planned.start_ms or
                    existing[3]!=planned.end_ms or existing[4]!=planned.identity_slots
                    for existing,planned in zip(rows,scenes)):
                    raise SegmentError('Scene plan differs for existing job')
                return tuple(parse(row) for row in rows)
            for scene in scenes:
                db.execute("""INSERT INTO kolbo_generation_segments
                    (job_id,segment_index,owner_hash,start_ms,end_ms,subject_count,
                     previous_index,state)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,'planned')""",
                    (job_id,scene.index,owner_hash,scene.start_ms,scene.end_ms,
                     scene.identity_slots,scene.previous_scene_index))
            rows=db.execute(f'SELECT {_COLUMNS} FROM kolbo_generation_segments WHERE job_id=%s ORDER BY segment_index',
                            (job_id,)).fetchall()
            return tuple(parse(row) for row in rows)

    def list_for_owner(self,job_id:str,owner_hash:str)->tuple[SegmentReceipt,...]:
        base._input(owner_hash=owner_hash)
        try:UUID(job_id)
        except (ValueError,TypeError) as e:raise SegmentError('Unknown job') from e
        with self._open() as db:
            rows=db.execute(f'''SELECT {_COLUMNS} FROM kolbo_generation_segments
                WHERE job_id=%s AND owner_hash=%s ORDER BY segment_index''',
                (job_id,owner_hash)).fetchall()
            if not rows:raise SegmentError('No visible scenes')
            return tuple(parse(r) for r in rows)

    def progress(self,job_id:str,owner_hash:str,index:int,new_state:str,
                 *,provider:str|None=None,task_id:str|None=None,
                 object_key:str|None=None,verified_rejection:bool=False,
                 verified_output:bool=False)->SegmentReceipt:
        if type(index)is not int or not 0<=index<=23:raise SegmentError('Invalid scene index')
        if provider is not None and not NAME.fullmatch(provider):
            raise SegmentError('Invalid provider')
        if task_id is not None and not TASK.fullmatch(task_id):
            raise SegmentError('Invalid provider task')
        if object_key is not None and not OBJECT.fullmatch(object_key):
            raise SegmentError('Invalid private object key')
        if new_state not in ('planned','submitting','unknown_acceptance','accepted',
                             'downloaded','verified','review_required','failed'):
            raise SegmentError('Unknown segment status')
        allowed={
         'planned':('submitting',),
         'submitting':('planned','unknown_acceptance','accepted'),
         'unknown_acceptance':('planned','accepted'),
         'accepted':('downloaded','failed'),
         'downloaded':('verified','review_required','failed'),
         'review_required':('verified','failed'),
         'verified':(),
         'failed':(),
        }
        with self._open() as db:
            parent_state=self._job_owner(db,job_id,owner_hash)
            if parent_state in ('completed','failed_refunded'):
                raise SegmentError('Job already finalized')
            row=db.execute(f'''SELECT {_COLUMNS} FROM kolbo_generation_segments
                 WHERE job_id=%s AND segment_index=%s AND owner_hash=%s FOR UPDATE''',
                 (job_id,index,owner_hash)).fetchone()
            if not row:raise SegmentError('Scene not found or not owned')
            old=parse(row)
            if new_state==old.state and provider in (None,old.provider) and task_id in (None,old.task_id) and object_key in (None,old.object_key):
                return old
            if new_state not in allowed[old.state]:
                raise SegmentError('Unsafe scene transition')
            selected,task,artifact=old.provider,old.task_id,old.object_key
            if new_state=='submitting':
                if not provider or task_id or object_key:
                    raise SegmentError('Record provider before request')
                # Do not start the next scene while an earlier scene is uncertain:
                # continuity depends on the prior output.
                if index:
                    prev=db.execute('''SELECT state FROM kolbo_generation_segments
                       WHERE job_id=%s AND segment_index=%s''',(job_id,index-1)).fetchone()
                    if not prev or prev[0]!='verified':
                        raise SegmentError('Prior scene not yet verified')
                selected=provider
            elif new_state=='planned':
                if not verified_rejection or task:
                    raise SegmentError('Cannot retry potentially accepted task')
                selected=None
            elif new_state=='accepted':
                if not task_id or object_key or not selected:
                    raise SegmentError('Provider task ID required')
                task=task_id
            elif new_state=='downloaded':
                if not object_key or not task:
                    raise SegmentError('Must store private media reference after accepted provider task')
                artifact=object_key
            elif new_state=='verified':
                if not verified_output or not artifact:
                    raise SegmentError('Verified output and stored media required')
            elif provider is not None or task_id is not None or object_key is not None:
                raise SegmentError('Unexpected provider/task/object modification')
            updated=db.execute(f'''UPDATE kolbo_generation_segments SET
                state=%s, provider_name=%s, provider_task_id=%s,object_key=%s,
                updated_at=now()
                WHERE job_id=%s AND segment_index=%s AND owner_hash=%s
                RETURNING {_COLUMNS}''',
                (new_state,selected,task,artifact,job_id,index,owner_hash)).fetchone()
            return parse(updated)
