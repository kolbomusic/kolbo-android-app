"""Private S3-compatible object storage for Kolbo Video (STAGING, not deployed).

Objects are owner/job scoped, checksum verified and addressed by unpredictable
random keys. S3 bucket must be private; encrypted-at-rest, bucket lifecycle and
cross-user authentication are operational prerequisites. No public ACL or CDN
read path. No live service is configured by this module.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import hashlib, hmac, io, os, re, time, uuid
from urllib.parse import urlsplit

_OWNER=re.compile(r"^[a-f0-9]{64}$")
_SHA=re.compile(r"^[a-f0-9]{64}$")
_JOB=re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_KINDS={'reference':('image/jpeg','image/png','image/webp'),
        'scene':('video/mp4',),
        'output':('video/mp4',)}
_EXT={'image/jpeg':'jpg','image/png':'png','image/webp':'webp','video/mp4':'mp4'}
_LIMIT={'reference':10*1024*1024,'scene':300*1024*1024,'output':300*1024*1024}
_TTL={'reference':45*60,'scene':24*3600,'output':7*24*3600}

class StorageError(RuntimeError):pass
class UnauthorizedMedia(StorageError):pass
class MediaExpired(StorageError):pass

@dataclass(frozen=True)
class StoredMedia:
    key:str
    owner_hash:str
    job_id:str
    kind:str
    media_type:str
    size:int
    sha256:str
    expires_at:int

def _validate(owner_hash:str,job_id:str,kind:str,content_type:str):
    if not _OWNER.fullmatch(owner_hash) or not _JOB.fullmatch(job_id):
        raise UnauthorizedMedia('Unverified owner or job identifier')
    if kind not in _KINDS or content_type not in _KINDS[kind]:
        raise StorageError('Unsupported media type or artifact role')

def _key(owner_hash:str,job_id:str,kind:str,identifier:str,content_type:str)->str:
    return f'private/{owner_hash}/{job_id}/{kind}/{identifier}.{_EXT[content_type]}'

class PrivateObjectStore:
    def __init__(self,client,bucket:str,*,clock=None):
        if not re.fullmatch(r'[a-z0-9][a-z0-9.-]{2,61}[a-z0-9]',bucket):
            raise StorageError('Valid private object bucket is required')
        self.client=client
        self.bucket=bucket
        self.clock=clock or time.time

    def put(self,owner_hash:str,job_id:str,kind:str,
            file:Path,media_type:str)->StoredMedia:
        _validate(owner_hash,job_id,kind,media_type)
        path=Path(file).resolve(strict=True)
        if not path.is_file():raise StorageError('Source must be a local file')
        size=path.stat().st_size
        if not 64<=size<=_LIMIT[kind]:
            raise StorageError('Media size exceeds allowed bounds')
        with path.open('rb') as f:
            header=f.read(16)
            if media_type=='video/mp4' and header[4:8]!=b'ftyp':
                raise StorageError('MP4 signature absent')
            if media_type=='image/jpeg' and not header.startswith(b'\xff\xd8\xff'):
                raise StorageError('JPEG signature absent')
            if media_type=='image/png' and not header.startswith(b'\x89PNG\r\n\x1a\n'):
                raise StorageError('PNG signature absent')
            if media_type=='image/webp' and not (
                header.startswith(b'RIFF') and header[8:12]==b'WEBP'):
                raise StorageError('WEBP signature absent')
            f.seek(0)
            digest=hashlib.sha256()
            while piece:=f.read(1024*1024):digest.update(piece)
        sha=digest.hexdigest()
        key=_key(owner_hash,job_id,kind,uuid.uuid4().hex,media_type)
        expiry=int(self.clock())+_TTL[kind]
        metadata={'sha256':sha,'owner':owner_hash,'job':job_id,
                  'kind':kind,'expires':str(expiry)}
        try:
            with path.open('rb') as contents:
                self.client.put_object(Bucket=self.bucket,Key=key,
                    Body=contents,ContentLength=size,ContentType=media_type,
                    Metadata=metadata,ServerSideEncryption='AES256',
                    IfNoneMatch='*')
            item=self.head(owner_hash,job_id,key,kind)
            if item.sha256!=sha or item.size!=size:
                raise StorageError('Uploaded object integrity mismatch')
            return item
        except Exception:
            # A failed upload or integrity check cannot produce a valid receipt.
            # Cleanup is best effort; bucket lifecycle handles residual orphans.
            try:self.client.delete_object(Bucket=self.bucket,Key=key)
            except Exception:pass
            raise

    def head(self,owner_hash:str,job_id:str,key:str,kind:str)->StoredMedia:
        if not _OWNER.fullmatch(owner_hash) or not _JOB.fullmatch(job_id) or kind not in _KINDS:
            raise UnauthorizedMedia('Invalid owner/job scope')
        prefix=f'private/{owner_hash}/{job_id}/{kind}/'
        if not isinstance(key,str) or not key.startswith(prefix) or len(key)>260:
            raise UnauthorizedMedia('Media does not belong to this job')
        try:obj=self.client.head_object(Bucket=self.bucket,Key=key)
        except Exception as e:raise StorageError('Media not available in private object storage') from e
        meta=obj.get('Metadata') or {}
        if (meta.get('owner')!=owner_hash or meta.get('job')!=job_id or
            meta.get('kind')!=kind):
            raise UnauthorizedMedia('Private storage metadata does not match owner/job')
        stamp=meta.get('expires','')
        if not stamp.isdigit() or int(stamp)<=int(self.clock()):
            raise MediaExpired('Media retention window ended')
        digest=meta.get('sha256','')
        media=obj.get('ContentType','')
        size=obj.get('ContentLength')
        if (not _SHA.fullmatch(digest) or media not in _KINDS[kind] or
            type(size)is not int or not 64<=size<=_LIMIT[kind]):
            raise StorageError('Media metadata invalid')
        return StoredMedia(key,owner_hash,job_id,kind,media,size,digest,int(stamp))

    def private_download_url(self,owner_hash:str,job_id:str,key:str,
                             kind:str,*,expires_seconds:int=300)->str:
        """Must be called only after server-side authenticated owner check."""
        if type(expires_seconds)is not int or not 30<=expires_seconds<=900:
            raise StorageError('Presigned URL lifetime outside safe range')
        item=self.head(owner_hash,job_id,key,kind)
        remaining=item.expires_at-int(self.clock())
        if remaining<expires_seconds:
            raise MediaExpired('Media expires before requested download URL')
        url=self.client.generate_presigned_url('get_object',
            Params={'Bucket':self.bucket,'Key':key},
            ExpiresIn=expires_seconds,HttpMethod='GET')
        # Configured endpoint must use TLS and must not contain userinfo.
        parts=urlsplit(url)
        if parts.scheme!='https' or not parts.hostname or parts.username or parts.password:
            raise StorageError('Insecure presigned storage endpoint')
        return url

    def check_download(self,owner_hash:str,job_id:str,key:str,kind:str,
                       *,max_bytes:int|None=None)->bytes:
        """Only use for small image references; video streams must stay streamed."""
        item=self.head(owner_hash,job_id,key,kind)
        ceiling=max_bytes if max_bytes is not None else _LIMIT[kind]
        if type(ceiling)is not int or item.size>ceiling:
            raise StorageError('Download would exceed memory limit')
        response=self.client.get_object(Bucket=self.bucket,Key=key)
        try:
            body=response['Body'].read(item.size+1)
        finally:
            response['Body'].close()
        if len(body)!=item.size or not hmac.compare_digest(
            hashlib.sha256(body).hexdigest(),item.sha256):
            raise StorageError('Downloaded media checksum mismatch')
        return body

    def delete(self,owner_hash:str,job_id:str,key:str,kind:str)->None:
        self.head(owner_hash,job_id,key,kind)
        self.client.delete_object(Bucket=self.bucket,Key=key)

def configured_from_environment(env=None)->bool:
    """No automatic access to user credentials from a distributed APK."""
    data=os.environ if env is None else env
    required=('KOLBO_S3_BUCKET','KOLBO_S3_ENDPOINT','KOLBO_S3_ACCESS_KEY',
              'KOLBO_S3_SECRET_KEY','KOLBO_S3_REGION')
    if any(not data.get(k) for k in required):return False
    target=urlsplit(data['KOLBO_S3_ENDPOINT'])
    return target.scheme=='https' and bool(target.hostname) and not (
        target.username or target.password or target.fragment)

def create_client_from_environment(env=None):
    data=os.environ if env is None else env
    if not configured_from_environment(data):
        raise StorageError('Private S3-compatible storage is not configured')
    import boto3
    from botocore.config import Config
    return PrivateObjectStore(boto3.client('s3',
        endpoint_url=data['KOLBO_S3_ENDPOINT'],
        region_name=data['KOLBO_S3_REGION'],
        aws_access_key_id=data['KOLBO_S3_ACCESS_KEY'],
        aws_secret_access_key=data['KOLBO_S3_SECRET_KEY'],
        config=Config(signature_version='s3v4',
            retries={'max_attempts':2,'mode':'standard'})),
        data['KOLBO_S3_BUCKET'])
