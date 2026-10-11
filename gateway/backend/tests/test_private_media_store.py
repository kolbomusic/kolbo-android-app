"""S3-like fake validates object access rules without an account or real cost."""
import hashlib,io,uuid
from pathlib import Path
import pytest
import private_media_store as media

OWNER='a'*64
OTHER='b'*64
JOB='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
OTHER_JOB='bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'

class Body:
    def __init__(self,content):self._f=io.BytesIO(content)
    def read(self,n=-1):return self._f.read(n)
    def close(self):self._f.close()

class FakeS3:
    def __init__(self):
        self.data={}
        self.last_put={}
    def put_object(self,**kw):
        self.last_put=kw
        identifier=(kw['Bucket'],kw['Key'])
        assert kw['ServerSideEncryption']=='AES256'
        assert kw['IfNoneMatch']=='*'
        if identifier in self.data:raise ValueError('Object already exists')
        content=kw['Body'].read()
        if len(content)!=kw['ContentLength']:raise ValueError('Size mismatch')
        self.data[identifier]={'content':content,'metadata':dict(kw['Metadata']),
                               'ctype':kw['ContentType']}
    def head_object(self,**kw):
        obj=self.data[(kw['Bucket'],kw['Key'])]
        return {'ContentLength':len(obj['content']),'ContentType':obj['ctype'],
                'Metadata':dict(obj['metadata'])}
    def get_object(self,**kw):
        obj=self.data[(kw['Bucket'],kw['Key'])]
        return {'Body':Body(obj['content'])}
    def delete_object(self,**kw):
        self.data.pop((kw['Bucket'],kw['Key']),None)
    def generate_presigned_url(self,operation,Params,ExpiresIn,HttpMethod):
        assert operation=='get_object' and HttpMethod=='GET'
        return ('https://private-object.example.com/'
                +Params['Key']+'?X-Amz-Expires='+str(ExpiresIn))

@pytest.fixture
def source(tmp_path):
    path=tmp_path/'video.mp4'
    path.write_bytes(b'\x00\x00\x00\x20ftypisom'+b'1'*2500)
    return path

@pytest.fixture
def store():
    fake=FakeS3()
    return media.PrivateObjectStore(fake,'kolbo-video-private',clock=lambda:1000),fake

def test_secure_mp4_upload_head_and_url_ttl(store,source):
    s,f=store
    entry=s.put(OWNER,JOB,'scene',source,'video/mp4')
    assert entry.size==source.stat().st_size
    assert entry.sha256==hashlib.sha256(source.read_bytes()).hexdigest()
    assert f.last_put['ServerSideEncryption']=='AES256'
    assert entry.key.startswith(f'private/{OWNER}/{JOB}/scene/')
    assert s.head(OWNER,JOB,entry.key,'scene')==entry
    assert s.check_download(OWNER,JOB,entry.key,'scene')==source.read_bytes()
    url=s.private_download_url(OWNER,JOB,entry.key,'scene',expires_seconds=300)
    assert url.startswith('https://private-object.example.com/')
    assert 'X-Amz-Expires=300' in url

def test_path_guessing_different_owner_or_job_always_fails(store,source):
    s,f=store
    item=s.put(OWNER,JOB,'output',source,'video/mp4')
    for owner,job,kind in [(OTHER,JOB,'output'),(OWNER,OTHER_JOB,'output'),
                          (OWNER,JOB,'reference')]:
        with pytest.raises(media.UnauthorizedMedia):
            s.head(owner,job,item.key,kind)
        with pytest.raises(media.UnauthorizedMedia):
            s.private_download_url(owner,job,item.key,kind)

def test_unexpected_metadata_owner_rejected_even_correct_prefix(store,source):
    s,f=store
    item=s.put(OWNER,JOB,'scene',source,'video/mp4')
    f.data[(s.bucket,item.key)]['metadata']['owner']=OTHER
    with pytest.raises(media.UnauthorizedMedia):
        s.head(OWNER,JOB,item.key,'scene')

def test_storage_rejects_corrupt_payload_after_download(store,source):
    s,f=store
    item=s.put(OWNER,JOB,'scene',source,'video/mp4')
    f.data[(s.bucket,item.key)]['content']=b'\x00\x00\x00\x20ftypisom'+b'x'*2500
    with pytest.raises(media.StorageError,match='checksum mismatch'):
        s.check_download(OWNER,JOB,item.key,'scene')

def test_expired_object_rejected_and_no_presigned_link(store,source):
    s,f=store
    item=s.put(OWNER,JOB,'reference',source.with_name('reference.jpg')
       if False else _create_jpeg(source.parent),'image/jpeg')
    s.clock=lambda:1000+46*60
    with pytest.raises(media.MediaExpired):
        s.head(OWNER,JOB,item.key,'reference')
    with pytest.raises(media.MediaExpired):
        s.private_download_url(OWNER,JOB,item.key,'reference')

def _create_jpeg(folder):
    path=folder/'reference.jpg'
    path.write_bytes(b'\xff\xd8\xff'+b'J'*2500)
    return path

def test_no_public_bucket_and_no_access_without_real_configuration():
    assert not media.configured_from_environment({})
    assert not media.configured_from_environment({
        'KOLBO_S3_BUCKET':'a','KOLBO_S3_ENDPOINT':'http://localhost:9000',
        'KOLBO_S3_ACCESS_KEY':'fake','KOLBO_S3_SECRET_KEY':'fake',
        'KOLBO_S3_REGION':'eu-central-1'})
    with pytest.raises(media.StorageError):
        media.create_client_from_environment({})

def test_no_fake_mp4_or_file_outside_scope(store,source,tmp_path):
    s,f=store
    path=tmp_path/'fake.mp4'
    path.write_bytes(b'NOT REAL MP4'+b'0'*100)
    with pytest.raises(media.StorageError,match='MP4 signature'):
        s.put(OWNER,JOB,'scene',path,'video/mp4')
    with pytest.raises(media.StorageError):
        s.put(OWNER,JOB,'scene',source,'image/jpeg')
    with pytest.raises(media.UnauthorizedMedia):
        s.put('invalid_owner',JOB,'scene',source,'video/mp4')

def test_expiration_never_extended_by_presign(store,source):
    s,f=store
    entry=s.put(OWNER,JOB,'scene',source,'video/mp4')
    s.clock=lambda:entry.expires_at-100
    with pytest.raises(media.MediaExpired):
        s.private_download_url(OWNER,JOB,entry.key,'scene',expires_seconds=300)
    url=s.private_download_url(OWNER,JOB,entry.key,'scene',expires_seconds=90)
    assert 'X-Amz-Expires=90' in url

def test_reject_overlong_or_very_short_presigned_links(store,source):
    s,_=store
    item=s.put(OWNER,JOB,'scene',source,'video/mp4')
    with pytest.raises(media.StorageError):s.private_download_url(OWNER,JOB,item.key,'scene',expires_seconds=2000)
    with pytest.raises(media.StorageError):s.private_download_url(OWNER,JOB,item.key,'scene',expires_seconds=1)

def test_output_upload_random_keys_are_unique_and_never_overwrite(store,source):
    s,f=store
    a=s.put(OWNER,JOB,'output',source,'video/mp4')
    b=s.put(OWNER,JOB,'output',source,'video/mp4')
    assert a.key!=b.key
    assert len(f.data)==2
    assert all(obj['content']==source.read_bytes() for obj in f.data.values())


def test_private_scene_survives_worker_restart_and_restores_as_stream(store,source,tmp_path):
    s,f=store
    saved=s.put(OWNER,JOB,'scene',source,'video/mp4')
    # A different coordinator instance after restart can verify the same
    # durable object without relying on any ephemeral server process memory.
    restarted=media.PrivateObjectStore(f,s.bucket,clock=lambda:1001)
    restored=restarted.restore_to_local(OWNER,JOB,saved.key,'scene',
        tmp_path/'restarted-worker','scene001.mp4')
    assert restored.read_bytes()==source.read_bytes()
    assert restored.stat().st_mode & 0o777==0o600
    with pytest.raises(media.StorageError,match='overwrite'):
        restarted.restore_to_local(OWNER,JOB,saved.key,'scene',
            tmp_path/'restarted-worker','scene001.mp4')
    assert restored.read_bytes()==source.read_bytes()

def test_restored_mp4_with_tampered_content_is_never_written(store,source,tmp_path):
    s,f=store
    saved=s.put(OWNER,JOB,'scene',source,'video/mp4')
    f.data[(s.bucket,saved.key)]['content']=b'\x00\x00\x00\x20ftypisom'+b'Z'*2500
    with pytest.raises(media.StorageError,match='integrity mismatch'):
        s.restore_to_local(OWNER,JOB,saved.key,'scene',
            tmp_path/'private','scene002.mp4')
    assert not (tmp_path/'private'/'scene002.mp4').exists()

def test_private_restore_cannot_read_other_account_job(store,source,tmp_path):
    s,f=store
    saved=s.put(OWNER,JOB,'scene',source,'video/mp4')
    with pytest.raises(media.UnauthorizedMedia):
        s.restore_to_local(OTHER,JOB,saved.key,'scene',
            tmp_path/'private','scene003.mp4')
    with pytest.raises(media.UnauthorizedMedia):
        s.restore_to_local(OWNER,OTHER_JOB,saved.key,'scene',
            tmp_path/'private','scene003.mp4')
