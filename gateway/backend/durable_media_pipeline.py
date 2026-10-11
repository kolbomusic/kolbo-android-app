"""Staging integration for Postgres job receipts, private S3 and FFmpeg output.

Only invoke from a trusted server worker after authenticating the owner. An
artifact must be saved to object storage and durably indexed before a job may
be marked complete. This module cannot submit jobs to AI providers or sell
credits; it is not wired to live Render.
"""
from __future__ import annotations
import hashlib
from pathlib import Path
import psycopg
import postgres_media_index as artifacts
import postgres_job_store as jobs
import private_media_store as objects
import scene_assembler as assembly

class PipelineError(RuntimeError):pass

def _checksum(file:Path)->str:
    digest=hashlib.sha256()
    with Path(file).open('rb') as src:
        while piece:=src.read(1024*1024):digest.update(piece)
    return digest.hexdigest()

class DurableMediaPipeline:
    def __init__(self,store:jobs.PostgresJobStore,
                 index:artifacts.PostgresArtifactIndex,
                 bucket:objects.PrivateObjectStore):
        self.store=store
        self.index=index
        self.bucket=bucket

    def _job(self,owner_hash:str,job_id:str,allowed:tuple[str,...]):
        receipt=self.store.get(job_id,owner_hash)
        if receipt.state not in allowed:
            raise PipelineError('Generation job is not in the required processing state')
        return receipt

    def upload_scene(self,*,owner_hash:str,job_id:str,index:int,
                     file:Path,expected_ms:int,
                     require_audio:bool)->artifacts.Artifact:
        self._job(owner_hash,job_id,('accepted','validating'))
        if type(index)is not int or not 0<=index<=99:
            raise PipelineError('Invalid scene index')
        duration,has_audio=assembly._probe_audio_video(Path(file))
        if type(expected_ms)is not int or not 100<=expected_ms<=120000:
            raise PipelineError('Invalid expected scene duration')
        if abs(duration-expected_ms)>500:
            raise PipelineError('Generated scene is shorter or longer than requested')
        if require_audio and not has_audio:
            raise PipelineError('Missing required sound in generated scene')
        existing=self.index.find_position(job_id=job_id,owner_hash=owner_hash,
                                         role='scene',sequence_no=index)
        if existing:
            if existing.sha256!=_checksum(file):
                raise artifacts.ArtifactConflict('Cannot replace original committed scene')
            current=self.bucket.head(owner_hash,job_id,existing.object_key,'scene')
            if current.sha256!=existing.sha256:
                raise PipelineError('Indexed scene checksum does not match object storage')
            return existing
        saved=self.bucket.put(owner_hash,job_id,'scene',Path(file),'video/mp4')
        try:
            return self.index.attach(job_id=job_id,owner_hash=owner_hash,
               role='scene',sequence_no=index,object_key=saved.key,
               sha256=saved.sha256,media_type=saved.media_type,
               byte_size=saved.size,expires_at=saved.expires_at)
        except Exception:
            # If DB insertion failed, remove the orphaned S3 object.
            try:self.bucket.delete(owner_hash,job_id,saved.key,'scene')
            except Exception:pass
            raise

    def restore_scene(self,*,owner_hash:str,job_id:str,index:int,
                      destination_directory:Path)->Path:
        self._job(owner_hash,job_id,('accepted','validating'))
        record=self.index.find_position(job_id=job_id,owner_hash=owner_hash,
                                        role='scene',sequence_no=index)
        if record is None:raise PipelineError('Scene is not durably recorded')
        stored=self.bucket.head(owner_hash,job_id,record.object_key,'scene')
        if (stored.sha256!=record.sha256 or stored.size!=record.byte_size):
            raise PipelineError('Durable index differs from object bytes')
        return self.bucket.restore_to_local(owner_hash,job_id,
               record.object_key,'scene',destination_directory,
               f'scene_{index:03d}.mp4')

    def save_final_draft(self,*,owner_hash:str,job_id:str,
                         file:Path,expected_ms:int,
                         require_audio:bool)->artifacts.Artifact:
        # After the output is durably saved, a SEPARATE trusted QA reviewer
        # must check actual identities, singing and lips before 'completed'.
        self._job(owner_hash,job_id,('validating',))
        actual,has_audio=assembly._probe_audio_video(Path(file))
        if abs(actual-expected_ms)>500:
            raise PipelineError('Final output duration mismatches request')
        if require_audio and not has_audio:
            raise PipelineError('Final output has no audio')
        prior=self.index.find_position(job_id=job_id,owner_hash=owner_hash,
                                       role='output',sequence_no=0)
        if prior:
            if prior.sha256!=_checksum(file):
                raise artifacts.ArtifactConflict('Cannot overwrite output awaiting review')
            return prior
        saved=self.bucket.put(owner_hash,job_id,'output',Path(file),'video/mp4')
        try:
            return self.index.attach(job_id=job_id,owner_hash=owner_hash,
               role='output',sequence_no=0,object_key=saved.key,
               sha256=saved.sha256,media_type=saved.media_type,
               byte_size=saved.size,expires_at=saved.expires_at)
        except Exception:
            try:self.bucket.delete(owner_hash,job_id,saved.key,'output')
            except Exception:pass
            raise

    def final_download_url(self,*,owner_hash:str,job_id:str,
                           expires_seconds:int=300)->str:
        # SQL join explicitly verifies owner AND completed generation job.
        record=self.index.output_for_owner(job_id=job_id,owner_hash=owner_hash)
        stored=self.bucket.head(owner_hash,job_id,record.object_key,'output')
        if (stored.sha256!=record.sha256 or stored.size!=record.byte_size):
            raise PipelineError('Final media not verified in private storage')
        return self.bucket.private_download_url(owner_hash,job_id,
               record.object_key,'output',expires_seconds=expires_seconds)
